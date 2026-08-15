"""Tests GET /plans/{id}, GET /plans/compare, and the plan-board swap endpoints
against hand-built persisted plans (via db_session directly, bypassing a real
solve for speed)."""

from app.models.course import Course
from app.models.course_group import CourseGroup
from app.models.course_group_member import CourseGroupMember
from app.models.course_rule_node import CourseRuleNode
from app.models.degree_plan import DegreePlan
from app.models.enums import RequirementNodeType
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.requirement_set import RequirementSet
from app.models.student import Student
from app.models.term import Term


def _two_swappable_course_ids(db_session) -> tuple[int, int]:
    """Return two real, fall-offered course_ids with no prerequisites of their
    own, so swap tests aren't tripped up by `plan_swap_validation`'s
    offering/prerequisite checks (which have their own dedicated tests)."""
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


def _persist_one_plan(db_session) -> DegreePlan:
    """Persist a minimal one-course plan directly, for testing the read endpoints."""
    course = db_session.query(Course).order_by(Course.course_id.asc()).first()
    term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    student = Student(display_name="Plans API Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id)
    db_session.add(scenario)
    db_session.flush()
    plan = DegreePlan(
        planning_scenario_id=scenario.planning_scenario_id,
        plan_name="FIXTURE",
        status="DRAFT",
        total_credit_hours=course.credit_hours,
    )
    db_session.add(plan)
    db_session.flush()
    db_session.add(
        PlanCourse(
            degree_plan_id=plan.degree_plan_id, course_id=course.course_id, term_id=term.term_id,
            credit_hours=course.credit_hours,
        )
    )
    db_session.flush()
    return plan


def test_get_plan_returns_full_breakdown(client, db_session):
    plan = _persist_one_plan(db_session)

    response = client.get(f"/plans/{plan.degree_plan_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["degree_plan_id"] == plan.degree_plan_id
    assert len(body["courses"]) == 1


def test_get_plan_404_for_unknown_plan(client):
    response = client.get("/plans/999999")

    assert response.status_code == 404


def test_compare_plans_returns_metrics_for_each_id(client, db_session):
    plan_one = _persist_one_plan(db_session)
    plan_two = _persist_one_plan(db_session)

    response = client.get(f"/plans/compare?ids={plan_one.degree_plan_id},{plan_two.degree_plan_id}")

    assert response.status_code == 200
    plans = response.json()["plans"]
    assert {p["degree_plan_id"] for p in plans} == {plan_one.degree_plan_id, plan_two.degree_plan_id}


def test_compare_plans_400_for_malformed_ids(client):
    response = client.get("/plans/compare?ids=abc,def")

    assert response.status_code == 400


def test_compare_plans_404_for_unknown_id(client):
    response = client.get("/plans/compare?ids=999999")

    assert response.status_code == 404


def test_get_plan_requirements_returns_flattened_sets(client, db_session):
    plan = _persist_one_plan(db_session)

    response = client.get(f"/plans/{plan.degree_plan_id}/requirements")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


def test_get_plan_requirements_404_for_unknown_plan(client):
    response = client.get("/plans/999999/requirements")

    assert response.status_code == 404


def _persist_plan_with_swappable_course(db_session) -> tuple[DegreePlan, PlanCourse, int]:
    """Persist a plan whose one course is allocated to a two-member course group,
    returning the plan, its plan_course, and the group's other member's course_id."""
    picked_id, alternative_id = _two_swappable_course_ids(db_session)
    picked, alternative = db_session.get(Course, picked_id), db_session.get(Course, alternative_id)
    term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    student = Student(display_name="Swap API Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id)
    db_session.add(scenario)
    db_session.flush()
    plan = DegreePlan(
        planning_scenario_id=scenario.planning_scenario_id, status="DRAFT", total_credit_hours=picked.credit_hours
    )
    db_session.add(plan)
    db_session.flush()
    plan_course = PlanCourse(
        degree_plan_id=plan.degree_plan_id, course_id=picked.course_id, term_id=term.term_id, credit_hours=picked.credit_hours
    )
    db_session.add(plan_course)
    db_session.flush()
    req_set = RequirementSet(
        requirement_set_code="SWAP-API-TEST", requirement_set_name="Swap API Test", requirement_set_type="CORE"
    )
    group = CourseGroup(
        course_group_code="SWAP-API-TEST", course_group_name="Swap API Test", course_group_type="ELECTIVE"
    )
    db_session.add_all([req_set, group])
    db_session.flush()
    db_session.add_all(
        [
            CourseGroupMember(course_group_id=group.course_group_id, course_id=picked.course_id),
            CourseGroupMember(course_group_id=group.course_group_id, course_id=alternative.course_id),
        ]
    )
    node = RequirementNode(
        requirement_set_id=req_set.requirement_set_id,
        node_type=RequirementNodeType.COURSE_GROUP,
        course_group_id=group.course_group_id,
    )
    db_session.add(node)
    db_session.flush()
    db_session.add(
        RequirementAllocation(
            degree_plan_id=plan.degree_plan_id, requirement_node_id=node.requirement_node_id, plan_course_id=plan_course.plan_course_id
        )
    )
    db_session.flush()
    return plan, plan_course, alternative.course_id


def test_get_plan_swap_options_returns_the_group_alternative(client, db_session):
    plan, plan_course, alternative_course_id = _persist_plan_with_swappable_course(db_session)

    response = client.get(f"/plans/{plan.degree_plan_id}/swap-options")

    assert response.status_code == 200
    options = response.json()[str(plan_course.plan_course_id)]
    assert alternative_course_id in {course["course_id"] for course in options}


def test_get_plan_swap_options_404_for_unknown_plan(client):
    response = client.get("/plans/999999/swap-options")

    assert response.status_code == 404


def test_swap_plan_course_replaces_the_course_and_returns_the_updated_plan(client, db_session):
    plan, plan_course, alternative_course_id = _persist_plan_with_swappable_course(db_session)

    response = client.post(
        f"/plans/{plan.degree_plan_id}/courses/{plan_course.plan_course_id}/swap",
        json={"new_course_id": alternative_course_id},
    )

    assert response.status_code == 200
    updated_course_ids = {course["course"]["course_id"] for course in response.json()["courses"]}
    assert alternative_course_id in updated_course_ids


def test_swap_plan_course_404_for_unknown_plan_course(client, db_session):
    plan, _, alternative_course_id = _persist_plan_with_swappable_course(db_session)

    response = client.post(
        f"/plans/{plan.degree_plan_id}/courses/999999/swap", json={"new_course_id": alternative_course_id}
    )

    assert response.status_code == 404


def test_swap_plan_course_422_for_unknown_new_course(client, db_session):
    plan, plan_course, _ = _persist_plan_with_swappable_course(db_session)

    response = client.post(
        f"/plans/{plan.degree_plan_id}/courses/{plan_course.plan_course_id}/swap", json={"new_course_id": 999999}
    )

    assert response.status_code == 422


def test_add_plan_course_returns_the_plan_with_the_new_course(client, db_session):
    plan = _persist_one_plan(db_session)
    term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    _, second_id = _two_swappable_course_ids(db_session)

    response = client.post(f"/plans/{plan.degree_plan_id}/courses", json={"course_id": second_id, "term_id": term.term_id})

    assert response.status_code == 200
    body = response.json()
    assert len(body["courses"]) == 2
    added = next(course for course in body["courses"] if course["course"]["course_id"] == second_id)
    assert added["placement_source"] == "STUDENT_ADDED"


def test_add_plan_course_404_for_unknown_plan(db_session, client):
    term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    _, second_id = _two_swappable_course_ids(db_session)

    response = client.post("/plans/999999/courses", json={"course_id": second_id, "term_id": term.term_id})

    assert response.status_code == 404


def test_add_plan_course_404_for_unknown_term(client, db_session):
    plan = _persist_one_plan(db_session)
    _, second_id = _two_swappable_course_ids(db_session)

    response = client.post(f"/plans/{plan.degree_plan_id}/courses", json={"course_id": second_id, "term_id": 999999})

    assert response.status_code == 404


def test_add_plan_course_422_for_unknown_course(client, db_session):
    plan = _persist_one_plan(db_session)
    term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()

    response = client.post(f"/plans/{plan.degree_plan_id}/courses", json={"course_id": 999999, "term_id": term.term_id})

    assert response.status_code == 422


def test_add_plan_course_422_when_the_course_is_already_in_the_plan(client, db_session):
    plan = _persist_one_plan(db_session)
    term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    existing_course_id = (
        db_session.query(PlanCourse.course_id).filter(PlanCourse.degree_plan_id == plan.degree_plan_id).scalar()
    )

    response = client.post(
        f"/plans/{plan.degree_plan_id}/courses", json={"course_id": existing_course_id, "term_id": term.term_id}
    )

    assert response.status_code == 422


def test_remove_plan_course_returns_the_plan_without_the_removed_course(client, db_session):
    plan = _persist_one_plan(db_session)
    plan_course_id = db_session.query(PlanCourse.plan_course_id).filter(
        PlanCourse.degree_plan_id == plan.degree_plan_id
    ).scalar()

    response = client.delete(f"/plans/{plan.degree_plan_id}/courses/{plan_course_id}")

    assert response.status_code == 200
    assert response.json()["courses"] == []


def test_remove_plan_course_404_for_unknown_plan_course(client, db_session):
    plan = _persist_one_plan(db_session)

    response = client.delete(f"/plans/{plan.degree_plan_id}/courses/999999")

    assert response.status_code == 404


def test_swap_plan_course_422_for_a_course_not_offered_that_term(client, db_session):
    picked_id, _ = _two_swappable_course_ids(db_session)
    spring_term = db_session.query(Term).filter(Term.term_type == "SPRING").order_by(Term.sequence_index.asc()).first()
    student = Student(display_name="Swap Validation API Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id)
    db_session.add(scenario)
    db_session.flush()
    picked = db_session.get(Course, picked_id)
    plan = DegreePlan(planning_scenario_id=scenario.planning_scenario_id, status="DRAFT", total_credit_hours=picked.credit_hours)
    db_session.add(plan)
    db_session.flush()
    plan_course = PlanCourse(
        degree_plan_id=plan.degree_plan_id, course_id=picked_id, term_id=spring_term.term_id, credit_hours=picked.credit_hours
    )
    db_session.add(plan_course)
    db_session.flush()
    # PSYCH 4993 "Psychology of Gender" is fall-only in the loaded catalog.
    fall_only_course_id = 874

    response = client.post(
        f"/plans/{plan.degree_plan_id}/courses/{plan_course.plan_course_id}/swap",
        json={"new_course_id": fall_only_course_id},
    )

    assert response.status_code == 422
