"""Regression tests for transparent workload and course-level tie-breakers."""

from types import SimpleNamespace

from ortools.sat.python import cp_model

from app.services import optimizer_objectives


def _solve(model: cp_model.CpModel) -> cp_model.CpSolver:
    """Solve a tiny deterministic objective fixture and require optimality."""
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    assert status == cp_model.OPTIMAL
    return solver


def test_balanced_workload_prefers_twelve_twelve_twelve_over_fifteen_fifteen_six():
    """Prefer the lower peak when equal total credits can be distributed evenly."""
    model = cp_model.CpModel()
    uneven = model.NewBoolVar("uneven")
    context = SimpleNamespace(
        model=model,
        term_credit_totals={1: 120 + 30 * uneven, 2: 120 + 30 * uneven, 3: 120 - 60 * uneven},
        heaviest_term_credits_var=None,
        candidates=SimpleNamespace(assignable_course_ids=set(), course_level_by_course_id={}),
        terms=[SimpleNamespace(term_id=1), SimpleNamespace(term_id=2), SimpleNamespace(term_id=3)],
        assign={},
    )
    model.Minimize(optimizer_objectives._balanced_workload_score(context))
    solver = _solve(model)
    assert solver.Value(uneven) == 0


def test_early_advanced_tiebreaker_avoids_optional_5000_level_course():
    """Choose an equivalent lower-level option over an early 5000-level option."""
    model = cp_model.CpModel()
    lower = model.NewBoolVar("lower")
    advanced = model.NewBoolVar("advanced")
    model.Add(lower + advanced == 1)
    context = SimpleNamespace(
        model=model,
        terms=[SimpleNamespace(term_id=1, term_type="FALL")],
        assign={(10, 1): lower, (20, 1): advanced},
        candidates=SimpleNamespace(course_level_by_course_id={10: 4000, 20: 5000}),
    )
    model.Minimize(optimizer_objectives.early_advanced_course_penalty(context))
    solver = _solve(model)
    assert solver.Value(lower) == 1
    assert solver.Value(advanced) == 0


def test_required_early_5000_level_course_remains_feasible():
    """Keep the early-advanced rule soft when a 5000-level course is mandatory."""
    model = cp_model.CpModel()
    advanced = model.NewBoolVar("required_advanced")
    model.Add(advanced == 1)
    context = SimpleNamespace(
        model=model,
        terms=[SimpleNamespace(term_id=1, term_type="FALL")],
        assign={(20, 1): advanced},
        candidates=SimpleNamespace(course_level_by_course_id={20: 5000}),
    )
    model.Minimize(optimizer_objectives.early_advanced_course_penalty(context))
    solver = _solve(model)
    assert solver.Value(advanced) == 1


def test_overlap_score_uses_actual_allocations_in_distinct_requirement_sets():
    """Reward one course only when solved usage spans two meaningful requirement sets."""
    model = cp_model.CpModel()
    first_usage = model.NewBoolVar("first_set_usage")
    second_usage = model.NewBoolVar("second_set_usage")
    model.Add(first_usage == 1)
    model.Add(second_usage == 1)
    context = SimpleNamespace(
        model=model,
        node_course_usage_indicators={(101, 10): first_usage, (202, 10): second_usage},
        candidates=SimpleNamespace(
            requirement_set_id_by_node_id={101: 1, 202: 2},
            program_ids_by_requirement_set={1: {10}, 2: {20}},
        ),
    )
    score = optimizer_objectives._overlap_score(context)
    model.Maximize(score)
    solver = _solve(model)
    assert solver.Value(score) == 1


def test_inherited_parent_requirement_set_does_not_create_emphasis_overlap():
    """Avoid counting two nodes in one inherited set as parent/emphasis sharing."""
    model = cp_model.CpModel()
    first_usage = model.NewBoolVar("parent_usage")
    inherited_usage = model.NewBoolVar("inherited_emphasis_usage")
    model.Add(first_usage == 1)
    model.Add(inherited_usage == 1)
    context = SimpleNamespace(
        model=model,
        node_course_usage_indicators={(101, 10): first_usage, (102, 10): inherited_usage},
        candidates=SimpleNamespace(
            requirement_set_id_by_node_id={101: 1, 102: 1},
            program_ids_by_requirement_set={1: {10, 20}},
        ),
    )
    assert optimizer_objectives._overlap_score(context) == 0
