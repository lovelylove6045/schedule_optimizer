"""Tests optimizer_model.py's CP-SAT hard-constraint construction against the 3
scenarios named in docs/PHASES.md §3.5, using real Aerospace BS/minor catalog data."""

from ortools.sat.python import cp_model

from app.models.enums import OptimizationObjectiveType, ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_program import ScenarioProgram
from app.models.student import Student
from app.models.term import Term
from app.services import optimizer_candidates, optimizer_model, optimizer_objectives, optimizer_terms

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2  # heavy real overlap with Aero BS -- same department's minor
MAX_SOLVE_SECONDS = 20.0


def _make_scenario(
    db_session, program_ids: list[int], default_maximum_credits: float = 18.0
) -> PlanningScenario:
    """Create a minimal, flushed PlanningScenario with the given scenario_programs."""
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    start_term = db_session.query(Term).order_by(Term.sequence_index.asc()).first()
    scenario = PlanningScenario(
        student_id=student.student_id,
        start_term_id=start_term.term_id,
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


def _build_model(db_session, scenario: PlanningScenario) -> optimizer_model.OptimizerModel:
    """Build a candidate set, term horizon, and CP-SAT model for `scenario`."""
    candidates = optimizer_candidates.build_candidate_course_set(db_session, scenario)
    terms = optimizer_terms.build_term_horizon(db_session, scenario)
    return optimizer_model.build_optimizer_model(db_session, scenario, candidates, terms)


def _solve(ctx: optimizer_model.OptimizerModel) -> tuple[int, cp_model.CpSolver]:
    """Solve `ctx`'s model with a bounded wall-clock time limit."""
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = MAX_SOLVE_SECONDS
    status = solver.Solve(ctx.model)
    return status, solver


def _earliest_graduation_index(db_session, scenario: PlanningScenario) -> int:
    """Build a model for `scenario`, solve it for earliest graduation, and return the
    resulting graduation_index (sequence_index of the latest term used)."""
    ctx = _build_model(db_session, scenario)
    optimizer_objectives.set_primary_objective(ctx, OptimizationObjectiveType.EARLIEST_GRADUATION)
    status, solver = _solve(ctx)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return solver.Value(ctx.graduation_index_var)


def test_scenario_a_primary_program_only_is_feasible(db_session):
    """Scenario A: no scenario_preferences or tight caps, primary program alone -> a
    feasible schedule exists, and every one of its requirement sets' root nodes holds."""
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])
    ctx = _build_model(db_session, scenario)

    status, solver = _solve(ctx)

    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assigned = [var for var in ctx.assign.values() if solver.Value(var) == 1]
    assert len(assigned) > 0
    for req_set in ctx.candidates.requirement_sets:
        for node in req_set.nodes:
            assert solver.Value(ctx.node_indicators[node.requirement_node_id]) == 1


def test_scenario_b_tight_credit_cap_needs_more_terms_than_loose_cap(db_session):
    """Scenario B: a tight per-term credit cap still finds a feasible plan -- it just
    needs a later graduation term than a looser cap does."""
    loose_scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID], default_maximum_credits=18.0)
    tight_scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID], default_maximum_credits=9.0)

    loose_graduation_index = _earliest_graduation_index(db_session, loose_scenario)
    tight_graduation_index = _earliest_graduation_index(db_session, tight_scenario)

    assert tight_graduation_index > loose_graduation_index


def test_scenario_c_primary_plus_minor_shares_courses_across_programs(db_session):
    """Scenario C: primary major + a minor with known shared courses -> the solved
    plan's leaf satisfactions show the same course satisfying nodes from both
    programs' requirement trees (the double-counting signal `optimizer_persistence`
    turns into multiple `requirement_allocations` rows for one `plan_course`)."""
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID, AERO_MINOR_PROGRAM_ID])
    ctx = _build_model(db_session, scenario)
    optimizer_objectives.set_primary_objective(ctx, OptimizationObjectiveType.MAX_REQUIREMENT_OVERLAP)

    status, solver = _solve(ctx)

    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    node_ids_by_course_id = _index_node_ids_by_course_id(optimizer_model.collect_leaf_satisfactions(ctx, solver))
    shared_courses = {cid: node_ids for cid, node_ids in node_ids_by_course_id.items() if len(node_ids) > 1}
    assert len(shared_courses) > 0, "expected at least one course to satisfy 2+ requirement nodes"


def _index_node_ids_by_course_id(leaf_satisfactions: dict[int, set[int]]) -> dict[int, set[int]]:
    """Invert a {requirement_node_id: {course_id, ...}} map into {course_id: {requirement_node_id, ...}}."""
    node_ids_by_course_id: dict[int, set[int]] = {}
    for node_id, course_ids in leaf_satisfactions.items():
        for course_id in course_ids:
            node_ids_by_course_id.setdefault(course_id, set()).add(node_id)
    return node_ids_by_course_id
