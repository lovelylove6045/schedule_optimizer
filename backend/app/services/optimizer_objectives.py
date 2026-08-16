"""Builds and sets the CP-SAT objective for one of the 5 supported
`OptimizationObjectiveType` values on top of an `OptimizerModel`. The service
optimizes these expressions one stage at a time and locks each achieved value,
so no arbitrary weighted sum can let a lower priority degrade a higher one."""

from __future__ import annotations

from ortools.sat.python import cp_model
from sqlalchemy import func

from app.models.enums import OptimizationObjectiveType
from app.models.enums import ScenarioPreferenceType, ScenarioProgramRole
from app.models.academic_program import AcademicProgram
from app.models.course_rule_node import CourseRuleNode
from app.models.scenario_preference import ScenarioPreference
from app.models.scenario_program import ScenarioProgram
from app.models.subject import Subject
from app.services.optimizer_model import (
    OptimizerModel,
    course_satisfaction_indicator,
    scaled_credits,
    term_used_indicator,
)

SUMMER_TERM_TYPE = "SUMMER"
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
    between plans for *this* scenario. Two of the five are provably constant in common scenarios, and solving for them
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
    """Set exactly one objective expression for a standalone alternative solve."""
    ctx.model.Minimize(minimize_expression(ctx, objective_type))


def minimize_expression(
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
        return _balanced_workload_score(ctx)
    return _summer_credit_hours(ctx)


def total_assigned_credit_hours(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Return the linear expression for total scaled credit hours assigned across all terms."""
    return sum(ctx.term_credit_totals.values()) if ctx.term_credit_totals else 0


def total_assigned_course_count(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Return the number of distinct future courses selected by the plan."""
    indicators = [course_satisfaction_indicator(ctx, course_id) for course_id in ctx.candidates.assignable_course_ids]
    return sum(indicators) if indicators else 0


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
    """Reward actual allocation across exclusive requirements of multiple programs."""
    usage_by_course_and_program: dict[tuple[int, int], list[cp_model.IntVar]] = {}
    for (node_id, course_id), usage in ctx.node_course_usage_indicators.items():
        requirement_set_id = ctx.candidates.requirement_set_id_by_node_id.get(node_id)
        owners = ctx.candidates.program_ids_by_requirement_set.get(requirement_set_id, set())
        if len(owners) == 1:
            program_id = next(iter(owners))
            usage_by_course_and_program.setdefault((course_id, program_id), []).append(usage)
    program_used_by_course: dict[int, list[cp_model.IntVar]] = {}
    for (course_id, _program_id), usages in usage_by_course_and_program.items():
        program_used = ctx.model.NewBoolVar(f"course_{course_id}_used_in_program")
        ctx.model.AddMaxEquality(program_used, usages)
        program_used_by_course.setdefault(course_id, []).append(program_used)
    overlap_terms = []
    for course_id, program_indicators in program_used_by_course.items():
        if len(program_indicators) < 2:
            continue
        any_used = ctx.model.NewBoolVar(f"course_{course_id}_used_any_program")
        ctx.model.AddMaxEquality(any_used, program_indicators)
        overlap_terms.append(sum(program_indicators) - any_used)
    return sum(overlap_terms) if overlap_terms else 0


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


def _balanced_workload_score(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Balance maximum credits and clustering of 4000/5000-level courses."""
    return 10 * _heaviest_term_credits(ctx) + 15 * _maximum_high_level_course_count(ctx)


def _maximum_high_level_course_count(ctx: OptimizerModel) -> cp_model.IntVar:
    """Return the largest number of 4000/5000-level courses assigned in one term."""
    maximum = ctx.model.NewIntVar(0, len(ctx.candidates.assignable_course_ids), "maximum_high_level_count")
    for term in ctx.terms:
        high_level_assignments = [
            var
            for (course_id, term_id), var in ctx.assign.items()
            if term_id == term.term_id
            and ctx.candidates.course_level_by_course_id.get(course_id, 0) >= 4000
        ]
        ctx.model.Add(maximum >= sum(high_level_assignments))
    return maximum


def early_advanced_course_penalty(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Penalize optional 5000-level placement in the first two regular planning terms."""
    regular_terms = [term for term in ctx.terms if term.term_type != SUMMER_TERM_TYPE][:2]
    early_term_ids = {term.term_id for term in regular_terms}
    penalties = [
        var
        for (course_id, term_id), var in ctx.assign.items()
        if term_id in early_term_ids
        and ctx.candidates.course_level_by_course_id.get(course_id, 0) >= 5000
    ]
    return sum(penalties) if penalties else 0


def academic_quality_tiebreaker(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Prefer soft course choices, primary-department value, and bottleneck sequencing."""
    preference_penalty = _soft_preference_penalty(ctx)
    department_reward = _primary_department_reward(ctx)
    sequencing_penalty = _bottleneck_sequencing_penalty(ctx)
    return preference_penalty - department_reward + sequencing_penalty


def _soft_preference_penalty(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Return penalties for avoided courses and rewards for preferred courses."""
    rows = ctx.db.query(ScenarioPreference).filter(
        ScenarioPreference.planning_scenario_id == ctx.scenario.planning_scenario_id,
        ScenarioPreference.preference_type.in_(
            (ScenarioPreferenceType.PREFER_COURSE, ScenarioPreferenceType.AVOID_COURSE)
        ),
        ScenarioPreference.course_id.isnot(None),
    ).all()
    terms = []
    for row in rows:
        weight = round(float(row.weight or 1) * 10)
        direction = -1 if row.preference_type == ScenarioPreferenceType.PREFER_COURSE else 1
        terms.append(direction * weight * course_satisfaction_indicator(ctx, row.course_id))
    return sum(terms) if terms else 0


def _primary_department_reward(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Reward needed elective choices from the primary major's department."""
    department_id = (
        ctx.db.query(AcademicProgram.department_id)
        .join(ScenarioProgram, ScenarioProgram.academic_program_id == AcademicProgram.academic_program_id)
        .filter(
            ScenarioProgram.planning_scenario_id == ctx.scenario.planning_scenario_id,
            ScenarioProgram.program_role == ScenarioProgramRole.PRIMARY_MAJOR,
        )
        .scalar()
    )
    if department_id is None:
        return 0
    subject_ids = {
        subject_id
        for (subject_id,) in ctx.db.query(Subject.subject_id).filter(Subject.department_id == department_id).all()
    }
    terms = [
        var
        for (course_id, _term_id), var in ctx.assign.items()
        if ctx.candidates.subject_id_by_course_id.get(course_id) in subject_ids
    ]
    return sum(terms) if terms else 0


def _bottleneck_sequencing_penalty(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Penalize delaying prerequisite-critical and infrequently offered candidate courses."""
    prerequisite_counts = dict(
        ctx.db.query(CourseRuleNode.required_course_id, func.count(CourseRuleNode.course_rule_node_id))
        .filter(CourseRuleNode.required_course_id.in_(ctx.candidates.assignable_course_ids))
        .group_by(CourseRuleNode.required_course_id)
        .all()
    )
    term_indices = {term.term_id: index + 1 for index, term in enumerate(ctx.terms)}
    terms = []
    for (course_id, term_id), var in ctx.assign.items():
        course = ctx.candidates.courses_by_id[course_id]
        offering_count = int(course.fall_offered) + int(course.spring_offered) + int(course.summer_offered)
        bottleneck_weight = min(prerequisite_counts.get(course_id, 0), 5) + int(offering_count <= 1)
        if bottleneck_weight:
            terms.append(bottleneck_weight * term_indices[term_id] * var)
    return sum(terms) if terms else 0


def _summer_credit_hours(ctx: OptimizerModel) -> cp_model.LinearExpr:
    """Return the linear expression for total scaled credit hours assigned to SUMMER terms."""
    summer_term_ids = {term.term_id for term in ctx.terms if term.term_type == SUMMER_TERM_TYPE}
    terms = [total for term_id, total in ctx.term_credit_totals.items() if term_id in summer_term_ids]
    return sum(terms) if terms else 0
