"""Regression tests for summer filtering and adaptive long planning horizons."""

from app.models.planning_scenario import PlanningScenario
from app.models.student import Student
from app.models.term import Term
from ortools.sat.python import cp_model
from types import SimpleNamespace

from app.schemas.scenario import ScenarioCreate
from app.services import optimizer_model, optimizer_terms


def _scenario(db_session, allow_summer: bool, target_term_id: int | None = None) -> PlanningScenario:
    """Create a minimal scenario starting at the first seeded term."""
    student = Student(display_name="Horizon Student")
    db_session.add(student)
    db_session.flush()
    start = db_session.query(Term).order_by(Term.sequence_index).first()
    scenario = PlanningScenario(
        student_id=student.student_id,
        start_term_id=start.term_id,
        target_graduation_term_id=target_term_id,
        allow_summer=allow_summer,
    )
    db_session.add(scenario)
    db_session.flush()
    return scenario


def test_summer_disabled_removes_every_summer_assignment_term(db_session):
    """Exclude summer terms completely when the scenario disables summer enrollment."""
    terms = optimizer_terms.build_term_horizon(db_session, _scenario(db_session, False))
    assert terms
    assert all(term.term_type != "SUMMER" for term in terms)


def test_expanded_horizon_supports_more_than_sixteen_terms(db_session):
    """Expose a safety-capped long horizon for retrying scenarios that need extra years."""
    terms = optimizer_terms.build_term_horizon(
        db_session,
        _scenario(db_session, True),
        optimizer_terms.ABSOLUTE_MAX_HORIZON_TERMS,
    )
    assert len(terms) > optimizer_terms.DEFAULT_MAX_HORIZON_TERMS


def test_target_graduation_remains_a_hard_horizon_boundary(db_session):
    """Never expand beyond an explicit target graduation term."""
    target = db_session.query(Term).order_by(Term.sequence_index).offset(4).first()
    terms = optimizer_terms.build_term_horizon(
        db_session,
        _scenario(db_session, True, target.term_id),
        optimizer_terms.ABSOLUTE_MAX_HORIZON_TERMS,
    )
    assert terms[-1].sequence_index == target.sequence_index


def test_scenario_input_defaults_summer_maximum_to_nine_credits():
    """Use the requested independent nine-credit summer default."""
    payload = ScenarioCreate(start_term_id=1, programs=[{"academic_program_id": 1, "program_role": "PRIMARY_MAJOR"}])
    assert payload.summer_maximum_credits == 9


def _summer_credit_model(
    maximum: float,
    course_count: int,
    bounds: dict[int, tuple[float | None, float | None]] | None = None,
):
    """Build a tiny term-credit model with every three-credit summer course required."""
    model = cp_model.CpModel()
    term = SimpleNamespace(term_id=3, term_type="SUMMER")
    course_ids = range(1, course_count + 1)
    assignments = {(course_id, term.term_id): model.NewBoolVar(f"summer_{course_id}") for course_id in course_ids}
    context = SimpleNamespace(
        model=model,
        scenario=SimpleNamespace(
            default_minimum_credits=12,
            default_maximum_credits=18,
            summer_maximum_credits=maximum,
        ),
        candidates=SimpleNamespace(
            courses_by_id={course_id: SimpleNamespace(credit_hours=3) for course_id in course_ids}
        ),
        assign=assignments,
        term_credit_totals={},
        term_used_indicators={},
        var_counter=0,
    )
    optimizer_model._add_one_term_credit_constraint(context, term, bounds or {})
    for variable in assignments.values():
        model.Add(variable == 1)
    return model


def test_custom_summer_maximum_is_enforced_independently():
    """Reject six summer credits under a custom five-credit cap."""
    solver = cp_model.CpSolver()
    assert solver.Solve(_summer_credit_model(5, 2)) == cp_model.INFEASIBLE


def test_nine_summer_credits_fit_the_default_cap():
    """Allow nine summer credits even when the regular-term minimum is twelve."""
    solver = cp_model.CpSolver()
    assert solver.Solve(_summer_credit_model(9, 3)) == cp_model.OPTIMAL


def test_partial_summer_override_keeps_the_scenario_default_maximum():
    """Keep the summer cap when an override row leaves its maximum unset."""
    solver = cp_model.CpSolver()
    assert solver.Solve(_summer_credit_model(5, 2, {3: (None, None)})) == cp_model.INFEASIBLE
