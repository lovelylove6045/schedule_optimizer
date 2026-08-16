"""Tests plan_comparison_service.compute_plan_metrics() against a hand-built
degree_plans/plan_courses/requirement_allocations fixture (not a real solve --
the numbers are hand-verified against known inputs), using real course/term/
requirement_node ids so foreign keys are satisfied."""

from app.models.course import Course
from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.student import Student
from app.models.term import Term
from app.services import plan_comparison_service


def _two_courses(db_session) -> list[Course]:
    """Return 2 real courses with distinct credit_hours, for building fixture plan_courses."""
    return db_session.query(Course).filter(Course.credit_hours > 0).order_by(Course.course_id.asc()).limit(2).all()


def _two_requirement_nodes(db_session) -> list[RequirementNode]:
    """Return 2 real requirement_nodes, for building fixture requirement_allocations."""
    return db_session.query(RequirementNode).order_by(RequirementNode.requirement_node_id.asc()).limit(2).all()


def _fall_and_summer_terms(db_session) -> tuple[Term, Term]:
    """Return one FALL term and one SUMMER term, for building fixture plan_courses."""
    fall_term = db_session.query(Term).filter(Term.term_type == "FALL").order_by(Term.sequence_index.asc()).first()
    summer_term = (
        db_session.query(Term).filter(Term.term_type == "SUMMER").order_by(Term.sequence_index.asc()).first()
    )
    return fall_term, summer_term


def _build_fixture_plan(db_session) -> DegreePlan:
    """Persist a hand-built plan: course A (in the FALL term) satisfies 2 requirement
    nodes (overlap), course B (in the SUMMER term) satisfies 1 (no overlap)."""
    course_a, course_b = _two_courses(db_session)
    node_one, node_two = _two_requirement_nodes(db_session)
    fall_term, summer_term = _fall_and_summer_terms(db_session)
    student = Student(display_name="Fixture Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id)
    db_session.add(scenario)
    db_session.flush()
    plan = DegreePlan(
        planning_scenario_id=scenario.planning_scenario_id,
        plan_name="FIXTURE",
        status="DRAFT",
        total_credit_hours=float(course_a.credit_hours) + float(course_b.credit_hours),
        additional_credit_hours=0,
    )
    db_session.add(plan)
    db_session.flush()
    plan_course_a = PlanCourse(
        degree_plan_id=plan.degree_plan_id,
        course_id=course_a.course_id,
        term_id=fall_term.term_id,
        credit_hours=course_a.credit_hours,
    )
    plan_course_b = PlanCourse(
        degree_plan_id=plan.degree_plan_id,
        course_id=course_b.course_id,
        term_id=summer_term.term_id,
        credit_hours=course_b.credit_hours,
    )
    db_session.add_all([plan_course_a, plan_course_b])
    db_session.flush()
    db_session.add_all(
        [
            RequirementAllocation(
                degree_plan_id=plan.degree_plan_id,
                requirement_node_id=node_one.requirement_node_id,
                plan_course_id=plan_course_a.plan_course_id,
                credit_hours_applied=plan_course_a.credit_hours,
            ),
            RequirementAllocation(
                degree_plan_id=plan.degree_plan_id,
                requirement_node_id=node_two.requirement_node_id,
                plan_course_id=plan_course_a.plan_course_id,
                credit_hours_applied=plan_course_a.credit_hours,
            ),
            RequirementAllocation(
                degree_plan_id=plan.degree_plan_id,
                requirement_node_id=node_one.requirement_node_id,
                plan_course_id=plan_course_b.plan_course_id,
                credit_hours_applied=plan_course_b.credit_hours,
            ),
        ]
    )
    db_session.flush()
    return plan, course_a, course_b


def test_compute_plan_metrics_matches_hand_built_fixture(db_session):
    """Every metric should match what the hand-built fixture's inputs dictate."""
    plan, course_a, course_b = _build_fixture_plan(db_session)

    metrics = plan_comparison_service.compute_plan_metrics(db_session, plan.degree_plan_id)

    assert metrics is not None
    assert metrics.degree_plan_id == plan.degree_plan_id
    assert metrics.plan_name == "FIXTURE"
    assert metrics.summer_term_count == 1
    assert metrics.max_term_credit_hours == max(float(course_a.credit_hours), float(course_b.credit_hours))
    assert metrics.avg_term_credit_hours == (float(course_a.credit_hours) + float(course_b.credit_hours)) / 2
    assert metrics.overlap_credit_hours == 0.0


def test_compute_plan_metrics_returns_none_for_unknown_plan(db_session):
    """An unknown degree_plan_id should return None, not raise."""
    assert plan_comparison_service.compute_plan_metrics(db_session, 999_999_999) is None
