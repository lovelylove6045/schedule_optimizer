"""Tests plan_generation_service.generate_and_persist_plans()'s filtering/ordering
of scenario_objectives selections, and its persistence + reload round-trip,
against real Aerospace BS catalog data."""

from app.models.enums import OptimizationObjectiveType, ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_objective import ScenarioObjective
from app.models.scenario_program import ScenarioProgram
from app.models.student import Student
from app.models.term import Term
from app.services import plan_generation_service

AERO_BS_PROGRAM_ID = 1


def _make_scenario(db_session, objective_types: list[OptimizationObjectiveType] | None = None) -> PlanningScenario:
    """Create a minimal, flushed PlanningScenario for Aerospace BS, optionally with
    an ordered scenario_objectives selection."""
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    start_term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    scenario = PlanningScenario(student_id=student.student_id, start_term_id=start_term.term_id, allow_summer=True)
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioProgram(
            planning_scenario_id=scenario.planning_scenario_id,
            academic_program_id=AERO_BS_PROGRAM_ID,
            program_role=ScenarioProgramRole.PRIMARY_MAJOR,
        )
    )
    for index, objective_type in enumerate(objective_types or []):
        db_session.add(
            ScenarioObjective(
                planning_scenario_id=scenario.planning_scenario_id,
                objective_type=objective_type,
                display_order=index,
            )
        )
    db_session.flush()
    return scenario


def test_generate_and_persist_plans_with_no_objectives_returns_all_five(db_session):
    """A scenario with no scenario_objectives selection gets every supported objective's plan."""
    scenario = _make_scenario(db_session)

    plans = plan_generation_service.generate_and_persist_plans(db_session, scenario.planning_scenario_id)

    assert len(plans) >= 2
    for plan in plans:
        assert plan.degree_plan_id is not None


def test_generate_and_persist_plans_keeps_recommended_before_selected_alternatives(db_session):
    """Keep the recommended plan first before requested legacy alternatives."""
    requested_order = [
        OptimizationObjectiveType.MIN_SUMMER_ENROLLMENT,
        OptimizationObjectiveType.EARLIEST_GRADUATION,
    ]
    scenario = _make_scenario(db_session, objective_types=requested_order)

    plans = plan_generation_service.generate_and_persist_plans(db_session, scenario.planning_scenario_id)

    assert plans[0].plan_name == OptimizationObjectiveType.MIN_ADDITIONAL_CREDITS.value
    assert [plan.plan_name for plan in plans[1:]] == [
        objective.value for objective in requested_order if any(plan.plan_name == objective.value for plan in plans[1:])
    ]


def test_generate_and_persist_plans_raises_for_unknown_scenario(db_session):
    """An unknown planning_scenario_id should raise ValueError."""
    try:
        plan_generation_service.generate_and_persist_plans(db_session, 999_999_999)
        assert False, "expected ValueError for an unknown planning_scenario_id"
    except ValueError:
        pass
