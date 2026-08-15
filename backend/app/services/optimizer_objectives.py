"""Builds and sets the CP-SAT objective for one of the 5 supported
`OptimizationObjectiveType` values (docs/PHASES.md §3.2), on top of an
already-built `OptimizerModel` from `optimizer_model`. Per §3.3, each solve
picks one objective as primary (weighted heavily) and folds the other 4 in
as tie-breakers (weighted lightly) -- otherwise a lopsided objective like
MAX_REQUIREMENT_OVERLAP has no pressure against padding in unnecessary extra
courses, since nothing else discourages them. `MAX_INTEREST_ALIGNMENT` and
`PRESERVE_FLEXIBILITY` are out of scope (see the Phase 3 plan)."""

from __future__ import annotations

from ortools.sat.python import cp_model

from app.models.enums import OptimizationObjectiveType
from app.services.optimizer_model import (
    OptimizerModel,
    course_satisfaction_indicator,
    scaled_credits,
    term_used_indicator,
)

SUMMER_TERM_TYPE = "SUMMER"
PRIMARY_OBJECTIVE_WEIGHT = 100_000
TIE_BREAK_WEIGHT = 1
_HEAVIEST_TERM_CREDITS_UPPER_BOUND = scaled_credits(60.0)
SUPPORTED_OBJECTIVE_TYPES = (
    OptimizationObjectiveType.EARLIEST_GRADUATION,
    OptimizationObjectiveType.MIN_ADDITIONAL_CREDITS,
    OptimizationObjectiveType.MAX_REQUIREMENT_OVERLAP,
    OptimizationObjectiveType.BALANCED_WORKLOAD,
    OptimizationObjectiveType.MIN_SUMMER_ENROLLMENT,
)


def applicable_objective_types(ctx: OptimizerModel) -> tuple[OptimizationObjectiveType, ...]:
    """Return the subset of `SUPPORTED_OBJECTIVE_TYPES` that can actually discriminate
    between plans for *this* scenario.

    Two of the five are provably constant in common scenarios, and solving for them
    anyway costs a full CP-SAT run and produces an alternative plan whose stated
    rationale is meaningless to the student:

    * `MAX_REQUIREMENT_OVERLAP` -- `_overlap_score` rewards courses shared across two
      or more scenario *programs*, so it's identically zero with only one program.
    * `MIN_SUMMER_ENROLLMENT` -- `optimizer_terms.build_term_horizon` already drops
      SUMMER terms when the scenario disallows them, leaving nothing to minimize.
    """
    has_summer_terms = any(term.term_type == SUMMER_TERM_TYPE for term in ctx.terms)
    has_multiple_programs = len(ctx.candidates.course_ids_by_program) > 1
    skipped = set()
    if not has_multiple_programs:
        skipped.add(OptimizationObjectiveType.MAX_REQUIREMENT_OVERLAP)
    if not has_summer_terms:
        skipped.add(OptimizationObjectiveType.MIN_SUMMER_ENROLLMENT)
    return tuple(t for t in SUPPORTED_OBJECTIVE_TYPES if t not in skipped)


def set_primary_objective(ctx: OptimizerModel, objective_type: OptimizationObjectiveType) -> None:
    """Set the model's objective: `objective_type` weighted heavily, the other 4
    supported objective types folded in lightly as tie-breakers among otherwise-equal
    solutions."""
    minimize_expressions = {
        candidate_type: _minimize_expression(ctx, candidate_type)
        for candidate_type in SUPPORTED_OBJECTIVE_TYPES
    }
    combined = PRIMARY_OBJECTIVE_WEIGHT * minimize_expressions[objective_type] + sum(
        TIE_BREAK_WEIGHT * expression
        for candidate_type, expression in minimize_expressions.items()
        if candidate_type != objective_type
    )
    ctx.model.Minimize(combined)


def _minimize_expression(
    ctx: OptimizerModel, objective_type: OptimizationObjectiveType
) -> cp_model.LinearExpr:
    """Return one objective type's scoring expression, oriented so that lower is always
    better (a naturally-maximized objective, like overlap, is negated)."""
    if objective_type == OptimizationObjectiveType.EARLIEST_GRADUATION:
        return _graduation_index(ctx)
    if objective_type == OptimizationObjectiveType.MIN_ADDITIONAL_CREDITS:
        return total_assigned_credit_hours(ctx)
    if objective_type == OptimizationObjectiveType.MAX_REQUIREMENT_OVERLAP:
        return -_overlap_score(ctx)
    if objective_type == OptimizationObjectiveType.BALANCED_WORKLOAD:
        return _heaviest_term_credits(ctx)
    return _summer_credit_hours(ctx)


def total_assigned_credit_hours(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Return the linear expression for total scaled credit hours assigned across all terms."""
    return sum(ctx.term_credit_totals.values()) if ctx.term_credit_totals else 0


def _graduation_index(ctx: OptimizerModel) -> cp_model.IntVar:
    """Build (once) an IntVar equal to the sequence_index of the latest used term
    in the horizon, 0 if no term ends up used."""
    if ctx.graduation_index_var is not None:
        return ctx.graduation_index_var
    max_index = max((term.sequence_index for term in ctx.terms), default=0)
    graduation_index = ctx.model.NewIntVar(0, max_index, "graduation_index")
    for term in ctx.terms:
        used = term_used_indicator(ctx, term)
        ctx.model.Add(graduation_index >= term.sequence_index).OnlyEnforceIf(used)
    ctx.graduation_index_var = graduation_index
    return graduation_index


def _overlap_score(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Return the linear expression rewarding each course for every program beyond its
    first that it helps satisfy (genuine cross-program double counting, UC-15). Zero for
    a single-program scenario by construction -- there's no second program to share with."""
    program_counts = _course_program_counts(ctx)
    terms = [
        (count - 1) * course_satisfaction_indicator(ctx, course_id)
        for course_id, count in program_counts.items()
        if count > 1
    ]
    return sum(terms) if terms else 0


def _course_program_counts(ctx: OptimizerModel) -> dict[int, int]:
    """Return, for each course id, how many distinct scenario programs reference it."""
    counts: dict[int, int] = {}
    for course_ids in ctx.candidates.course_ids_by_program.values():
        for course_id in course_ids:
            counts[course_id] = counts.get(course_id, 0) + 1
    return counts


def _heaviest_term_credits(ctx: OptimizerModel) -> cp_model.IntVar:
    """Build (once) an IntVar equal to the maximum of every term's credit-hour total
    (a simpler proxy for variance-based balancing, matching UC-43's 'based primarily
    on credit totals')."""
    if ctx.heaviest_term_credits_var is not None:
        return ctx.heaviest_term_credits_var
    heaviest = ctx.model.NewIntVar(0, _HEAVIEST_TERM_CREDITS_UPPER_BOUND, "heaviest_term_credits")
    for total in ctx.term_credit_totals.values():
        ctx.model.Add(heaviest >= total)
    ctx.heaviest_term_credits_var = heaviest
    return heaviest


def _summer_credit_hours(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Return the linear expression for total scaled credit hours assigned to SUMMER terms."""
    summer_term_ids = {term.term_id for term in ctx.terms if term.term_type == SUMMER_TERM_TYPE}
    terms = [total for term_id, total in ctx.term_credit_totals.items() if term_id in summer_term_ids]
    return sum(terms) if terms else 0
