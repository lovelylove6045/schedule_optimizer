"""Builds the solver's candidate course universe for one planning scenario:
every course its resolved requirement trees could assign (including
course_group alternatives), plus their prerequisite/corequisite closure via
`course_rule_nodes`, minus whatever the student already completed."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.academic_program import AcademicProgram
from app.models.course import Course
from app.models.course_group_member import CourseGroupMember
from app.models.course_rule_node import CourseRuleNode
from app.models.enums import RequisiteType, ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.scenario_program import ScenarioProgram
from app.models.student_credit import StudentCredit
from app.schemas.course import CourseOut
from app.schemas.requirement import RequirementNodeOut, RequirementSetOut
from app.services import credit_matching_service, requirement_service
from app.services.common import load_courses_by_id
from app.services.credit_matching_service import COMPLETED_STATUS

# Safety valve on prerequisite-closure growth, not a modeling decision. The
# original value (60) was set before the closure was measured against the full
# catalog and turned out to bind on ordinary scenarios: Aerospace BS alone wants
# 88 extra courses over 3 levels, so every generated plan came back carrying
# ~24 "a prerequisite was excluded by the closure growth cap" warnings. The whole
# prerequisite graph is only 4,777 `course_rule_nodes` rows over 2,120 courses,
# so a cap in the hundreds still bounds a pathological expansion (the
# same-or-above-level language/biology ladder in db/SUMMARY.md §3a) while never
# firing on a real degree program.
MAX_CLOSURE_GROWTH = 500
_CLOSURE_REQUISITE_TYPES = (
    RequisiteType.PREREQUISITE,
    RequisiteType.COREQUISITE,
    RequisiteType.PRE_OR_COREQUISITE,
)
# A minor/emphasis doesn't have its own "total credits to graduate" -- it just
# adds specific coursework on top of a bachelor's degree, already enforced via
# the requirement-node constraints. Only a MAJOR-level program's own published
# total is a real graduation floor.
_CREDIT_FLOOR_ROLES = (ScenarioProgramRole.PRIMARY_MAJOR, ScenarioProgramRole.SECOND_MAJOR)


@dataclass(frozen=True)
class CandidateCourseSet:
    """The full solver input derived from one scenario: its requirement
    trees (already flattened and credit-matched), which courses are open
    decision variables, which are already completed, and whether the
    prerequisite-closure growth cap was hit while building it."""

    requirement_sets: list[RequirementSetOut]
    assignable_course_ids: set[int]
    completed_course_ids: set[int]
    courses_by_id: dict[int, CourseOut]
    group_members: dict[int, set[int]]
    course_ids_by_program: dict[int, set[int]]
    closure_capped: bool
    # credit_hours for every course_group member, including ones already completed
    # (and so absent from `courses_by_id`, which only holds assignable courses).
    # `optimizer_model` needs these to enforce a group's required_credit_hours.
    credit_hours_by_course_id: dict[int, float]
    # How many more credit hours (beyond what's already completed) the scenario's
    # major(s) officially require to graduate, or None if no program in scope has
    # a published total_credit_hours. `optimizer_model` only enforces this as a
    # hard floor when the scenario opted in (see enforce_program_credit_minimum).
    credit_floor_remaining: float | None
    # The student's total earned credit hours so far (transfer + completed
    # coursework), independent of this scenario's own requirement trees.
    # `optimizer_model` adds each term's newly-assigned credits on top of this to
    # approximate class standing for STANDING/SUBJECT_LEVEL prerequisite leaves.
    completed_credit_hours: float


def build_candidate_course_set(
    db: Session, scenario: PlanningScenario, program_ids_override: list[int] | None = None
) -> CandidateCourseSet:
    """Build the candidate course universe for a scenario, ready to hand to `optimizer_model`.
    `program_ids_override` lets `optimizer_service` build a 'primary major alone' baseline
    without the scenario's other scenario_programs rows."""
    program_ids = (
        program_ids_override
        if program_ids_override is not None
        else _resolve_scenario_program_ids(db, scenario.planning_scenario_id)
    )
    requirement_sets = _collect_requirement_sets(db, program_ids, scenario.student_id)
    completed_course_ids = _collect_completed_course_ids(db, scenario.student_id)
    group_ids = _collect_course_group_ids(requirement_sets)
    group_members = _load_group_members(db, group_ids)
    course_ids_by_requirement_set = _index_course_ids_by_requirement_set(requirement_sets, group_members)
    course_ids_by_program = _index_course_ids_by_program(
        db, program_ids, course_ids_by_requirement_set
    )
    direct_course_ids: set[int] = set()
    for course_ids in course_ids_by_requirement_set.values():
        direct_course_ids |= course_ids
    assignable_course_ids, closure_capped = _expand_prerequisite_closure(
        db, direct_course_ids, completed_course_ids
    )
    courses_by_id = load_courses_by_id(db, assignable_course_ids)
    completed_credit_hours = _completed_credit_hours_total(db, scenario.student_id)
    return CandidateCourseSet(
        requirement_sets=requirement_sets,
        assignable_course_ids=assignable_course_ids,
        completed_course_ids=completed_course_ids,
        courses_by_id=courses_by_id,
        group_members=group_members,
        course_ids_by_program=course_ids_by_program,
        closure_capped=closure_capped,
        credit_hours_by_course_id=_load_credit_hours(db, group_members, courses_by_id),
        credit_floor_remaining=_resolve_credit_floor_remaining(
            db, scenario, program_ids, completed_credit_hours
        ),
        completed_credit_hours=completed_credit_hours,
    )


def _resolve_credit_floor_remaining(
    db: Session, scenario: PlanningScenario, program_ids: list[int], completed_credit_hours: float
) -> float | None:
    """Return how many more credit hours the scenario's in-scope MAJOR-role
    program(s) require beyond what the student has already earned, or None if
    none of them has a published total_credit_hours to compare against."""
    target = _resolve_credit_floor_target(db, scenario.planning_scenario_id, program_ids)
    if target is None:
        return None
    return max(target - completed_credit_hours, 0.0)


def _resolve_credit_floor_target(db: Session, planning_scenario_id: int, program_ids: list[int]) -> float | None:
    """Return the highest published total_credit_hours among this scenario's
    MAJOR-role programs (restricted to `program_ids`, so the 'primary major
    alone' baseline solve sees only that program's own total) -- the credit
    floor a bachelor's degree already requires no matter how many majors are
    combined with it."""
    if not program_ids:
        return None
    rows = (
        db.query(AcademicProgram.total_credit_hours)
        .join(ScenarioProgram, ScenarioProgram.academic_program_id == AcademicProgram.academic_program_id)
        .filter(
            ScenarioProgram.planning_scenario_id == planning_scenario_id,
            ScenarioProgram.academic_program_id.in_(program_ids),
            ScenarioProgram.program_role.in_(_CREDIT_FLOOR_ROLES),
            AcademicProgram.total_credit_hours.isnot(None),
        )
        .all()
    )
    totals = [float(total) for (total,) in rows if total is not None]
    return max(totals) if totals else None


def _completed_credit_hours_total(db: Session, student_id: int) -> float:
    """Return a student's total earned credit hours across every COMPLETED
    student_credits row, falling back to the catalog's credit_hours for an
    institutional course reported without its own explicit credits_earned."""
    rows = (
        db.query(StudentCredit.credits_earned, Course.credit_hours)
        .outerjoin(Course, StudentCredit.course_id == Course.course_id)
        .filter(StudentCredit.student_id == student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    return sum(float(credits_earned if credits_earned is not None else (catalog_hours or 0)) for credits_earned, catalog_hours in rows)


def _load_credit_hours(
    db: Session, group_members: dict[int, set[int]], courses_by_id: dict[int, CourseOut]
) -> dict[int, float]:
    """Return credit_hours for every assignable course plus every course_group member,
    keyed by course_id. Group members already completed by the student aren't assignable
    and so aren't in `courses_by_id`, but their credits still count toward a group's
    required_credit_hours -- so they're fetched here in one extra query."""
    credit_hours = {course_id: course.credit_hours for course_id, course in courses_by_id.items()}
    member_ids = {course_id for members in group_members.values() for course_id in members}
    missing_ids = member_ids - credit_hours.keys()
    if missing_ids:
        rows = db.query(Course.course_id, Course.credit_hours).filter(Course.course_id.in_(missing_ids)).all()
        credit_hours.update({course_id: float(hours) for course_id, hours in rows})
    return credit_hours


def _resolve_scenario_program_ids(db: Session, planning_scenario_id: int) -> list[int]:
    """Return every academic_program_id selected for this scenario (primary major + any goals)."""
    rows = (
        db.query(ScenarioProgram.academic_program_id)
        .filter(ScenarioProgram.planning_scenario_id == planning_scenario_id)
        .all()
    )
    return [program_id for (program_id,) in rows]


def _collect_requirement_sets(
    db: Session, program_ids: list[int], student_id: int
) -> list[RequirementSetOut]:
    """Resolve, flatten, and credit-match every requirement set attached to the given programs."""
    requirement_sets = requirement_service.resolve_requirement_sets(db, program_ids)
    flattened = [
        requirement_service.flatten_requirement_tree(db, req_set.requirement_set_id)
        for req_set in requirement_sets
    ]
    return [
        credit_matching_service.match_completed_courses(db, student_id, req_set)
        for req_set in flattened
        if req_set is not None
    ]


def _index_course_ids_by_requirement_set(
    requirement_sets: list[RequirementSetOut], group_members: dict[int, set[int]]
) -> dict[int, set[int]]:
    """Return each requirement set's referenced course ids (COURSE leaves plus
    COURSE_GROUP members), keyed by requirement_set_id."""
    result: dict[int, set[int]] = {}
    for req_set in requirement_sets:
        course_ids = _collect_course_ids_from_nodes(req_set.nodes)
        for group_id in _collect_group_ids_from_nodes(req_set.nodes):
            course_ids |= group_members.get(group_id, set())
        result[req_set.requirement_set_id] = course_ids
    return result


def _index_course_ids_by_program(
    db: Session, program_ids: list[int], course_ids_by_requirement_set: dict[int, set[int]]
) -> dict[int, set[int]]:
    """Return each program's referenced course ids (union across all its own requirement
    sets), keyed by academic_program_id -- the signal `optimizer_objectives` uses to detect
    genuine cross-PROGRAM double counting (UC-15), as distinct from a single program's own
    multiple requirement sets (core/gen-ed/electives) naturally sharing a course."""
    requirement_set_ids_by_program = _load_requirement_set_ids_by_program(db, program_ids)
    result: dict[int, set[int]] = {}
    for program_id in program_ids:
        course_ids: set[int] = set()
        for requirement_set_id in requirement_set_ids_by_program.get(program_id, set()):
            course_ids |= course_ids_by_requirement_set.get(requirement_set_id, set())
        result[program_id] = course_ids
    return result


def _load_requirement_set_ids_by_program(db: Session, program_ids: list[int]) -> dict[int, set[int]]:
    """Return each program's linked requirement_set ids, keyed by academic_program_id."""
    if not program_ids:
        return {}
    rows = (
        db.query(ProgramRequirementSet.academic_program_id, ProgramRequirementSet.requirement_set_id)
        .filter(ProgramRequirementSet.academic_program_id.in_(program_ids))
        .all()
    )
    result: dict[int, set[int]] = {}
    for program_id, requirement_set_id in rows:
        result.setdefault(program_id, set()).add(requirement_set_id)
    return result


def _collect_course_ids_from_nodes(nodes: list[RequirementNodeOut]) -> set[int]:
    """Recursively collect required_course ids from requirement nodes and their children."""
    course_ids: set[int] = set()
    for node in nodes:
        if node.required_course is not None:
            course_ids.add(node.required_course.course_id)
        course_ids |= _collect_course_ids_from_nodes(node.children)
    return course_ids


def _collect_course_group_ids(requirement_sets: list[RequirementSetOut]) -> set[int]:
    """Recursively collect every course_group id referenced across all given requirement trees."""
    group_ids: set[int] = set()
    for req_set in requirement_sets:
        group_ids |= _collect_group_ids_from_nodes(req_set.nodes)
    return group_ids


def _collect_group_ids_from_nodes(nodes: list[RequirementNodeOut]) -> set[int]:
    """Recursively collect course_group ids from requirement nodes and their children."""
    group_ids: set[int] = set()
    for node in nodes:
        if node.course_group is not None:
            group_ids.add(node.course_group.course_group_id)
        group_ids |= _collect_group_ids_from_nodes(node.children)
    return group_ids


def _load_group_members(db: Session, course_group_ids: set[int]) -> dict[int, set[int]]:
    """Return each course group's member course ids, keyed by course_group_id."""
    if not course_group_ids:
        return {}
    rows = (
        db.query(CourseGroupMember.course_group_id, CourseGroupMember.course_id)
        .filter(CourseGroupMember.course_group_id.in_(course_group_ids))
        .all()
    )
    members: dict[int, set[int]] = {}
    for group_id, course_id in rows:
        members.setdefault(group_id, set()).add(course_id)
    return members


def _collect_completed_course_ids(db: Session, student_id: int) -> set[int]:
    """Return course ids the student has already completed (status COMPLETED, real course only)."""
    rows = (
        db.query(StudentCredit.course_id)
        .filter(StudentCredit.student_id == student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    return {course_id for (course_id,) in rows if course_id is not None}


def _expand_prerequisite_closure(
    db: Session, course_ids: set[int], completed_course_ids: set[int]
) -> tuple[set[int], bool]:
    """Breadth-first expand `course_ids` to include their PREREQUISITE/COREQUISITE
    chains via course_rule_nodes, capped at MAX_CLOSURE_GROWTH additional courses so
    a loosely-linked cluster (e.g. the same-or-above-level language ladder documented
    in db/SUMMARY.md) can't balloon the candidate set. When the cap does bind, the
    truncation is taken in sorted id order so the same scenario always produces the
    same candidate set (iterating a `set` directly made it depend on hash ordering)."""
    visited = set(course_ids) - completed_course_ids
    frontier = set(visited)
    growth = 0
    capped = False
    while frontier and growth < MAX_CLOSURE_GROWTH:
        next_ids = _direct_prerequisite_course_ids(db, frontier) - completed_course_ids - visited
        if not next_ids:
            break
        if growth + len(next_ids) > MAX_CLOSURE_GROWTH:
            next_ids = set(sorted(next_ids)[: MAX_CLOSURE_GROWTH - growth])
            capped = True
        visited |= next_ids
        growth += len(next_ids)
        frontier = next_ids
    return visited, capped


def _direct_prerequisite_course_ids(db: Session, course_ids: set[int]) -> set[int]:
    """Return course ids directly required as a PREREQUISITE/COREQUISITE/PRE_OR_COREQUISITE
    of any of the given target courses."""
    rows = (
        db.query(CourseRuleNode.required_course_id)
        .filter(
            CourseRuleNode.target_course_id.in_(course_ids),
            CourseRuleNode.requisite_type.in_(_CLOSURE_REQUISITE_TYPES),
            CourseRuleNode.required_course_id.isnot(None),
        )
        .all()
    )
    return {course_id for (course_id,) in rows}
