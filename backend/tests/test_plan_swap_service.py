"""Tests plan_swap_service against hand-built plan fixtures: swapping,
adding, and removing all update `plan_courses`/credit totals correctly, keep
`requirement_allocations` in sync (or clean them up on removal), and reject
an unknown plan/plan_course/term/course or a duplicate course.

Uses fall-offered, prerequisite-free courses throughout so these tests stay
about the edit mechanics themselves, not `plan_swap_validation`'s offering/
credit/prerequisite checks (which have their own dedicated tests)."""

import pytest

from app.models.academic_program import AcademicProgram
from app.models.course import Course
from app.models.course_group import CourseGroup
from app.models.course_group_member import CourseGroupMember
from app.models.course_rule_node import CourseRuleNode
from app.models.degree_plan import DegreePlan
from app.models.enums import ProgramType, ScenarioProgramRole
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.requirement_set import RequirementSet
from app.models.scenario_program import ScenarioProgram
from app.models.student import Student
from app.services import (
    optimizer_persistence,
    plan_swap_service,
    plan_swap_validation,
    plan_validation_service,
)

FALL_2026_TERM_ID = 1
SPRING_2027_TERM_ID = 2
FALL_2027_TERM_ID = 4
FALL_2028_TERM_ID = 7
PSYCH_GENERAL_COURSE_ID = 839
PSYCH_GENDER_COURSE_ID = 874


def _n_real_course_ids(db_session, count: int) -> list[int]:
    """Return `count` real, fall-offered course_ids that have no prerequisites
    of their own, so `plan_swap_validation`'s checks always pass for them
    regardless of the bare test plan's (empty) placements."""
    prereq_target_ids = db_session.query(CourseRuleNode.target_course_id).distinct().subquery()
    rows = (
        db_session.query(Course.course_id)
        .filter(Course.fall_offered.is_(True))
        .filter(~Course.course_id.in_(db_session.query(prereq_target_ids.c.target_course_id)))
        .order_by(Course.course_id.asc())
        .limit(count)
        .all()
    )
    return [row[0] for row in rows]


def _two_real_course_ids(db_session) -> tuple[int, int]:
    """Return two real, fall-offered, prerequisite-free course_ids (see `_n_real_course_ids`)."""
    first_id, second_id = _n_real_course_ids(db_session, 2)
    return first_id, second_id


def _make_plan_with_one_course(db_session, course_id: int) -> tuple[DegreePlan, PlanCourse]:
    """Persist a minimal one-course plan for `course_id`, with a requirement_allocation
    pointing at a freshly created node, for testing the swap service."""
    student = Student(display_name="Swap Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id)
    db_session.add(scenario)
    db_session.flush()
    course = db_session.get(Course, course_id)
    plan = DegreePlan(
        planning_scenario_id=scenario.planning_scenario_id,
        status="DRAFT",
        total_credit_hours=course.credit_hours,
        additional_credit_hours=course.credit_hours,
    )
    db_session.add(plan)
    db_session.flush()
    plan_course = PlanCourse(
        degree_plan_id=plan.degree_plan_id, course_id=course_id, term_id=FALL_2026_TERM_ID, credit_hours=course.credit_hours
    )
    db_session.add(plan_course)
    db_session.flush()
    req_set = RequirementSet(requirement_set_code="SWAP-TEST", requirement_set_name="Swap Test", requirement_set_type="CORE")
    db_session.add(req_set)
    db_session.flush()
    node = RequirementNode(requirement_set_id=req_set.requirement_set_id, node_type="COURSE", required_course_id=course_id)
    db_session.add(node)
    db_session.flush()
    db_session.add(
        RequirementAllocation(
            degree_plan_id=plan.degree_plan_id,
            requirement_node_id=node.requirement_node_id,
            plan_course_id=plan_course.plan_course_id,
            credit_hours_applied=course.credit_hours,
        )
    )
    db_session.flush()
    return plan, plan_course


def _link_plan_requirement_to_scratch_major(db_session, plan: DegreePlan) -> RequirementNode:
    """Attach the fixture requirement to a selected scratch major for full validation."""
    allocation = db_session.query(RequirementAllocation).filter(
        RequirementAllocation.degree_plan_id == plan.degree_plan_id
    ).one()
    node = db_session.get(RequirementNode, allocation.requirement_node_id)
    program = AcademicProgram(
        department_id=1,
        program_code="EDIT_VALIDATION_MAJOR",
        program_name="Edit Validation Major",
        program_type=ProgramType.MAJOR,
        total_credit_hours=0,
    )
    db_session.add(program)
    db_session.flush()
    db_session.add(
        ProgramRequirementSet(
            academic_program_id=program.academic_program_id,
            requirement_set_id=node.requirement_set_id,
            display_order=1,
        )
    )
    db_session.add(
        ScenarioProgram(
            planning_scenario_id=plan.planning_scenario_id,
            academic_program_id=program.academic_program_id,
            program_role=ScenarioProgramRole.PRIMARY_MAJOR,
        )
    )
    scenario = db_session.get(PlanningScenario, plan.planning_scenario_id)
    scenario.start_term_id = FALL_2026_TERM_ID
    scenario.default_minimum_credits = 0
    scenario.default_maximum_credits = 18
    scenario.enforce_program_credit_minimum = False
    db_session.flush()
    return node


def test_swap_plan_course_updates_the_course_and_credit_hours(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)
    new_course = db_session.get(Course, second_id)

    updated = plan_swap_service.swap_plan_course(db_session, plan.degree_plan_id, plan_course.plan_course_id, second_id)

    db_session.refresh(plan_course)
    assert plan_course.course_id == second_id
    assert float(plan_course.credit_hours) == float(new_course.credit_hours)
    assert plan_course.placement_source == "STUDENT_SWAP"
    assert updated.degree_plan_id == plan.degree_plan_id


def test_swap_plan_course_keeps_credit_totals_and_allocations_in_sync(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)
    old_credits = float(plan_course.credit_hours)
    new_course = db_session.get(Course, second_id)

    plan_swap_service.swap_plan_course(db_session, plan.degree_plan_id, plan_course.plan_course_id, second_id)

    db_session.refresh(plan)
    delta = float(new_course.credit_hours) - old_credits
    assert float(plan.total_credit_hours) == pytest.approx(old_credits + delta)
    allocation = (
        db_session.query(RequirementAllocation)
        .filter(RequirementAllocation.plan_course_id == plan_course.plan_course_id)
        .one()
    )
    assert float(allocation.credit_hours_applied) == float(new_course.credit_hours)


def test_swap_plan_course_404_for_unknown_plan_course(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    plan, _ = _make_plan_with_one_course(db_session, first_id)

    with pytest.raises(plan_swap_service.PlanCourseNotFoundError):
        plan_swap_service.swap_plan_course(db_session, plan.degree_plan_id, 999_999, second_id)


def test_swap_plan_course_422_for_unknown_new_course(db_session):
    first_id, _ = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)

    with pytest.raises(plan_swap_service.CourseNotFoundError):
        plan_swap_service.swap_plan_course(db_session, plan.degree_plan_id, plan_course.plan_course_id, 999_999)


def test_swap_plan_course_422_when_the_new_course_is_already_in_the_plan(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)
    other_course = db_session.get(Course, second_id)
    db_session.add(
        PlanCourse(
            degree_plan_id=plan.degree_plan_id,
            course_id=second_id,
            term_id=FALL_2026_TERM_ID,
            credit_hours=other_course.credit_hours,
        )
    )
    db_session.flush()

    with pytest.raises(plan_swap_service.DuplicateCourseError):
        plan_swap_service.swap_plan_course(db_session, plan.degree_plan_id, plan_course.plan_course_id, second_id)


def test_add_plan_course_creates_a_new_slot_and_updates_credit_totals(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    plan, _ = _make_plan_with_one_course(db_session, first_id)
    old_total = float(plan.total_credit_hours)
    new_course = db_session.get(Course, second_id)

    updated = plan_swap_service.add_plan_course(db_session, plan.degree_plan_id, second_id, FALL_2026_TERM_ID)

    added = (
        db_session.query(PlanCourse)
        .filter(PlanCourse.degree_plan_id == plan.degree_plan_id, PlanCourse.course_id == second_id)
        .one()
    )
    assert added.term_id == FALL_2026_TERM_ID
    assert added.placement_source == "STUDENT_ADDED"
    assert float(updated.total_credit_hours) == pytest.approx(old_total + float(new_course.credit_hours))


def test_add_plan_course_404_for_unknown_plan(db_session):
    (course_id,) = _n_real_course_ids(db_session, 1)

    with pytest.raises(plan_swap_service.DegreePlanNotFoundError):
        plan_swap_service.add_plan_course(db_session, 999_999, course_id, FALL_2026_TERM_ID)


def test_add_plan_course_404_for_unknown_term(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    plan, _ = _make_plan_with_one_course(db_session, first_id)

    with pytest.raises(plan_swap_service.TermNotFoundError):
        plan_swap_service.add_plan_course(db_session, plan.degree_plan_id, second_id, 999_999)


def test_add_plan_course_422_for_unknown_course(db_session):
    (first_id,) = _n_real_course_ids(db_session, 1)
    plan, _ = _make_plan_with_one_course(db_session, first_id)

    with pytest.raises(plan_swap_service.CourseNotFoundError):
        plan_swap_service.add_plan_course(db_session, plan.degree_plan_id, 999_999, FALL_2026_TERM_ID)


def test_add_plan_course_422_when_the_course_is_already_in_the_plan(db_session):
    first_id, _ = _two_real_course_ids(db_session)
    plan, _ = _make_plan_with_one_course(db_session, first_id)

    with pytest.raises(plan_swap_service.DuplicateCourseError):
        plan_swap_service.add_plan_course(db_session, plan.degree_plan_id, first_id, FALL_2026_TERM_ID)


def test_remove_plan_course_deletes_the_row_its_allocations_and_updates_credit_totals(db_session):
    first_id, _ = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)

    updated = plan_swap_service.remove_plan_course(db_session, plan.degree_plan_id, plan_course.plan_course_id)

    assert db_session.get(PlanCourse, plan_course.plan_course_id) is None
    remaining_allocations = (
        db_session.query(RequirementAllocation)
        .filter(RequirementAllocation.plan_course_id == plan_course.plan_course_id)
        .count()
    )
    assert remaining_allocations == 0
    # The fixture plan had exactly this one course, so removing it should zero out the total.
    assert float(updated.total_credit_hours) == pytest.approx(0.0)


def test_remove_plan_course_404_for_unknown_plan_course(db_session):
    first_id, _ = _two_real_course_ids(db_session)
    plan, _ = _make_plan_with_one_course(db_session, first_id)

    with pytest.raises(plan_swap_service.PlanCourseNotFoundError):
        plan_swap_service.remove_plan_course(db_session, plan.degree_plan_id, 999_999)


def test_move_plan_course_accepts_a_valid_new_term(db_session):
    """Move a prerequisite course while it remains before its dependent course."""
    plan, prerequisite = _make_plan_with_one_course(db_session, PSYCH_GENERAL_COURSE_ID)
    dependent = db_session.get(Course, PSYCH_GENDER_COURSE_ID)
    db_session.add(
        PlanCourse(
            degree_plan_id=plan.degree_plan_id,
            course_id=dependent.course_id,
            term_id=FALL_2027_TERM_ID,
            credit_hours=dependent.credit_hours,
        )
    )
    db_session.flush()
    updated = plan_swap_service.move_plan_course(
        db_session, plan.degree_plan_id, prerequisite.plan_course_id, SPRING_2027_TERM_ID
    )
    db_session.refresh(prerequisite)
    assert updated.degree_plan_id == plan.degree_plan_id
    assert prerequisite.term_id == SPRING_2027_TERM_ID


def test_move_plan_course_rejects_breaking_a_downstream_prerequisite(db_session):
    """Reject moving a prerequisite after a dependent already scheduled in the plan."""
    plan, prerequisite = _make_plan_with_one_course(db_session, PSYCH_GENERAL_COURSE_ID)
    dependent = db_session.get(Course, PSYCH_GENDER_COURSE_ID)
    db_session.add(
        PlanCourse(
            degree_plan_id=plan.degree_plan_id,
            course_id=dependent.course_id,
            term_id=FALL_2027_TERM_ID,
            credit_hours=dependent.credit_hours,
        )
    )
    db_session.flush()
    with pytest.raises(plan_swap_validation.PrerequisiteNotMetError):
        plan_swap_service.move_plan_course(
            db_session, plan.degree_plan_id, prerequisite.plan_course_id, FALL_2028_TERM_ID
        )


def test_remove_plan_course_rejects_the_only_mandatory_requirement_course(db_session):
    """Roll back removal when the course is the only direct requirement satisfaction."""
    first_id, _ = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)
    _link_plan_requirement_to_scratch_major(db_session, plan)
    with pytest.raises(plan_validation_service.PlanAcademicValidationError):
        plan_swap_service.remove_plan_course(
            db_session, plan.degree_plan_id, plan_course.plan_course_id
        )
    assert db_session.get(PlanCourse, plan_course.plan_course_id) is not None


def test_swap_plan_course_rejects_an_unrelated_replacement(db_session):
    """Roll back a swap that cannot satisfy the original program requirement."""
    first_id, second_id = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)
    _link_plan_requirement_to_scratch_major(db_session, plan)
    with pytest.raises(plan_validation_service.PlanAcademicValidationError):
        plan_swap_service.swap_plan_course(
            db_session, plan.degree_plan_id, plan_course.plan_course_id, second_id
        )
    db_session.refresh(plan_course)
    assert plan_course.course_id == first_id


def test_swap_plan_course_accepts_a_valid_course_group_alternative(db_session):
    """Reallocate a requirement after swapping between two valid group members."""
    first_id, second_id = _two_real_course_ids(db_session)
    plan, plan_course = _make_plan_with_one_course(db_session, first_id)
    node = _link_plan_requirement_to_scratch_major(db_session, plan)
    group = CourseGroup(
        course_group_code="EDIT_VALIDATION_OPTIONS",
        course_group_name="Edit Validation Options",
        course_group_type="ELECTIVE",
    )
    db_session.add(group)
    db_session.flush()
    db_session.add_all(
        [
            CourseGroupMember(course_group_id=group.course_group_id, course_id=first_id),
            CourseGroupMember(course_group_id=group.course_group_id, course_id=second_id),
        ]
    )
    node.node_type = "COURSE_GROUP"
    node.required_course_id = None
    node.course_group_id = group.course_group_id
    node.required_count = 1
    db_session.flush()
    plan_swap_service.swap_plan_course(
        db_session, plan.degree_plan_id, plan_course.plan_course_id, second_id
    )
    db_session.refresh(plan_course)
    allocation = db_session.query(RequirementAllocation).filter(
        RequirementAllocation.plan_course_id == plan_course.plan_course_id
    ).one()
    assert plan_course.course_id == second_id
    assert allocation.requirement_node_id == node.requirement_node_id


def test_unrelated_manual_course_counts_as_workload_not_degree_progress(db_session):
    """Separate scheduled workload credits from conservative degree-applicable credits."""
    first_id, second_id = _two_real_course_ids(db_session)
    plan, original = _make_plan_with_one_course(db_session, first_id)
    _link_plan_requirement_to_scratch_major(db_session, plan)
    plan_swap_service.add_plan_course(
        db_session, plan.degree_plan_id, second_id, FALL_2026_TERM_ID
    )
    output = optimizer_persistence.load_degree_plan(db_session, plan.degree_plan_id)
    assert output is not None
    assert output.total_credit_hours == float(original.credit_hours)
    assert output.scheduled_credit_hours > output.total_credit_hours
