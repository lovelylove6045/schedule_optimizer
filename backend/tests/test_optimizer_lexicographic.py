"""Focused regression tests for true ordered-objective locking and hard deadlines."""

import time
from types import SimpleNamespace

from ortools.sat.python import cp_model

from app.models.enums import OptimizationObjectiveType
from app.services import optimizer_objectives, optimizer_service


def _conflicting_context():
    """Build a tiny model where earliest and balance must choose opposite solutions."""
    model = cp_model.CpModel()
    earliest_cost = model.NewBoolVar("earliest_cost")
    balance_cost = model.NewBoolVar("balance_cost")
    model.Add(earliest_cost + balance_cost == 1)
    context = SimpleNamespace(model=model, scenario=SimpleNamespace(planning_scenario_id=-1), assign={})
    return context, earliest_cost, balance_cost


def test_lexicographic_priority_reversal_changes_recommended_solution(monkeypatch):
    """Lock the first objective so reversing two conflicting priorities reverses the result."""
    def solve(order):
        """Solve the tiny conflicting model with one requested priority order."""
        context, earliest_cost, balance_cost = _conflicting_context()
        expressions = {
            OptimizationObjectiveType.EARLIEST_GRADUATION: earliest_cost,
            OptimizationObjectiveType.BALANCED_WORKLOAD: balance_cost,
        }
        monkeypatch.setattr(
            "app.services.optimizer_objectives.minimize_expression",
            lambda _ctx, objective: expressions[objective],
        )
        monkeypatch.setattr("app.services.optimizer_objectives.early_advanced_course_penalty", lambda _ctx: 0)
        monkeypatch.setattr("app.services.optimizer_objectives.academic_quality_tiebreaker", lambda _ctx: 0)
        status, solver, _ = optimizer_service._solve_lexicographic(context, order, time.monotonic() + 2)
        assert status == cp_model.OPTIMAL
        return solver.Value(earliest_cost), solver.Value(balance_cost)
    earliest_first = solve(
        [OptimizationObjectiveType.EARLIEST_GRADUATION, OptimizationObjectiveType.BALANCED_WORKLOAD]
    )
    balance_first = solve(
        [OptimizationObjectiveType.BALANCED_WORKLOAD, OptimizationObjectiveType.EARLIEST_GRADUATION]
    )
    assert earliest_first == (0, 1)
    assert balance_first == (1, 0)


def test_remaining_seconds_never_grants_time_after_deadline():
    """Return zero after the global deadline instead of the old extra 20-second floor."""
    assert optimizer_service._remaining_seconds(time.monotonic() - 1) == 0


def test_inapplicable_objectives_are_skipped_for_single_program_without_summer():
    """Skip overlap and summer priorities when neither can distinguish solutions."""
    context = SimpleNamespace(
        terms=[SimpleNamespace(term_type="FALL")],
        candidates=SimpleNamespace(course_ids_by_program={1: {10}}),
    )
    result = optimizer_objectives.applicable_objective_types(context)
    assert OptimizationObjectiveType.MAX_REQUIREMENT_OVERLAP not in result
    assert OptimizationObjectiveType.MIN_SUMMER_ENROLLMENT not in result


def test_feasible_stage_status_is_preserved_instead_of_reported_as_optimal(monkeypatch):
    """Keep CP-SAT's FEASIBLE proof status through every lexicographic stage."""
    class FeasibleSolver:
        """Provide the small CpSolver surface used by the staged solver."""
        def Solve(self, _model):
            """Return FEASIBLE without claiming optimality."""
            return cp_model.FEASIBLE
        def Value(self, _expression):
            """Return the achieved value used for the next equality lock."""
            return 0
        def WallTime(self):
            """Return a deterministic duration for diagnostics."""
            return 0.0
    context, earliest_cost, _balance_cost = _conflicting_context()
    context.model.Add(earliest_cost == 0)
    monkeypatch.setattr(optimizer_service, "_new_solver", lambda _seconds: FeasibleSolver())
    monkeypatch.setattr(optimizer_objectives, "minimize_expression", lambda _ctx, _objective: earliest_cost)
    monkeypatch.setattr(optimizer_objectives, "early_advanced_course_penalty", lambda _ctx: 0)
    monkeypatch.setattr(optimizer_objectives, "academic_quality_tiebreaker", lambda _ctx: 0)
    status, solver, stages = optimizer_service._solve_lexicographic(
        context,
        [OptimizationObjectiveType.EARLIEST_GRADUATION],
        time.monotonic() + 1,
    )
    assert status == cp_model.FEASIBLE
    assert solver is not None
    assert all(stage.endswith(":FEASIBLE") for stage in stages)


def test_horizon_exhaustion_has_a_distinct_infeasibility_message():
    """Distinguish the absolute planning-window limit from generic infeasibility."""
    assert "Planning horizon exhausted" in optimizer_service._horizon_exhaustion_reason()


def test_minimum_credit_stage_also_locks_the_fewest_course_count(monkeypatch):
    """Prevent zero-credit or variable-credit padding after minimum credits are fixed."""
    model = cp_model.CpModel()
    required = model.NewBoolVar("required")
    padding = model.NewBoolVar("padding")
    model.Add(required == 1)
    context = SimpleNamespace(
        model=model,
        scenario=SimpleNamespace(planning_scenario_id=-1),
        assign={(1, 1): required, (2, 1): padding},
    )
    monkeypatch.setattr(optimizer_objectives, "minimize_expression", lambda _ctx, _objective: 0)
    monkeypatch.setattr(optimizer_objectives, "total_assigned_course_count", lambda _ctx: required + padding)
    monkeypatch.setattr(optimizer_objectives, "early_advanced_course_penalty", lambda _ctx: 0)
    monkeypatch.setattr(optimizer_objectives, "academic_quality_tiebreaker", lambda _ctx: 0)
    status, solver, stages = optimizer_service._solve_lexicographic(
        context,
        [OptimizationObjectiveType.MIN_ADDITIONAL_CREDITS],
        time.monotonic() + 2,
    )
    assert status == cp_model.OPTIMAL
    assert solver is not None
    assert solver.Value(required) == 1
    assert solver.Value(padding) == 0
    assert "MIN_COURSE_COUNT:OPTIMAL" in stages


def test_expired_total_budget_starts_no_additional_solver_stage(monkeypatch):
    """Return promptly without granting a hidden minimum duration after the deadline."""
    context, _earliest_cost, _balance_cost = _conflicting_context()
    monkeypatch.setattr(
        optimizer_service,
        "_new_solver",
        lambda _seconds: (_ for _ in ()).throw(AssertionError("solver started after deadline")),
    )
    started_at = time.monotonic()
    status, solver, stages = optimizer_service._solve_lexicographic(
        context,
        [OptimizationObjectiveType.EARLIEST_GRADUATION],
        started_at,
    )
    assert time.monotonic() - started_at < 0.1
    assert status == cp_model.UNKNOWN
    assert solver is None
    assert stages == []
