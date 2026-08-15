"""Public entrypoint for Phase 3: `generate_plans(db, planning_scenario_id)` builds one
CP-SAT model per scenario, re-solves it once per supported `OptimizationObjectiveType`
(§3.3), and returns plain, deduplicated `GeneratedPlan` result objects -- not yet
persisted (see `optimizer_persistence` for that)."""

from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.models.enums import OptimizationObjectiveType, ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_program import ScenarioProgram
from app.models.term import Term
from app.schemas.course import CourseOut
from app.services import optimizer_candidates, optimizer_model, optimizer_objectives, optimizer_terms
from app.services.optimizer_model import OptimizerModel

DEFAULT_MAX_SOLVE_SECONDS = 30.0
_FEASIBLE_STATUSES = (cp_model.OPTIMAL, cp_model.FEASIBLE)
_STATUS_NAMES = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.UNKNOWN: "UNKNOWN",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
}


@dataclass(frozen=True)
class GeneratedPlan:
    """One candidate degree plan the solver produced for a specific strategy: which
    objective it was solved for, its course/term assignments (empty if infeasible),
    and everything `optimizer_persistence` needs to write it out."""

    strategy_code: str
    objective_type: OptimizationObjectiveType | None
    status: str
    assignments: dict[int, int]
    courses_by_id: dict[int, CourseOut]
    total_credit_hours: float
    additional_credit_hours: float | None
    projected_graduation_term_id: int | None
    node_satisfaction: dict[int, bool]
    node_satisfying_course_ids: dict[int, set[int]]
    credit_requirement_node_ids: set[int]
    unmodeled_prerequisite_course_ids: set[int]
    unmodeled_prerequisite_node_ids: set[int]
    infeasibility_reason: str | None


def generate_plans(
    db: Session, planning_scenario_id: int, max_solve_seconds: float = DEFAULT_MAX_SOLVE_SECONDS
) -> list[GeneratedPlan]:
    """Generate up to 5 meaningfully-different degree plans for one planning scenario,
    one per supported `OptimizationObjectiveType`, deduplicated by identical assignments.
    Returns a single infeasible `GeneratedPlan` if the scenario's hard constraints alone
    (independent of any objective) can't be satisfied."""
    scenario = _load_scenario(db, planning_scenario_id)
    terms = optimizer_terms.build_term_horizon(db, scenario)
    candidates = optimizer_candidates.build_candidate_course_set(db, scenario)
    ctx = optimizer_model.build_optimizer_model(db, scenario, candidates, terms)
    feasibility_status = _new_solver(max_solve_seconds).Solve(ctx.model)
    if feasibility_status not in _FEASIBLE_STATUSES:
        return [_infeasible_plan(None, "INFEASIBLE", feasibility_status)]
    baseline_credit_hours = _solve_baseline_credit_hours(db, scenario, terms, max_solve_seconds)
    return _solve_every_objective(ctx, baseline_credit_hours, max_solve_seconds)


def _load_scenario(db: Session, planning_scenario_id: int) -> PlanningScenario:
    """Look up a planning scenario by id, raising `ValueError` if it doesn't exist."""
    scenario = db.get(PlanningScenario, planning_scenario_id)
    if scenario is None:
        raise ValueError(f"planning_scenario_id {planning_scenario_id} not found")
    return scenario


def _new_solver(max_solve_seconds: float) -> cp_model.CpSolver:
    """Build a `CpSolver` configured with the given wall-clock time limit."""
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_solve_seconds
    return solver


def _status_name(status: int) -> str:
    """Return a human-readable name for a CP-SAT solver status code."""
    return _STATUS_NAMES.get(status, "UNKNOWN")


def _solve_baseline_credit_hours(
    db: Session, scenario: PlanningScenario, terms: list[Term], max_solve_seconds: float
) -> float | None:
    """Solve a 'primary major alone' baseline (only meaningful with 2+ scenario_programs)
    and return its minimal total credit hours, or `None` for a single-program scenario."""
    primary_program_id = _primary_program_id(db, scenario.planning_scenario_id)
    if primary_program_id is None:
        return None
    baseline_candidates = optimizer_candidates.build_candidate_course_set(
        db, scenario, program_ids_override=[primary_program_id]
    )
    baseline_ctx = optimizer_model.build_optimizer_model(db, scenario, baseline_candidates, terms)
    baseline_ctx.model.Minimize(optimizer_objectives.total_assigned_credit_hours(baseline_ctx))
    solver = _new_solver(max_solve_seconds)
    status = solver.Solve(baseline_ctx.model)
    if status not in _FEASIBLE_STATUSES:
        return None
    return solver.ObjectiveValue() / 10.0


def _primary_program_id(db: Session, planning_scenario_id: int) -> int | None:
    """Return the scenario's PRIMARY_MAJOR academic_program_id, or `None` if the
    scenario has only one program (no baseline comparison is meaningful)."""
    scenario_programs = (
        db.query(ScenarioProgram).filter(ScenarioProgram.planning_scenario_id == planning_scenario_id).all()
    )
    if len(scenario_programs) <= 1:
        return None
    primary = next(
        (sp for sp in scenario_programs if sp.program_role == ScenarioProgramRole.PRIMARY_MAJOR), None
    )
    return primary.academic_program_id if primary else None


def _solve_every_objective(
    ctx: OptimizerModel, baseline_credit_hours: float | None, max_solve_seconds: float
) -> list[GeneratedPlan]:
    """Re-solve the shared model once per supported objective type, keeping only the
    plans whose course/term assignments aren't an exact duplicate of an earlier one."""
    plans: list[GeneratedPlan] = []
    seen_signatures: set[frozenset] = set()
    for objective_type in optimizer_objectives.SUPPORTED_OBJECTIVE_TYPES:
        plan = _solve_one_objective(ctx, objective_type, baseline_credit_hours, max_solve_seconds)
        signature = frozenset(plan.assignments.items())
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        plans.append(plan)
    return plans


def _solve_one_objective(
    ctx: OptimizerModel,
    objective_type: OptimizationObjectiveType,
    baseline_credit_hours: float | None,
    max_solve_seconds: float,
) -> GeneratedPlan:
    """Set one objective type as primary on the shared model, solve, and package the result."""
    optimizer_objectives.set_primary_objective(ctx, objective_type)
    solver = _new_solver(max_solve_seconds)
    status = solver.Solve(ctx.model)
    strategy_code = objective_type.value
    if status not in _FEASIBLE_STATUSES:
        return _infeasible_plan(objective_type, strategy_code, status)
    return _build_generated_plan(ctx, solver, objective_type, strategy_code, status, baseline_credit_hours)


def _build_generated_plan(
    ctx: OptimizerModel,
    solver: cp_model.CpSolver,
    objective_type: OptimizationObjectiveType,
    strategy_code: str,
    status: int,
    baseline_credit_hours: float | None,
) -> GeneratedPlan:
    """Read a solved model's variable values back into a plain `GeneratedPlan` result."""
    assignments = {
        course_id: term_id for (course_id, term_id), var in ctx.assign.items() if solver.Value(var) == 1
    }
    courses_by_id = {course_id: ctx.candidates.courses_by_id[course_id] for course_id in assignments}
    total_credit_hours = sum(course.credit_hours for course in courses_by_id.values())
    node_satisfaction = {
        node_id: bool(solver.Value(indicator)) for node_id, indicator in ctx.node_indicators.items()
    }
    additional_credit_hours = (
        total_credit_hours - baseline_credit_hours if baseline_credit_hours is not None else None
    )
    return GeneratedPlan(
        strategy_code=strategy_code,
        objective_type=objective_type,
        status=_status_name(status),
        assignments=assignments,
        courses_by_id=courses_by_id,
        total_credit_hours=total_credit_hours,
        additional_credit_hours=additional_credit_hours,
        projected_graduation_term_id=_latest_used_term_id(ctx, assignments),
        node_satisfaction=node_satisfaction,
        node_satisfying_course_ids=optimizer_model.collect_leaf_satisfactions(ctx, solver),
        credit_requirement_node_ids=set(ctx.credit_requirement_node_ids),
        unmodeled_prerequisite_course_ids=set(ctx.unmodeled_prerequisite_course_ids),
        unmodeled_prerequisite_node_ids=set(ctx.unmodeled_prerequisite_node_ids),
        infeasibility_reason=None,
    )


def _latest_used_term_id(ctx: OptimizerModel, assignments: dict[int, int]) -> int | None:
    """Return the term_id with the highest sequence_index among a plan's assignments."""
    if not assignments:
        return None
    term_by_id = {term.term_id: term for term in ctx.terms}
    used_term_ids = set(assignments.values())
    return max(used_term_ids, key=lambda term_id: term_by_id[term_id].sequence_index)


def _infeasible_plan(
    objective_type: OptimizationObjectiveType | None, strategy_code: str, status: int
) -> GeneratedPlan:
    """Build a placeholder `GeneratedPlan` carrying an infeasibility reason instead of assignments."""
    return GeneratedPlan(
        strategy_code=strategy_code,
        objective_type=objective_type,
        status=_status_name(status),
        assignments={},
        courses_by_id={},
        total_credit_hours=0.0,
        additional_credit_hours=None,
        projected_graduation_term_id=None,
        node_satisfaction={},
        node_satisfying_course_ids={},
        credit_requirement_node_ids=set(),
        unmodeled_prerequisite_course_ids=set(),
        unmodeled_prerequisite_node_ids=set(),
        infeasibility_reason=_infeasibility_reason(status),
    )


def _infeasibility_reason(status: int) -> str:
    """Return a plain-language explanation for a non-feasible solver status, for
    an `optimization_messages` row."""
    if status == cp_model.INFEASIBLE:
        return (
            "No schedule satisfies every hard constraint (requirements, prerequisites, "
            "term credit limits, and any fixed target graduation term) for this scenario."
        )
    return "The solver could not find or verify a feasible schedule within the time limit."
