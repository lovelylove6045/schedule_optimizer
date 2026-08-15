"""End-to-end tests for optimizer_service.generate_plans() against real Aerospace BS
catalog data: a full multi-objective run producing several meaningfully different
plans, and a deliberately infeasible scenario (unreachable target graduation term)
surfacing a clear reason instead of crashing."""

from app.models.enums import ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_program import ScenarioProgram
from app.models.student import Student
from app.models.term import Term
from app.services import optimizer_service

AERO_BS_PROGRAM_ID = 1


def _make_scenario(
    db_session,
    program_ids: list[int],
    default_maximum_credits: float = 18.0,
    target_graduation_term_id: int | None = None,
) -> PlanningScenario:
    """Create a minimal, flushed PlanningScenario with the given scenario_programs."""
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    start_term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    scenario = PlanningScenario(
        student_id=student.student_id,
        start_term_id=start_term.term_id,
        target_graduation_term_id=target_graduation_term_id,
        allow_summer=True,
        default_minimum_credits=0,
        default_maximum_credits=default_maximum_credits,
    )
    db_session.add(scenario)
    db_session.flush()
    for index, program_id in enumerate(program_ids):
        role = ScenarioProgramRole.PRIMARY_MAJOR if index == 0 else ScenarioProgramRole.MINOR
        db_session.add(
            ScenarioProgram(
                planning_scenario_id=scenario.planning_scenario_id,
                academic_program_id=program_id,
                program_role=role,
            )
        )
    db_session.flush()
    return scenario


def _early_term_id(db_session, terms_after_start: int) -> int:
    """Return the term_id `terms_after_start` sequence positions after the first term."""
    terms = db_session.query(Term).order_by(Term.sequence_index.asc()).limit(terms_after_start + 1).all()
    return terms[-1].term_id


def test_generate_plans_produces_multiple_distinct_plans_for_real_program(db_session):
    """A real Aerospace BS scenario with no restrictive preferences should yield
    several feasible, meaningfully-different plans -- not just one repeated result."""
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])

    plans = optimizer_service.generate_plans(db_session, scenario.planning_scenario_id)

    assert len(plans) >= 2
    for plan in plans:
        assert plan.infeasibility_reason is None
        assert len(plan.assignments) > 0
        assert plan.projected_graduation_term_id is not None
    signatures = {frozenset(plan.assignments.items()) for plan in plans}
    assert len(signatures) == len(plans), "expected every surviving plan to be a distinct assignment"


def test_generate_plans_labels_each_plan_with_its_objective_strategy(db_session):
    """Every surviving plan should carry the objective_type it was solved for as its
    strategy_code, so callers can tell plans apart without inspecting assignments."""
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])

    plans = optimizer_service.generate_plans(db_session, scenario.planning_scenario_id)

    for plan in plans:
        assert plan.objective_type is not None
        assert plan.strategy_code == plan.objective_type.value


def test_generate_plans_reports_infeasibility_for_unreachable_target_graduation(db_session):
    """A target graduation term far too early for a multi-year Aerospace BS to be
    completed in should return a single infeasible plan with a clear reason, not
    raise or silently return an empty list."""
    early_target_term_id = _early_term_id(db_session, terms_after_start=1)
    scenario = _make_scenario(
        db_session,
        [AERO_BS_PROGRAM_ID],
        target_graduation_term_id=early_target_term_id,
    )

    plans = optimizer_service.generate_plans(db_session, scenario.planning_scenario_id)

    assert len(plans) == 1
    assert plans[0].infeasibility_reason is not None
    assert plans[0].assignments == {}


def test_generate_plans_raises_for_unknown_scenario(db_session):
    """An unknown planning_scenario_id should raise ValueError rather than fail silently."""
    try:
        optimizer_service.generate_plans(db_session, 999_999_999)
        assert False, "expected ValueError for an unknown planning_scenario_id"
    except ValueError:
        pass
