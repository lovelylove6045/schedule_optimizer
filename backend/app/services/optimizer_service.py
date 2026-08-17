"""Generate a lexicographic recommended plan and independent strategy alternatives."""

from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.models.enums import OptimizationObjectiveType, ScenarioProgramRole
from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_objective import ScenarioObjective
from app.models.term import Term
from app.schemas.course import CourseOut
from app.services import optimizer_candidates, optimizer_model, optimizer_objectives, optimizer_terms
from app.services.optimizer_model import OptimizerModel

logger = logging.getLogger(__name__)

# One hard wall-clock budget is shared by every stage in a generation operation.
DEFAULT_MAX_TOTAL_SOLVE_SECONDS = 270.0
# A relative gap is deliberately omitted: lexicographic stages record CP-SAT's exact
# OPTIMAL/FEASIBLE proof status and use only the achieved value for the next lock.
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
    objective_stage_results: tuple[str, ...] = ()
    candidate_course_count: int = 0
    assignment_variable_count: int = 0
    solver_wall_time_seconds: float = 0.0
    deadline_exhausted: bool = False


def generate_plans(
    db: Session, planning_scenario_id: int, max_total_solve_seconds: float = DEFAULT_MAX_TOTAL_SOLVE_SECONDS
) -> list[GeneratedPlan]:
    """Return the recommended plan followed by semantically distinct alternatives."""
    recommended = generate_recommended_plan(db, planning_scenario_id, max_total_solve_seconds)
    if recommended.infeasibility_reason is not None:
        return [recommended]
    recommended = dataclasses.replace(
        recommended,
        strategy_code=recommended.objective_type.value if recommended.objective_type else "RECOMMENDED",
    )
    remaining_budget = max(max_total_solve_seconds - recommended.solver_wall_time_seconds, 0.0)
    alternatives = generate_alternative_plans(
        db, planning_scenario_id, remaining_budget, excluded_signatures={_plan_signature(recommended)}
    )
    return [recommended, *alternatives]


def generate_recommended_plan(
    db: Session,
    planning_scenario_id: int,
    max_total_solve_seconds: float = DEFAULT_MAX_TOTAL_SOLVE_SECONDS,
) -> GeneratedPlan:
    """Solve the scenario's ordered priorities lexicographically and return one plan."""
    started_at = time.monotonic()
    deadline = started_at + max(max_total_solve_seconds, 0.0)
    scenario = _load_scenario(db, planning_scenario_id)
    ctx = _build_context(db, scenario, optimizer_terms.DEFAULT_MAX_HORIZON_TERMS)
    stages = _recommended_objective_order(db, planning_scenario_id, ctx)
    solved = _solve_lexicographic(ctx, stages, deadline)
    expanded_horizon = False
    if (
        solved[0] == cp_model.INFEASIBLE
        and scenario.target_graduation_term_id is None
        and _remaining_seconds(deadline) > 0
    ):
        expanded_horizon = True
        ctx = _build_context(db, scenario, optimizer_terms.ABSOLUTE_MAX_HORIZON_TERMS)
        solved = _solve_lexicographic(ctx, stages, deadline)
    status, solver, stage_results = solved
    if status not in _FEASIBLE_STATUSES or solver is None:
        elapsed = time.monotonic() - started_at
        plan = _infeasible_plan(None, "RECOMMENDED", status)
        if expanded_horizon and status == cp_model.INFEASIBLE:
            plan = dataclasses.replace(plan, infeasibility_reason=_horizon_exhaustion_reason())
        return dataclasses.replace(plan, solver_wall_time_seconds=elapsed, deadline_exhausted=_remaining_seconds(deadline) <= 0)
    baseline = _solve_baseline_credit_hours(db, scenario, ctx.terms, deadline)
    elapsed = time.monotonic() - started_at
    plan = _build_generated_plan(
        ctx, solver, stages[0] if stages else None, "RECOMMENDED", status, baseline
    )
    return dataclasses.replace(
        plan,
        objective_stage_results=tuple(stage_results),
        candidate_course_count=len(ctx.candidates.assignable_course_ids),
        assignment_variable_count=len(ctx.assign),
        solver_wall_time_seconds=elapsed,
        deadline_exhausted=_remaining_seconds(deadline) <= 0,
    )


def generate_alternative_plans(
    db: Session,
    planning_scenario_id: int,
    max_total_solve_seconds: float = DEFAULT_MAX_TOTAL_SOLVE_SECONDS,
    excluded_signatures: set[frozenset] | None = None,
) -> list[GeneratedPlan]:
    """Generate independent strategy alternatives while honoring one hard shared deadline."""
    if max_total_solve_seconds <= 0:
        return []
    scenario = _load_scenario(db, planning_scenario_id)
    deadline = time.monotonic() + max_total_solve_seconds
    ctx = _build_context(db, scenario, optimizer_terms.DEFAULT_MAX_HORIZON_TERMS)
    baseline = _solve_baseline_credit_hours(db, scenario, ctx.terms, deadline)
    plans: list[GeneratedPlan] = []
    seen = set(excluded_signatures or set())
    semantic_seen = _persisted_semantic_signatures(db, planning_scenario_id)
    objective_types = optimizer_objectives.applicable_objective_types(ctx)
    for index, objective_type in enumerate(objective_types):
        if _remaining_seconds(deadline) <= 0:
            break
        objective_ctx = ctx if index == 0 else _build_context(
            db, scenario, optimizer_terms.DEFAULT_MAX_HORIZON_TERMS
        )
        plan = _solve_one_objective(objective_ctx, objective_type, baseline, deadline)
        if plan.infeasibility_reason is not None:
            continue
        signature = _plan_signature(plan)
        semantic_signature = _semantic_plan_signature(plan)
        if signature in seen or semantic_signature in semantic_seen:
            continue
        seen.add(signature)
        semantic_seen.add(semantic_signature)
        plans.append(plan)
    return plans


def _build_context(
    db: Session, scenario: PlanningScenario, maximum_terms: int
) -> OptimizerModel:
    """Build one solver context using the requested horizon size."""
    terms = optimizer_terms.build_term_horizon(db, scenario, maximum_terms)
    candidates = optimizer_candidates.build_candidate_course_set(db, scenario)
    ctx = optimizer_model.build_optimizer_model(db, scenario, candidates, terms)
    logger.info(
        "optimizer_model_built scenario_id=%s candidates=%s assignment_variables=%s terms=%s",
        scenario.planning_scenario_id,
        len(candidates.assignable_course_ids),
        len(ctx.assign),
        len(terms),
    )
    return ctx


def _recommended_objective_order(
    db: Session, planning_scenario_id: int, ctx: OptimizerModel
) -> list[OptimizationObjectiveType]:
    """Return applicable scenario priorities with a no-padding completion-size safeguard first."""
    rows = (
        db.query(ScenarioObjective)
        .filter(ScenarioObjective.planning_scenario_id == planning_scenario_id)
        .order_by(ScenarioObjective.display_order.asc().nulls_last(), ScenarioObjective.scenario_objective_id)
        .all()
    )
    applicable = set(optimizer_objectives.applicable_objective_types(ctx))
    requested = [row.objective_type for row in rows if row.objective_type in applicable]
    if not requested:
        requested = [OptimizationObjectiveType.EARLIEST_GRADUATION]
    credit_stage = OptimizationObjectiveType.MIN_ADDITIONAL_CREDITS
    return [credit_stage, *[objective for objective in requested if objective != credit_stage]]


def _solve_lexicographic(
    ctx: OptimizerModel, stages: list[OptimizationObjectiveType], deadline: float
) -> tuple[int, cp_model.CpSolver | None, list[str]]:
    """Optimize and lock each priority in order until the shared deadline expires."""
    last_status = cp_model.UNKNOWN
    last_solver: cp_model.CpSolver | None = None
    stage_results: list[str] = []
    for objective_type in stages:
        remaining = _remaining_seconds(deadline)
        if remaining <= 0:
            break
        expression = optimizer_objectives.minimize_expression(ctx, objective_type)
        ctx.model.Minimize(expression)
        solver = _new_solver(remaining)
        status = solver.Solve(ctx.model)
        logger.info(
            "optimizer_stage scenario_id=%s stage=%s status=%s wall_time=%.3f variables=%s",
            ctx.scenario.planning_scenario_id,
            objective_type.value,
            _status_name(status),
            solver.WallTime(),
            len(ctx.assign),
        )
        stage_results.append(f"{objective_type.value}:{_status_name(status)}")
        if status not in _FEASIBLE_STATUSES:
            if last_solver is not None:
                return last_status, last_solver, stage_results
            return status, None, stage_results
        achieved_value = round(solver.Value(expression))
        ctx.model.Add(expression == achieved_value)
        last_status = status if last_status == cp_model.OPTIMAL else last_status
        if last_solver is None or status == cp_model.FEASIBLE:
            last_status = status
        last_solver = solver
        if objective_type == OptimizationObjectiveType.MIN_ADDITIONAL_CREDITS:
            count_result = _lock_minimum_course_count(ctx, deadline)
            if count_result is not None:
                count_status, count_solver, count_label = count_result
                stage_results.append(count_label)
                if count_status not in _FEASIBLE_STATUSES or count_solver is None:
                    return last_status, last_solver, stage_results
                if count_status == cp_model.FEASIBLE:
                    last_status = count_status
                last_solver = count_solver
    tie_breakers = (
        ("AVOID_EARLY_5000_LEVEL", optimizer_objectives.early_advanced_course_penalty),
        ("ACADEMIC_QUALITY", optimizer_objectives.academic_quality_tiebreaker),
    )
    for stage_name, expression_factory in tie_breakers:
        remaining = _remaining_seconds(deadline)
        if remaining <= 0:
            break
        expression = expression_factory(ctx)
        ctx.model.Minimize(expression)
        solver = _new_solver(remaining)
        status = solver.Solve(ctx.model)
        stage_results.append(f"{stage_name}:{_status_name(status)}")
        if status not in _FEASIBLE_STATUSES:
            break
        ctx.model.Add(expression == round(solver.Value(expression)))
        if status == cp_model.FEASIBLE:
            last_status = status
        last_solver = solver
    if last_solver is None:
        return cp_model.UNKNOWN, None, stage_results
    return last_status, last_solver, stage_results


def _lock_minimum_course_count(
    ctx: OptimizerModel, deadline: float
) -> tuple[int, cp_model.CpSolver | None, str] | None:
    """Minimize and lock course count after the minimum-credit value is fixed."""
    remaining = _remaining_seconds(deadline)
    if remaining <= 0:
        return None
    expression = optimizer_objectives.total_assigned_course_count(ctx)
    ctx.model.Minimize(expression)
    solver = _new_solver(remaining)
    status = solver.Solve(ctx.model)
    logger.info(
        "optimizer_stage scenario_id=%s stage=MIN_COURSE_COUNT status=%s wall_time=%.3f variables=%s",
        ctx.scenario.planning_scenario_id,
        _status_name(status),
        solver.WallTime(),
        len(ctx.assign),
    )
    label = f"MIN_COURSE_COUNT:{_status_name(status)}"
    if status not in _FEASIBLE_STATUSES:
        return status, None, label
    ctx.model.Add(expression == round(solver.Value(expression)))
    return status, solver, label


def _plan_signature(plan: GeneratedPlan) -> frozenset:
    """Return an exact assignment signature used for alternative deduplication."""
    return frozenset(plan.assignments.items())


def _semantic_plan_signature(plan: GeneratedPlan) -> tuple[frozenset[int], int | None, int]:
    """Return a signature that ignores inconsequential within-horizon term shuffling."""
    return (
        frozenset(plan.assignments),
        plan.projected_graduation_term_id,
        round(plan.total_credit_hours * 10),
    )


def _persisted_semantic_signatures(
    db: Session, planning_scenario_id: int
) -> set[tuple[frozenset[int], int | None, int]]:
    """Return semantic signatures for already-persisted plans in this scenario."""
    plans = db.query(DegreePlan).filter(
        DegreePlan.planning_scenario_id == planning_scenario_id
    ).all()
    signatures: set[tuple[frozenset[int], int | None, int]] = set()
    for plan in plans:
        course_ids = frozenset(
            course_id
            for (course_id,) in db.query(PlanCourse.course_id).filter(
                PlanCourse.degree_plan_id == plan.degree_plan_id
            ).all()
        )
        signatures.add(
            (course_ids, plan.projected_graduation_term_id, round(float(plan.total_credit_hours or 0) * 10))
        )
    return signatures


def _remaining_seconds(deadline: float) -> float:
    """Return non-negative wall-clock seconds left before the hard deadline."""
    return max(deadline - time.monotonic(), 0.0)


def _load_scenario(db: Session, planning_scenario_id: int) -> PlanningScenario:
    """Look up a planning scenario by id, raising `ValueError` if it doesn't exist."""
    scenario = db.get(PlanningScenario, planning_scenario_id)
    if scenario is None:
        raise ValueError(f"planning_scenario_id {planning_scenario_id} not found")
    return scenario


def _new_solver(max_solve_seconds: float) -> cp_model.CpSolver:
    """Build a `CpSolver` with this project's shared search settings: a wall-clock limit
    plus CP-SAT's portfolio search across 8 workers. The default is a single worker, and
    these models are big enough (thousands of assignment booleans) that parallel search
    reaches a comparable plan in roughly half the wall-clock time."""
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_solve_seconds
    solver.parameters.num_workers = 8
    return solver


def _status_name(status: int) -> str:
    """Return a human-readable name for a CP-SAT solver status code."""
    return _STATUS_NAMES.get(status, "UNKNOWN")


def _solve_baseline_credit_hours(
    db: Session, scenario: PlanningScenario, terms: list[Term], deadline: float
) -> float | None:
    """Solve a 'primary major alone' baseline (only meaningful with 2+ scenario_programs)
    and return its minimal total credit hours, or `None` for a single-program scenario."""
    primary_program_id = _primary_program_id(db, scenario.planning_scenario_id)
    if primary_program_id is None or _remaining_seconds(deadline) <= 0:
        return None
    baseline_candidates = optimizer_candidates.build_candidate_course_set(
        db, scenario, program_ids_override=[primary_program_id]
    )
    baseline_ctx = optimizer_model.build_optimizer_model(db, scenario, baseline_candidates, terms)
    baseline_ctx.model.Minimize(optimizer_objectives.total_assigned_credit_hours(baseline_ctx))
    solver = _new_solver(_remaining_seconds(deadline))
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


def _solve_one_objective(
    ctx: OptimizerModel,
    objective_type: OptimizationObjectiveType,
    baseline_credit_hours: float | None,
    deadline: float,
) -> GeneratedPlan:
    """Solve one strategy after first locking the minimum necessary coursework."""
    started_at = time.monotonic()
    strategy_code = objective_type.value
    credit_stage = OptimizationObjectiveType.MIN_ADDITIONAL_CREDITS
    stages = [credit_stage] if objective_type == credit_stage else [credit_stage, objective_type]
    status, solver, stage_results = _solve_lexicographic(ctx, stages, deadline)
    elapsed = time.monotonic() - started_at
    if status not in _FEASIBLE_STATUSES or solver is None:
        plan = _infeasible_plan(objective_type, strategy_code, status)
    else:
        plan = _build_generated_plan(
            ctx, solver, objective_type, strategy_code, status, baseline_credit_hours
        )
    return dataclasses.replace(
        plan,
        objective_stage_results=tuple(stage_results),
        candidate_course_count=len(ctx.candidates.assignable_course_ids),
        assignment_variable_count=len(ctx.assign),
        solver_wall_time_seconds=elapsed,
        deadline_exhausted=_remaining_seconds(deadline) <= 0,
    )


def _build_generated_plan(
    ctx: OptimizerModel,
    solver: cp_model.CpSolver,
    objective_type: OptimizationObjectiveType | None,
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
    selected_course_ids = set(assignments)
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
        unmodeled_prerequisite_course_ids=_selected_diagnostic_ids(
            ctx.unmodeled_prerequisite_course_ids_by_target, selected_course_ids
        ),
        unmodeled_prerequisite_node_ids=_selected_diagnostic_ids(
            ctx.unmodeled_prerequisite_node_ids_by_target, selected_course_ids
        ),
        infeasibility_reason=None,
    )


def _selected_diagnostic_ids(
    ids_by_course: dict[int, set[int]], selected_course_ids: set[int]
) -> set[int]:
    """Return diagnostic ids associated with courses selected in the solved plan."""
    return {
        diagnostic_id
        for course_id in selected_course_ids
        for diagnostic_id in ids_by_course.get(course_id, set())
    }


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


def _horizon_exhaustion_reason() -> str:
    """Return the distinct message used after the longest supported horizon fails."""
    return (
        "Planning horizon exhausted: no schedule fits within the supported 12-year "
        "window. Academic requirements or other hard constraints may also conflict."
    )
