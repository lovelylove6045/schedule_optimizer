"""Tests plan_requirement_service against hand-built plan fixtures (no solver
run needed): is_satisfied from a plan's own plan_courses, and is_shared from
requirement_allocations spanning two of the scenario's programs."""

from app.models.degree_plan import DegreePlan
from app.models.enums import ScenarioProgramRole
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.requirement_allocation import RequirementAllocation
from app.models.scenario_program import ScenarioProgram
from app.models.student import Student
from app.services import plan_requirement_service

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2
COMP_SCI_1972_COURSE_ID = 1122  # real Aero BS requirement course, also usable by the minor
AERO_BS_COURSE_NODE_ID = 2  # a real COURSE leaf under one of AERO_BS's requirement_sets
AERO_MINOR_COURSE_NODE_ID = 80  # a real COURSE leaf under AERO_MINOR's requirement_set


def _make_scenario(db_session, program_ids: list[int]) -> PlanningScenario:
    """Create a minimal scenario with the given programs for a fresh student."""
    student = Student(display_name="Coverage Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id)
    db_session.add(scenario)
    db_session.flush()
    for index, program_id in enumerate(program_ids):
        role = ScenarioProgramRole.PRIMARY_MAJOR if index == 0 else ScenarioProgramRole.MINOR
        db_session.add(
            ScenarioProgram(planning_scenario_id=scenario.planning_scenario_id, academic_program_id=program_id, program_role=role)
        )
    db_session.flush()
    return scenario


def _make_plan(db_session, scenario: PlanningScenario) -> DegreePlan:
    """Persist a bare DegreePlan row for `scenario`."""
    plan = DegreePlan(planning_scenario_id=scenario.planning_scenario_id, status="DRAFT")
    db_session.add(plan)
    db_session.flush()
    return plan


def test_get_plan_requirement_coverage_404_for_missing_plan(db_session):
    assert plan_requirement_service.get_plan_requirement_coverage(db_session, 999_999) is None


def test_marks_satisfied_from_plan_courses(db_session):
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])
    plan = _make_plan(db_session, scenario)
    db_session.add(
        PlanCourse(degree_plan_id=plan.degree_plan_id, course_id=COMP_SCI_1972_COURSE_ID, term_id=1, credit_hours=3)
    )
    db_session.flush()

    coverage = plan_requirement_service.get_plan_requirement_coverage(db_session, plan.degree_plan_id)

    satisfied_course_ids = _satisfied_course_ids(coverage)
    assert COMP_SCI_1972_COURSE_ID in satisfied_course_ids


def test_marks_shared_from_cross_program_allocations(db_session):
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID, AERO_MINOR_PROGRAM_ID])
    plan = _make_plan(db_session, scenario)
    plan_course = PlanCourse(
        degree_plan_id=plan.degree_plan_id, course_id=COMP_SCI_1972_COURSE_ID, term_id=1, credit_hours=3
    )
    db_session.add(plan_course)
    db_session.flush()
    db_session.add_all(
        [
            RequirementAllocation(
                degree_plan_id=plan.degree_plan_id,
                requirement_node_id=AERO_BS_COURSE_NODE_ID,
                plan_course_id=plan_course.plan_course_id,
            ),
            RequirementAllocation(
                degree_plan_id=plan.degree_plan_id,
                requirement_node_id=AERO_MINOR_COURSE_NODE_ID,
                plan_course_id=plan_course.plan_course_id,
            ),
        ]
    )
    db_session.flush()

    coverage = plan_requirement_service.get_plan_requirement_coverage(db_session, plan.degree_plan_id)

    shared_node_ids = _all_node_ids(coverage, only_shared=True)
    assert {AERO_BS_COURSE_NODE_ID, AERO_MINOR_COURSE_NODE_ID}.issubset(shared_node_ids)


def test_no_shared_nodes_for_a_single_program_scenario(db_session):
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])
    plan = _make_plan(db_session, scenario)
    plan_course = PlanCourse(
        degree_plan_id=plan.degree_plan_id, course_id=COMP_SCI_1972_COURSE_ID, term_id=1, credit_hours=3
    )
    db_session.add(plan_course)
    db_session.flush()
    db_session.add(
        RequirementAllocation(
            degree_plan_id=plan.degree_plan_id, requirement_node_id=AERO_BS_COURSE_NODE_ID, plan_course_id=plan_course.plan_course_id
        )
    )
    db_session.flush()

    coverage = plan_requirement_service.get_plan_requirement_coverage(db_session, plan.degree_plan_id)

    assert _all_node_ids(coverage, only_shared=True) == set()


def _satisfied_course_ids(coverage) -> set[int]:
    """Collect every satisfied leaf's required_course.course_id across all requirement sets."""
    result: set[int] = set()
    for req_set in coverage:
        _collect_satisfied_course_ids(req_set.nodes, result)
    return result


def _collect_satisfied_course_ids(nodes, result: set[int]) -> None:
    """Recursively add satisfied COURSE leaves' course ids into `result`."""
    for node in nodes:
        if node.is_satisfied and node.required_course is not None:
            result.add(node.required_course.course_id)
        _collect_satisfied_course_ids(node.children, result)


def _all_node_ids(coverage, only_shared: bool = False) -> set[int]:
    """Collect requirement_node_ids across all requirement sets, optionally only shared ones."""
    result: set[int] = set()
    for req_set in coverage:
        _collect_node_ids(req_set.nodes, result, only_shared)
    return result


def _collect_node_ids(nodes, result: set[int], only_shared: bool) -> None:
    """Recursively add node ids into `result`, filtering to is_shared ones if requested."""
    for node in nodes:
        if not only_shared or node.is_shared:
            result.add(node.requirement_node_id)
        _collect_node_ids(node.children, result, only_shared)
