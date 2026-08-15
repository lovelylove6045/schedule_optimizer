"""Checks a plan-board course swap or add against the same hard constraints
`optimizer_model` enforces when the solver builds a plan from scratch --
course-offering eligibility, per-term credit caps, and prerequisite/
corequisite ordering -- so a manual edit can never produce a schedule the
solver itself would have rejected.

Reimplemented as plain Python over one already-solved plan's fixed course
placements, rather than reusing `optimizer_model` directly: that module's
constraint logic is built entirely out of CP-SAT boolean variables inside an
active model, which have no meaning once a plan is already solved and a
student is just editing one slot."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.degree_plan import DegreePlan
from app.models.enums import RequisiteType
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_term import ScenarioTerm
from app.models.student_credit import StudentCredit
from app.models.term import Term
from app.schemas.prerequisite import PrerequisiteNodeOut
from app.services import catalog_service
from app.services.credit_matching_service import COMPLETED_STATUS

_SAME_TERM_ALLOWED_REQUISITE_TYPES = {RequisiteType.COREQUISITE, RequisiteType.PRE_OR_COREQUISITE}
_TERM_TYPE_OFFERING_FIELDS = {"FALL": "fall_offered", "SPRING": "spring_offered", "SUMMER": "summer_offered"}


class CourseNotOfferedInTermError(Exception):
    """Raised when the new course isn't offered during the slot's term type."""


class TermCreditCapExceededError(Exception):
    """Raised when the swap would push its term's total credit hours over the scenario's cap."""


class PrerequisiteNotMetError(Exception):
    """Raised when the new course's prerequisite/corequisite chain isn't satisfied by this plan yet."""


def validate_swap(db: Session, plan_course: PlanCourse, new_course: Course) -> None:
    """Raise the first hard-constraint violation from swapping `plan_course` to
    `new_course`: term-offering eligibility, then the term's credit cap, then
    prerequisite/corequisite ordering."""
    term = db.get(Term, plan_course.term_id)
    _validate_course_for_slot(db, plan_course.degree_plan_id, term, new_course, plan_course.plan_course_id)


def validate_add(db: Session, degree_plan_id: int, term_id: int, new_course: Course) -> None:
    """Raise the first hard-constraint violation from adding `new_course` to
    `degree_plan_id` in `term_id` as a brand-new slot (no existing plan_course
    to exclude, unlike a swap)."""
    term = db.get(Term, term_id)
    _validate_course_for_slot(db, degree_plan_id, term, new_course, exclude_plan_course_id=None)


def _validate_course_for_slot(
    db: Session, degree_plan_id: int, term: Term, new_course: Course, exclude_plan_course_id: int | None
) -> None:
    """Run every hard-constraint check for placing `new_course` into `term` on
    this plan, shared by both `validate_swap` (excludes the slot being
    replaced) and `validate_add` (no slot to exclude)."""
    _check_offered_in_term(new_course, term)
    _check_term_credit_cap(db, degree_plan_id, term, new_course, exclude_plan_course_id)
    _check_prerequisites_satisfied(db, degree_plan_id, term, new_course, exclude_plan_course_id)


def _check_offered_in_term(new_course: Course, term: Term) -> None:
    """Raise if `new_course` isn't offered during `term`'s term type."""
    field_name = _TERM_TYPE_OFFERING_FIELDS.get(term.term_type)
    if field_name and not getattr(new_course, field_name):
        raise CourseNotOfferedInTermError(
            f"Course {new_course.course_id} isn't offered in {term.term_type.lower()} terms like {term.term_code}"
        )


def _check_term_credit_cap(
    db: Session, degree_plan_id: int, term: Term, new_course: Course, exclude_plan_course_id: int | None
) -> None:
    """Raise if placing `new_course` in this slot would push `term`'s total
    credit hours over its scenario_terms override or the scenario's default max."""
    maximum = _term_credit_maximum(db, degree_plan_id, term.term_id)
    if maximum is None:
        return
    other_credits = _other_courses_credit_total(db, degree_plan_id, term.term_id, exclude_plan_course_id)
    projected_total = other_credits + float(new_course.credit_hours)
    if projected_total > maximum:
        raise TermCreditCapExceededError(
            f"Adding course {new_course.course_id} would put {term.term_code} at "
            f"{projected_total:g} credits, over its {maximum:g}-credit cap"
        )


def _term_credit_maximum(db: Session, degree_plan_id: int, term_id: int) -> float | None:
    """Return this term's credit-hour cap: a scenario_terms override if one exists
    for it, else the scenario's default_maximum_credits, or None if neither is set."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    if scenario is None:
        return None
    override = (
        db.query(ScenarioTerm.maximum_credits)
        .filter(ScenarioTerm.planning_scenario_id == scenario.planning_scenario_id, ScenarioTerm.term_id == term_id)
        .scalar()
    )
    maximum = override if override is not None else scenario.default_maximum_credits
    return float(maximum) if maximum is not None else None


def _scenario_for_plan(db: Session, degree_plan_id: int) -> PlanningScenario | None:
    """Look up the planning_scenario a degree plan belongs to, or None if either is missing."""
    plan = db.get(DegreePlan, degree_plan_id)
    return db.get(PlanningScenario, plan.planning_scenario_id) if plan is not None else None


def _other_courses_credit_total(
    db: Session, degree_plan_id: int, term_id: int, exclude_plan_course_id: int | None
) -> float:
    """Sum the credit hours of every other plan_courses row sharing this term."""
    query = db.query(PlanCourse.credit_hours).filter(
        PlanCourse.degree_plan_id == degree_plan_id, PlanCourse.term_id == term_id
    )
    if exclude_plan_course_id is not None:
        query = query.filter(PlanCourse.plan_course_id != exclude_plan_course_id)
    return sum(float(credit_hours) for (credit_hours,) in query.all())


def _check_prerequisites_satisfied(
    db: Session, degree_plan_id: int, term: Term, new_course: Course, exclude_plan_course_id: int | None
) -> None:
    """Raise if any of `new_course`'s prerequisite/corequisite roots aren't already
    satisfied by completed coursework or by another course this plan places early
    enough relative to `term`."""
    roots = catalog_service.get_prerequisite_tree(db, new_course.course_id)
    if not roots:
        return
    completed_ids = _completed_course_ids(db, degree_plan_id)
    placements = _course_term_sequence(db, degree_plan_id, exclude_plan_course_id)
    if any(not _node_satisfied(root, completed_ids, placements, term.sequence_index) for root in roots):
        raise PrerequisiteNotMetError(
            f"Course {new_course.course_id} needs a prerequisite this plan hasn't placed before {term.term_code}"
        )


def _completed_course_ids(db: Session, degree_plan_id: int) -> set[int]:
    """Return this plan's student's completed course ids, per student_credits."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    if scenario is None:
        return set()
    rows = (
        db.query(StudentCredit.course_id)
        .filter(StudentCredit.student_id == scenario.student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    return {course_id for (course_id,) in rows if course_id is not None}


def _course_term_sequence(
    db: Session, degree_plan_id: int, exclude_plan_course_id: int | None
) -> dict[int, int]:
    """Map each other plan_courses row's course_id to its term's sequence_index, for
    checking whether a prerequisite is placed early enough elsewhere in this plan."""
    query = (
        db.query(PlanCourse.course_id, Term.sequence_index)
        .join(Term, Term.term_id == PlanCourse.term_id)
        .filter(PlanCourse.degree_plan_id == degree_plan_id)
    )
    if exclude_plan_course_id is not None:
        query = query.filter(PlanCourse.plan_course_id != exclude_plan_course_id)
    return dict(query.all())


def _node_satisfied(
    node: PrerequisiteNodeOut, completed_ids: set[int], placements: dict[int, int], before_sequence: int
) -> bool:
    """Evaluate one prerequisite-tree node against a plan's fixed course
    placements, mirroring `optimizer_model`'s CP-SAT constraint but as a plain
    boolean check over an already-solved plan."""
    if node.node_type == "COURSE" and node.required_course is not None:
        same_term_allowed = node.requisite_type in _SAME_TERM_ALLOWED_REQUISITE_TYPES
        return _course_satisfied_before(
            node.required_course.course_id, completed_ids, placements, before_sequence, same_term_allowed
        )
    if node.children:
        return _aggregate_satisfied(node, completed_ids, placements, before_sequence)
    return True


def _aggregate_satisfied(
    node: PrerequisiteNodeOut, completed_ids: set[int], placements: dict[int, int], before_sequence: int
) -> bool:
    """Combine a GROUP node's children per its rule_operator (ALL by default,
    matching `optimizer_model._aggregate_prerequisite_indicator`)."""
    results = [_node_satisfied(child, completed_ids, placements, before_sequence) for child in node.children]
    if node.rule_operator == "ANY":
        return any(results)
    if node.rule_operator == "N_OF":
        return sum(results) >= (node.required_count or 1)
    return all(results)


def _course_satisfied_before(
    course_id: int,
    completed_ids: set[int],
    placements: dict[int, int],
    before_sequence: int,
    same_term_allowed: bool,
) -> bool:
    """Return whether `course_id` is already completed, or placed by this plan
    early enough relative to `before_sequence` (same term too, for co-requisites)."""
    if course_id in completed_ids:
        return True
    sequence = placements.get(course_id)
    if sequence is None:
        return False
    return sequence <= before_sequence if same_term_allowed else sequence < before_sequence
