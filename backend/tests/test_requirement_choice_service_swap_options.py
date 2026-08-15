"""Tests requirement_choice_service.list_swap_options_for_plan: a plan_course
allocated to a choice-shaped requirement node (a course group, or a literal
"course A or course B" alternative) gets its group-mate/sibling courses back
as swap candidates; a plan_course allocated to a genuinely mandatory single
course gets none.

Uses fall-offered, prerequisite-free courses throughout so these tests stay
about the choice-detection logic itself, not `plan_swap_validation`'s
offering/credit/prerequisite checks (which have their own dedicated tests)."""

from app.models.course import Course
from app.models.course_group import CourseGroup
from app.models.course_group_member import CourseGroupMember
from app.models.course_rule_node import CourseRuleNode
from app.models.degree_plan import DegreePlan
from app.models.enums import RequirementNodeType, RuleOperator
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.requirement_set import RequirementSet
from app.models.student import Student
from app.services import requirement_choice_service


def _two_real_course_ids(db_session) -> tuple[int, int]:
    """Return two real, fall-offered course_ids that have no prerequisites of
    their own, so `plan_swap_validation`'s checks always pass for them
    regardless of the bare test plan's (empty) placements."""
    prereq_target_ids = db_session.query(CourseRuleNode.target_course_id).distinct().subquery()
    rows = (
        db_session.query(Course.course_id)
        .filter(Course.fall_offered.is_(True))
        .filter(~Course.course_id.in_(db_session.query(prereq_target_ids.c.target_course_id)))
        .order_by(Course.course_id.asc())
        .limit(2)
        .all()
    )
    return rows[0][0], rows[1][0]


def _make_plan(db_session) -> DegreePlan:
    """Persist a bare scenario + degree plan for a fresh student."""
    student = Student(display_name="Swap Options Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id)
    db_session.add(scenario)
    db_session.flush()
    plan = DegreePlan(planning_scenario_id=scenario.planning_scenario_id, status="DRAFT")
    db_session.add(plan)
    db_session.flush()
    return plan


def _add_plan_course_with_allocation(db_session, plan: DegreePlan, course_id: int, node_id: int) -> PlanCourse:
    """Persist one plan_courses row for `course_id`, allocated to `node_id`."""
    course = db_session.get(Course, course_id)
    plan_course = PlanCourse(
        degree_plan_id=plan.degree_plan_id, course_id=course_id, term_id=1, credit_hours=course.credit_hours
    )
    db_session.add(plan_course)
    db_session.flush()
    db_session.add(
        RequirementAllocation(
            degree_plan_id=plan.degree_plan_id, requirement_node_id=node_id, plan_course_id=plan_course.plan_course_id
        )
    )
    db_session.flush()
    return plan_course


def _make_requirement_set(db_session, code: str) -> RequirementSet:
    """Persist a bare requirement_sets row to attach test nodes to."""
    req_set = RequirementSet(requirement_set_code=code, requirement_set_name=code, requirement_set_type="CORE")
    db_session.add(req_set)
    db_session.flush()
    return req_set


def test_course_group_leaf_offers_its_other_members_as_alternatives(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    req_set = _make_requirement_set(db_session, "SWAP-GROUP-TEST")
    group = CourseGroup(
        course_group_code="SWAP-GROUP-TEST", course_group_name="Swap Group Test", course_group_type="ELECTIVE"
    )
    db_session.add(group)
    db_session.flush()
    db_session.add_all(
        [
            CourseGroupMember(course_group_id=group.course_group_id, course_id=first_id),
            CourseGroupMember(course_group_id=group.course_group_id, course_id=second_id),
        ]
    )
    node = RequirementNode(
        requirement_set_id=req_set.requirement_set_id,
        node_type=RequirementNodeType.COURSE_GROUP,
        course_group_id=group.course_group_id,
    )
    db_session.add(node)
    db_session.flush()
    plan = _make_plan(db_session)
    plan_course = _add_plan_course_with_allocation(db_session, plan, first_id, node.requirement_node_id)

    swap_options = requirement_choice_service.list_swap_options_for_plan(db_session, plan.degree_plan_id)

    alternatives = {c.course_id for c in swap_options[plan_course.plan_course_id]}
    assert alternatives == {first_id, second_id}


def test_either_or_course_leaf_offers_its_siblings_as_alternatives(db_session):
    first_id, second_id = _two_real_course_ids(db_session)
    req_set = _make_requirement_set(db_session, "SWAP-EITHER-OR-TEST")
    parent = RequirementNode(
        requirement_set_id=req_set.requirement_set_id, node_type=RequirementNodeType.GROUP, node_operator=RuleOperator.ANY
    )
    db_session.add(parent)
    db_session.flush()
    child_a = RequirementNode(
        requirement_set_id=req_set.requirement_set_id,
        node_type=RequirementNodeType.COURSE,
        required_course_id=first_id,
        parent_requirement_node_id=parent.requirement_node_id,
    )
    child_b = RequirementNode(
        requirement_set_id=req_set.requirement_set_id,
        node_type=RequirementNodeType.COURSE,
        required_course_id=second_id,
        parent_requirement_node_id=parent.requirement_node_id,
    )
    db_session.add_all([child_a, child_b])
    db_session.flush()
    plan = _make_plan(db_session)
    plan_course = _add_plan_course_with_allocation(db_session, plan, first_id, child_a.requirement_node_id)

    swap_options = requirement_choice_service.list_swap_options_for_plan(db_session, plan.degree_plan_id)

    alternatives = {c.course_id for c in swap_options[plan_course.plan_course_id]}
    assert alternatives == {first_id, second_id}


def test_a_mandatory_single_course_has_no_swap_alternatives(db_session):
    first_id, _ = _two_real_course_ids(db_session)
    req_set = _make_requirement_set(db_session, "SWAP-MANDATORY-TEST")
    node = RequirementNode(
        requirement_set_id=req_set.requirement_set_id,
        node_type=RequirementNodeType.COURSE,
        required_course_id=first_id,
    )
    db_session.add(node)
    db_session.flush()
    plan = _make_plan(db_session)
    plan_course = _add_plan_course_with_allocation(db_session, plan, first_id, node.requirement_node_id)

    swap_options = requirement_choice_service.list_swap_options_for_plan(db_session, plan.degree_plan_id)

    assert plan_course.plan_course_id not in swap_options


def test_a_candidate_already_placed_elsewhere_in_the_plan_is_excluded(db_session):
    """A course group's other member is a valid swap target on its own, but not
    when that same course is already placed in a *different* plan_courses row
    on this plan -- swapping it in there would just bounce as a duplicate-
    course error, so it shouldn't be offered in the first place."""
    first_id, second_id = _two_real_course_ids(db_session)
    req_set = _make_requirement_set(db_session, "SWAP-DUP-TEST")
    group = CourseGroup(course_group_code="SWAP-DUP-TEST", course_group_name="Swap Dup Test", course_group_type="ELECTIVE")
    db_session.add(group)
    db_session.flush()
    db_session.add_all(
        [
            CourseGroupMember(course_group_id=group.course_group_id, course_id=first_id),
            CourseGroupMember(course_group_id=group.course_group_id, course_id=second_id),
        ]
    )
    node = RequirementNode(
        requirement_set_id=req_set.requirement_set_id,
        node_type=RequirementNodeType.COURSE_GROUP,
        course_group_id=group.course_group_id,
    )
    db_session.add(node)
    db_session.flush()
    plan = _make_plan(db_session)
    plan_course = _add_plan_course_with_allocation(db_session, plan, first_id, node.requirement_node_id)
    second_course = db_session.get(Course, second_id)
    db_session.add(
        PlanCourse(
            degree_plan_id=plan.degree_plan_id, course_id=second_id, term_id=1, credit_hours=second_course.credit_hours
        )
    )
    db_session.flush()

    swap_options = requirement_choice_service.list_swap_options_for_plan(db_session, plan.degree_plan_id)

    alternatives = {c.course_id for c in swap_options.get(plan_course.plan_course_id, [])}
    assert second_id not in alternatives
    assert alternatives == {first_id}


def test_no_allocations_yields_no_swap_options(db_session):
    plan = _make_plan(db_session)

    assert requirement_choice_service.list_swap_options_for_plan(db_session, plan.degree_plan_id) == {}
