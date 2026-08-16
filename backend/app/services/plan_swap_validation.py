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
from app.models.course_relation import CourseRelation
from app.models.degree_plan import DegreePlan
from app.models.enums import CourseRelationType, RequisiteType, ScenarioPreferenceType
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_term import ScenarioTerm
from app.models.student_credit import StudentCredit
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_preference import ScenarioPreference
from app.models.term import Term
from app.schemas.prerequisite import PrerequisiteNodeOut
from app.services import catalog_service
from app.services.credit_matching_service import COMPLETED_STATUS

_SAME_TERM_ALLOWED_REQUISITE_TYPES = {RequisiteType.COREQUISITE, RequisiteType.PRE_OR_COREQUISITE}
_TERM_TYPE_OFFERING_FIELDS = {"FALL": "fall_offered", "SPRING": "spring_offered", "SUMMER": "summer_offered"}


class PlanEditConstraintError(Exception):
    """Raised when a manual placement violates a scenario or academic constraint."""


class CourseNotOfferedInTermError(PlanEditConstraintError):
    """Raised when the new course isn't offered during the slot's term type."""


class TermCreditCapExceededError(PlanEditConstraintError):
    """Raised when the swap would push its term's total credit hours over the scenario's cap."""


class PrerequisiteNotMetError(PlanEditConstraintError):
    """Raised when the new course's prerequisite/corequisite chain isn't satisfied by this plan yet."""


class SummerEnrollmentNotAllowedError(PlanEditConstraintError):
    """Raised when a plan edit tries to use a summer term that the scenario disabled."""


class DuplicateCreditError(PlanEditConstraintError):
    """Raised when related courses would receive impermissible duplicate academic credit."""


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


def validate_move(db: Session, plan_course: PlanCourse, term_id: int, course: Course) -> None:
    """Validate moving an existing placement while excluding its original slot from totals."""
    term = db.get(Term, term_id)
    _validate_course_for_slot(db, plan_course.degree_plan_id, term, course, plan_course.plan_course_id)


def _validate_course_for_slot(
    db: Session, degree_plan_id: int, term: Term, new_course: Course, exclude_plan_course_id: int | None
) -> None:
    """Run every hard-constraint check for placing `new_course` into `term` on
    this plan, shared by both `validate_swap` (excludes the slot being
    replaced) and `validate_add` (no slot to exclude)."""
    _check_offered_in_term(new_course, term)
    _check_summer_allowed(db, degree_plan_id, term)
    _check_term_in_scenario_window(db, degree_plan_id, term)
    _check_term_credit_cap(db, degree_plan_id, term, new_course, exclude_plan_course_id)
    _check_prerequisites_satisfied(db, degree_plan_id, term, new_course, exclude_plan_course_id)


def _check_offered_in_term(new_course: Course, term: Term) -> None:
    """Raise if `new_course` isn't offered during `term`'s term type."""
    field_name = _TERM_TYPE_OFFERING_FIELDS.get(term.term_type)
    if field_name and not getattr(new_course, field_name):
        raise CourseNotOfferedInTermError(
            f"Course {new_course.course_id} isn't offered in {term.term_type.lower()} terms like {term.term_code}"
        )


def _check_summer_allowed(db: Session, degree_plan_id: int, term: Term) -> None:
    """Raise when the scenario disables summer but an edit targets a summer term."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    if term.term_type == "SUMMER" and scenario is not None and not scenario.allow_summer:
        raise SummerEnrollmentNotAllowedError("Summer enrollment is disabled for this scenario")


def _check_term_in_scenario_window(db: Session, degree_plan_id: int, term: Term) -> None:
    """Reject excluded terms and placements outside the scenario's planning window."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    if scenario is None:
        return
    override = db.query(ScenarioTerm).filter(
        ScenarioTerm.planning_scenario_id == scenario.planning_scenario_id,
        ScenarioTerm.term_id == term.term_id,
    ).one_or_none()
    if override is not None and override.is_excluded:
        raise PlanEditConstraintError(f"{term.term_code} is excluded from this scenario")
    start = db.get(Term, scenario.start_term_id) if scenario.start_term_id is not None else None
    target = db.get(Term, scenario.target_graduation_term_id) if scenario.target_graduation_term_id else None
    if start is not None and term.sequence_index < start.sequence_index:
        raise PlanEditConstraintError(f"{term.term_code} is before this scenario's starting term")
    if target is not None and term.sequence_index > target.sequence_index:
        raise PlanEditConstraintError(f"{term.term_code} is after the target graduation term")


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
    default_maximum = (
        scenario.summer_maximum_credits if db.get(Term, term_id).term_type == "SUMMER"
        else scenario.default_maximum_credits
    )
    maximum = override if override is not None else default_maximum
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
    completed_ids, placements = _expand_equivalent_coursework(db, completed_ids, placements)
    completed_credits = _credits_completed_before(db, degree_plan_id, term.sequence_index, exclude_plan_course_id)
    selected_program_ids = _selected_program_ids(db, degree_plan_id)
    if any(
        not _node_satisfied(
            root, completed_ids, placements, term.sequence_index, completed_credits, selected_program_ids
        )
        for root in roots
    ):
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


def _expand_equivalent_coursework(
    db: Session, completed_ids: set[int], placements: dict[int, int]
) -> tuple[set[int], dict[int, int]]:
    """Expand transcript and planned coursework through directed equivalence relations."""
    source_ids = completed_ids | set(placements)
    if not source_ids:
        return completed_ids, placements
    relations = db.query(CourseRelation).filter(
        CourseRelation.relation_type.in_((CourseRelationType.CROSS_LISTED, CourseRelationType.EQUIVALENT)),
        (CourseRelation.course_id.in_(source_ids) | CourseRelation.related_course_id.in_(source_ids)),
    ).all()
    expanded_completed = set(completed_ids)
    expanded_placements = dict(placements)
    for relation in relations:
        _copy_equivalent_coursework(relation.course_id, relation.related_course_id, expanded_completed, expanded_placements)
        if relation.is_bidirectional:
            _copy_equivalent_coursework(relation.related_course_id, relation.course_id, expanded_completed, expanded_placements)
    return expanded_completed, expanded_placements


def _copy_equivalent_coursework(
    source_id: int,
    target_id: int,
    completed_ids: set[int],
    placements: dict[int, int],
) -> None:
    """Copy one earned or planned course's completion signal to its valid equivalent."""
    if source_id in completed_ids:
        completed_ids.add(target_id)
    if source_id in placements:
        placements[target_id] = min(placements.get(target_id, placements[source_id]), placements[source_id])


def _node_satisfied(
    node: PrerequisiteNodeOut,
    completed_ids: set[int],
    placements: dict[int, int],
    before_sequence: int,
    completed_credits: float,
    selected_program_ids: set[int],
) -> bool:
    """Evaluate one prerequisite-tree node against a plan's fixed course
    placements, mirroring `optimizer_model`'s CP-SAT constraint but as a plain
    boolean check over an already-solved plan."""
    if node.node_type == "COURSE" and node.required_course is not None:
        same_term_allowed = node.requisite_type in _SAME_TERM_ALLOWED_REQUISITE_TYPES
        return _course_satisfied_before(
            node.required_course.course_id, completed_ids, placements, before_sequence, same_term_allowed
        )
    if node.node_type == "CREDIT_HOURS" and node.minimum_total_credits is not None:
        return completed_credits >= node.minimum_total_credits
    if node.node_type == "STANDING" and node.minimum_standing is not None:
        thresholds = {"SOPHOMORE": 30, "JUNIOR": 60, "SENIOR": 90, "GRADUATE": 120}
        return completed_credits >= thresholds.get(node.minimum_standing, 0)
    if node.node_type == "PROGRAM_MEMBERSHIP" and node.required_academic_program_id is not None:
        return node.required_academic_program_id in selected_program_ids
    if node.children:
        return _aggregate_satisfied(
            node, completed_ids, placements, before_sequence, completed_credits, selected_program_ids
        )
    return True


def _aggregate_satisfied(
    node: PrerequisiteNodeOut,
    completed_ids: set[int],
    placements: dict[int, int],
    before_sequence: int,
    completed_credits: float,
    selected_program_ids: set[int],
) -> bool:
    """Combine a GROUP node's children per its rule_operator (ALL by default,
    matching `optimizer_model._aggregate_prerequisite_indicator`)."""
    results = [
        _node_satisfied(
            child, completed_ids, placements, before_sequence, completed_credits, selected_program_ids
        )
        for child in node.children
    ]
    if node.rule_operator == "ANY":
        return any(results)
    if node.rule_operator == "N_OF":
        return sum(results) >= (node.required_count or 1)
    return all(results)


def _credits_completed_before(
    db: Session, degree_plan_id: int, before_sequence: int, exclude_plan_course_id: int | None
) -> float:
    """Return transcript plus prior-term planned credits before a prospective placement."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    transcript_rows = (
        db.query(StudentCredit.credits_earned, Course.credit_hours)
        .outerjoin(Course, Course.course_id == StudentCredit.course_id)
        .filter(StudentCredit.student_id == scenario.student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    total = sum(float(earned if earned is not None else (catalog or 0)) for earned, catalog in transcript_rows)
    query = (
        db.query(PlanCourse.credit_hours)
        .join(Term, Term.term_id == PlanCourse.term_id)
        .filter(PlanCourse.degree_plan_id == degree_plan_id, Term.sequence_index < before_sequence)
    )
    if exclude_plan_course_id is not None:
        query = query.filter(PlanCourse.plan_course_id != exclude_plan_course_id)
    return total + sum(float(credits) for (credits,) in query.all())


def _selected_program_ids(db: Session, degree_plan_id: int) -> set[int]:
    """Return academic programs selected on the plan's scenario."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    rows = (
        db.query(ScenarioProgram.academic_program_id)
        .filter(ScenarioProgram.planning_scenario_id == scenario.planning_scenario_id)
        .all()
    )
    return {program_id for (program_id,) in rows}


def validate_existing_plan(db: Session, degree_plan_id: int) -> None:
    """Recheck every placement so edits cannot break downstream prerequisites or limits."""
    rows = db.query(PlanCourse).filter(PlanCourse.degree_plan_id == degree_plan_id).all()
    for plan_course in rows:
        course = db.get(Course, plan_course.course_id)
        term = db.get(Term, plan_course.term_id)
        _validate_course_for_slot(db, degree_plan_id, term, course, plan_course.plan_course_id)
    _validate_term_minimums(db, degree_plan_id, rows)
    _validate_hard_preferences(db, degree_plan_id, rows)
    _validate_course_relations(db, rows)


def _validate_term_minimums(
    db: Session, degree_plan_id: int, plan_courses: list[PlanCourse]
) -> None:
    """Require each used term to retain its configured minimum credit load."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    if scenario is None:
        return
    overrides = {
        row.term_id: row
        for row in db.query(ScenarioTerm).filter(
            ScenarioTerm.planning_scenario_id == scenario.planning_scenario_id
        ).all()
    }
    credits_by_term: dict[int, float] = {}
    for row in plan_courses:
        credits_by_term[row.term_id] = credits_by_term.get(row.term_id, 0) + float(row.credit_hours)
    for term_id, credits in credits_by_term.items():
        override = overrides.get(term_id)
        term = db.get(Term, term_id)
        if override is not None and override.minimum_credits is not None:
            minimum = override.minimum_credits
        elif term.term_type == "SUMMER":
            minimum = None
        else:
            minimum = scenario.default_minimum_credits
        if minimum is not None and credits + 0.01 < float(minimum):
            raise PlanEditConstraintError(
                f"{term.term_code} would have {credits:g} credits, below its {float(minimum):g}-credit minimum"
            )


def _validate_hard_preferences(
    db: Session, degree_plan_id: int, plan_courses: list[PlanCourse]
) -> None:
    """Recheck required, avoided, and fixed-to-term course preferences after an edit."""
    scenario = _scenario_for_plan(db, degree_plan_id)
    if scenario is None:
        return
    placements = {row.course_id: row.term_id for row in plan_courses}
    completed_ids = _completed_course_ids(db, degree_plan_id)
    rows = db.query(ScenarioPreference).filter(
        ScenarioPreference.planning_scenario_id == scenario.planning_scenario_id
    ).all()
    for preference in rows:
        _validate_hard_preference(preference, placements, completed_ids)


def _validate_hard_preference(
    preference: ScenarioPreference, placements: dict[int, int], completed_ids: set[int]
) -> None:
    """Raise when one inherently mandatory course preference no longer holds."""
    course_id = preference.course_id
    if course_id is None:
        return
    if (
        preference.preference_type == ScenarioPreferenceType.REQUIRE_COURSE
        and course_id not in placements
        and course_id not in completed_ids
    ):
        raise PlanEditConstraintError(f"Course {course_id} is required by this scenario")
    if preference.preference_type == ScenarioPreferenceType.AVOID_COURSE and course_id in placements:
        raise PlanEditConstraintError(f"Course {course_id} is excluded by this scenario")
    if (
        preference.preference_type == ScenarioPreferenceType.FIX_COURSE_TO_TERM
        and course_id not in completed_ids
        and placements.get(course_id) != preference.term_id
    ):
        raise PlanEditConstraintError(
            f"Course {course_id} is fixed to term {preference.term_id} by this scenario"
        )


def _validate_course_relations(db: Session, plan_courses: list[PlanCourse]) -> None:
    """Reject duplicate/equivalent course pairs that cannot both receive full credit."""
    courses = {row.course_id: row for row in plan_courses}
    if not courses:
        return
    completed_ids = _completed_course_ids(db, plan_courses[0].degree_plan_id)
    all_course_ids = set(courses) | completed_ids
    relations = (
        db.query(CourseRelation)
        .filter(
            CourseRelation.course_id.in_(all_course_ids),
            CourseRelation.related_course_id.in_(all_course_ids),
            CourseRelation.relation_type.in_(
                (
                    CourseRelationType.CROSS_LISTED,
                    CourseRelationType.EQUIVALENT,
                    CourseRelationType.DUPLICATE_CREDIT,
                    CourseRelationType.MUTUALLY_EXCLUSIVE,
                )
            ),
        )
        .all()
    )
    for relation in relations:
        if relation.course_id not in courses and relation.related_course_id not in courses:
            continue
        first = db.get(Course, relation.course_id)
        second = db.get(Course, relation.related_course_id)
        combined = float(first.credit_hours) + float(second.credit_hours)
        maximum = float(relation.maximum_combined_credits) if relation.maximum_combined_credits is not None else 0
        if relation.maximum_combined_credits is None or combined > maximum:
            raise DuplicateCreditError(
                f"Courses {relation.course_id} and {relation.related_course_id} cannot both receive full degree credit."
            )


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
