"""Per-plan requirement coverage: which requirement nodes one already-generated
degree plan satisfies, which remain, and which satisfied leaves are "shared"
(the same course counted toward more than one of the scenario's programs).

Reuses Phase 2's `requirement_service`/`credit_matching_service` almost as-is:
the only new idea is treating a plan's `plan_courses` as additional completed
courses (via `extra_completed_course_ids`) so container-level ALL/ANY/N_OF
rollups work the same way they do for a student's real transcript. "Shared"
is computed separately from the plan's persisted `requirement_allocations`,
since that table already records exactly which course the solver picked for
each COURSE_GROUP leaf -- something a fresh credit-matching pass can't
recover (it only knows a group is satisfied by *some* member).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.scenario_program import ScenarioProgram
from app.models.student_credit import StudentCredit
from app.schemas.course import CourseOut
from app.schemas.requirement import RequirementNodeOut, RequirementSetOut
from app.services import credit_matching_service, requirement_service
from app.services.common import load_courses_by_id


def get_plan_requirement_coverage(db: Session, degree_plan_id: int) -> list[RequirementSetOut] | None:
    """Return every requirement_set behind a plan's scenario, flattened and
    annotated with is_satisfied/is_shared for that specific plan, or None if
    the plan doesn't exist."""
    plan = db.get(DegreePlan, degree_plan_id)
    if plan is None:
        return None
    scenario = db.get(PlanningScenario, plan.planning_scenario_id)
    program_ids = _scenario_program_ids(db, plan.planning_scenario_id)
    plan_course_ids = _plan_course_ids(db, degree_plan_id)
    allocations = _plan_allocations(db, degree_plan_id)
    shared_node_ids = _shared_node_ids(db, program_ids, allocations)
    satisfying_courses = _satisfying_courses_by_node(db, allocations)
    requirement_sets = requirement_service.resolve_requirement_sets(db, program_ids)
    return [
        _coverage_for_requirement_set(
            db,
            scenario.student_id,
            req_set.requirement_set_id,
            plan_course_ids,
            shared_node_ids,
            satisfying_courses,
        )
        for req_set in requirement_sets
    ]


def _coverage_for_requirement_set(
    db: Session,
    student_id: int,
    requirement_set_id: int,
    plan_course_ids: set[int],
    shared_node_ids: set[int],
    satisfying_courses: dict[int, list[CourseOut]],
) -> RequirementSetOut:
    """Return one matched requirement set with sharing and course evidence."""
    flattened = requirement_service.flatten_requirement_tree(db, requirement_set_id)
    matched = credit_matching_service.match_completed_courses(
        db, student_id, flattened, extra_completed_course_ids=plan_course_ids
    )
    marked_nodes = [_annotate_node(node, shared_node_ids, satisfying_courses) for node in matched.nodes]
    return matched.model_copy(update={"nodes": marked_nodes})


def _annotate_node(
    node: RequirementNodeOut,
    shared_node_ids: set[int],
    satisfying_courses: dict[int, list[CourseOut]],
) -> RequirementNodeOut:
    """Recursively attach sharing and satisfying-course evidence to a node."""
    children = [_annotate_node(child, shared_node_ids, satisfying_courses) for child in node.children]
    is_shared = node.requirement_node_id in shared_node_ids
    courses = satisfying_courses.get(node.requirement_node_id, [])
    return node.model_copy(update={"children": children, "is_shared": is_shared, "satisfying_courses": courses})


def _scenario_program_ids(db: Session, planning_scenario_id: int) -> list[int]:
    """Return the academic_program_ids selected for a scenario."""
    rows = (
        db.query(ScenarioProgram.academic_program_id)
        .filter(ScenarioProgram.planning_scenario_id == planning_scenario_id)
        .all()
    )
    return [row[0] for row in rows]


def _plan_course_ids(db: Session, degree_plan_id: int) -> set[int]:
    """Return the distinct course_ids a plan assigns across all its terms."""
    rows = db.query(PlanCourse.course_id).filter(PlanCourse.degree_plan_id == degree_plan_id).all()
    return {row[0] for row in rows}


def _plan_allocations(db: Session, degree_plan_id: int) -> list[RequirementAllocation]:
    """Return every persisted requirement allocation for a plan."""
    return db.query(RequirementAllocation).filter(RequirementAllocation.degree_plan_id == degree_plan_id).all()


def _shared_node_ids(
    db: Session, program_ids: list[int], allocations: list[RequirementAllocation]
) -> set[int]:
    """Return requirement_node_ids whose persisted allocation's satisfying
    course is also allocated (for this same plan) to a node belonging to a
    *different* one of the scenario's programs."""
    if not allocations:
        return set()
    node_to_set = _node_to_requirement_set(db, {a.requirement_node_id for a in allocations})
    set_to_programs = _requirement_set_to_programs(db, program_ids)
    course_by_allocation = _course_id_by_allocation(db, allocations)
    programs_by_course = _programs_touched_by_course(allocations, node_to_set, set_to_programs, course_by_allocation)
    shared_courses = {course_id for course_id, programs in programs_by_course.items() if len(programs) > 1}
    return {
        allocation.requirement_node_id
        for allocation in allocations
        if course_by_allocation.get(allocation.requirement_allocation_id) in shared_courses
    }


def _satisfying_courses_by_node(
    db: Session, allocations: list[RequirementAllocation]
) -> dict[int, list[CourseOut]]:
    """Map each allocated requirement node to its concrete satisfying courses."""
    course_by_allocation = _course_id_by_allocation(db, allocations)
    course_ids_by_node: dict[int, set[int]] = {}
    for allocation in allocations:
        course_id = course_by_allocation.get(allocation.requirement_allocation_id)
        if course_id is not None:
            course_ids_by_node.setdefault(allocation.requirement_node_id, set()).add(course_id)
    courses_by_id = load_courses_by_id(db, set(course_by_allocation.values()))
    return {
        node_id: sorted(
            (courses_by_id[course_id] for course_id in course_ids if course_id in courses_by_id),
            key=lambda course: (course.subject_code, course.course_number),
        )
        for node_id, course_ids in course_ids_by_node.items()
    }


def _node_to_requirement_set(db: Session, node_ids: set[int]) -> dict[int, int]:
    """Map requirement_node_id -> requirement_set_id for the given nodes."""
    rows = (
        db.query(RequirementNode.requirement_node_id, RequirementNode.requirement_set_id)
        .filter(RequirementNode.requirement_node_id.in_(node_ids))
        .all()
    )
    return dict(rows)


def _requirement_set_to_programs(db: Session, program_ids: list[int]) -> dict[int, set[int]]:
    """Map requirement_set_id -> the subset of `program_ids` linked to it."""
    if not program_ids:
        return {}
    rows = (
        db.query(ProgramRequirementSet.requirement_set_id, ProgramRequirementSet.academic_program_id)
        .filter(ProgramRequirementSet.academic_program_id.in_(program_ids))
        .all()
    )
    result: dict[int, set[int]] = {}
    for requirement_set_id, program_id in rows:
        result.setdefault(requirement_set_id, set()).add(program_id)
    return result


def _course_id_by_allocation(db: Session, allocations: list[RequirementAllocation]) -> dict[int, int]:
    """Map requirement_allocation_id -> the course_id it actually resolves to,
    via whichever of plan_course_id/student_credit_id is set."""
    plan_course_ids = {a.plan_course_id for a in allocations if a.plan_course_id is not None}
    student_credit_ids = {a.student_credit_id for a in allocations if a.student_credit_id is not None}
    course_by_plan_course = _course_ids_by_id(db, PlanCourse, PlanCourse.plan_course_id, plan_course_ids)
    course_by_student_credit = _course_ids_by_id(db, StudentCredit, StudentCredit.student_credit_id, student_credit_ids)
    result: dict[int, int] = {}
    for allocation in allocations:
        course_id = None
        if allocation.plan_course_id is not None:
            course_id = course_by_plan_course.get(allocation.plan_course_id)
        elif allocation.student_credit_id is not None:
            course_id = course_by_student_credit.get(allocation.student_credit_id)
        if course_id is not None:
            result[allocation.requirement_allocation_id] = course_id
    return result


def _course_ids_by_id(
    db: Session, model: type[PlanCourse] | type[StudentCredit], id_column, ids: set[int]
) -> dict[int, int]:
    """Fetch `model.course_id` for the given primary-key ids, keyed by that id."""
    if not ids:
        return {}
    rows = db.query(id_column, model.course_id).filter(id_column.in_(ids)).all()
    return dict(rows)


def _programs_touched_by_course(
    allocations: list[RequirementAllocation],
    node_to_set: dict[int, int],
    set_to_programs: dict[int, set[int]],
    course_by_allocation: dict[int, int],
) -> dict[int, set[int]]:
    """Map courses to exclusive program owners, ignoring inherited/common sets."""
    result: dict[int, set[int]] = {}
    for allocation in allocations:
        course_id = course_by_allocation.get(allocation.requirement_allocation_id)
        if course_id is None:
            continue
        requirement_set_id = node_to_set.get(allocation.requirement_node_id)
        programs = set_to_programs.get(requirement_set_id, set())
        if len(programs) == 1:
            result.setdefault(course_id, set()).update(programs)
    return result
