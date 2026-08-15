"""Tests GET /plans/{id} and GET /plans/compare against a hand-built persisted
plan (via db_session directly, bypassing a real solve for speed)."""

from app.models.course import Course
from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.student import Student
from app.models.term import Term


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
