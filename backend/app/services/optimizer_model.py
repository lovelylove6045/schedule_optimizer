"""Builds the CP-SAT decision variables and hard constraints for one
planning scenario: `assign[course_id, term_id]` booleans, one-term-per-course,
term-offering eligibility, prerequisite/corequisite ordering (reusing
`catalog_service.get_prerequisite_tree`), per-term credit bounds, requirement
coverage (mirroring `credit_matching_service`'s ALL/ANY/N_OF/CREDITS_FROM
logic but as CP-SAT constraints instead of fixed booleans), and hard
`scenario_preferences`. Call `optimizer_objectives` afterward to set an
objective and solve."""

from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.models.enums import RequisiteType, ScenarioPreferenceType
from app.models.planning_scenario import PlanningScenario
from app.models.overlap_policy import OverlapPolicy
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.scenario_preference import ScenarioPreference
from app.models.scenario_term import ScenarioTerm
from app.models.term import Term
from app.schemas.course import CourseOut
from app.schemas.prerequisite import PrerequisiteNodeOut
from app.schemas.requirement import RequirementNodeOut
from app.services import catalog_service
from app.services.optimizer_candidates import CandidateCourseSet

_SAME_TERM_ALLOWED_REQUISITE_TYPES = {RequisiteType.COREQUISITE, RequisiteType.PRE_OR_COREQUISITE}
_TERM_TYPE_OFFERING_FIELDS = {
    "FALL": "fall_offered",
    "SPRING": "spring_offered",
    "SUMMER": "summer_offered",
}
# Class-standing proxy for STANDING prerequisite leaves (e.g. "Senior standing").
# The catalog has no "credits earned so far" field to check directly, so this
# reuses the standard US credit-hour bands for each class year. FRESHMAN isn't
# listed because its floor is 0, same as any standing this map doesn't cover.
_STANDING_MINIMUM_CREDIT_HOURS = {
    "SOPHOMORE": 30.0,
    "JUNIOR": 60.0,
    "SENIOR": 90.0,
    "GRADUATE": 120.0,
}
# Same credit-hour bands as `_STANDING_MINIMUM_CREDIT_HOURS`, keyed by the
# catalog-level thousands digit a SUBJECT_LEVEL leaf names (e.g. "4000-level
# coursework in the subject") -- one academic year's worth of credits per level.
_CREDITS_PER_COURSE_LEVEL_YEAR = 30.0
# Generous upper bound for a materialized cumulative-credit-hours IntVar's domain --
# no real plan should ever reach this, it just needs to be safely above one.
_MAX_PLAUSIBLE_CUMULATIVE_CREDITS = 400.0
_MISSING_CATALOG_COURSE_PREFIX = "Referenced course not present in provided dataset:"


@dataclass
class OptimizerModel:
    """Mutable build context for one scenario's CP-SAT model: the underlying
    `cp_model.CpModel`, its decision variables, and every memoization cache
    the constraint/objective builders share while walking requirement and
    prerequisite trees."""

    db: Session
    scenario: PlanningScenario
    candidates: CandidateCourseSet
    terms: list[Term]
    model: cp_model.CpModel
    assign: dict[tuple[int, int], cp_model.IntVar]
    node_indicators: dict[int, cp_model.IntVar] = field(default_factory=dict)
    course_assigned_indicators: dict[int, cp_model.IntVar] = field(default_factory=dict)
    course_satisfaction_indicators: dict[int, cp_model.IntVar] = field(default_factory=dict)
    open_credit_indicators: dict[int, cp_model.IntVar] = field(default_factory=dict)
    node_course_usage_indicators: dict[tuple[int, int], cp_model.IntVar] = field(default_factory=dict)
    prerequisite_indicators: dict[tuple[int, int, bool], cp_model.IntVar] = field(default_factory=dict)
    term_credit_totals: dict[int, cp_model.LinearExpr] = field(default_factory=dict)
    cumulative_credit_totals: dict[int, cp_model.IntVar] = field(default_factory=dict)
    term_used_indicators: dict[int, cp_model.IntVar] = field(default_factory=dict)
    graduation_index_var: cp_model.IntVar | None = None
    heaviest_term_credits_var: cp_model.IntVar | None = None
    credit_requirement_node_ids: set[int] = field(default_factory=set)
    unmodeled_prerequisite_course_ids: set[int] = field(default_factory=set)
    unmodeled_prerequisite_node_ids: set[int] = field(default_factory=set)
    unmodeled_prerequisite_course_ids_by_target: dict[int, set[int]] = field(default_factory=dict)
    unmodeled_prerequisite_node_ids_by_target: dict[int, set[int]] = field(default_factory=dict)
    active_prerequisite_target_course_id: int | None = None
    var_counter: int = 0


def build_optimizer_model(
    db: Session, scenario: PlanningScenario, candidates: CandidateCourseSet, terms: list[Term]
) -> OptimizerModel:
    """Build the CP-SAT model (variables + all hard constraints) for one scenario."""
    ctx = OptimizerModel(
        db=db, scenario=scenario, candidates=candidates, terms=terms, model=cp_model.CpModel(), assign={}
    )
    _create_assignment_variables(ctx)
    _add_single_term_constraints(ctx)
    _add_course_relation_constraints(ctx)
    # Term credit totals first: prerequisite ordering's class-standing proxy
    # (`_cumulative_credit_hours_before`) reuses `ctx.term_credit_totals` instead of
    # re-summing every assign variable per prerequisite node.
    _add_term_credit_constraints(ctx)
    _add_prerequisite_ordering_constraints(ctx)
    _add_required_early_seminar_constraints(ctx)
    _add_requirement_coverage_constraints(ctx)
    _add_overlap_policy_constraints(ctx)
    _add_hard_preference_constraints(ctx)
    _add_program_credit_floor_constraint(ctx)
    return ctx


def _add_required_early_seminar_constraints(ctx: OptimizerModel) -> None:
    """Place each mandatory introductory seminar in its earliest offered horizon term."""
    terms_by_id = {term.term_id: term for term in ctx.terms}
    for course_id in ctx.candidates.required_early_seminar_course_ids:
        assignments = sorted(
            ((terms_by_id[term_id].sequence_index, var) for (cid, term_id), var in ctx.assign.items() if cid == course_id),
            key=lambda item: item[0],
        )
        if assignments:
            ctx.model.Add(assignments[0][1] == 1)


def _next_name(ctx: OptimizerModel, prefix: str) -> str:
    """Return a fresh, unique CP-SAT variable name with the given prefix."""
    ctx.var_counter += 1
    return f"{prefix}_{ctx.var_counter}"


def _constant_bool(ctx: OptimizerModel, value: bool) -> cp_model.IntVar:
    """Return a fresh BoolVar fixed to the given constant value."""
    var = ctx.model.NewBoolVar(_next_name(ctx, "const"))
    ctx.model.Add(var == int(value))
    return var


def _at_least_indicator(
    ctx: OptimizerModel, indicators: list[cp_model.IntVar], threshold: int
) -> cp_model.IntVar:
    """Return a 0/1 indicator that at least `threshold` of the given indicators are 1."""
    result = ctx.model.NewBoolVar(_next_name(ctx, "at_least"))
    total = sum(indicators) if indicators else 0
    ctx.model.Add(total >= threshold).OnlyEnforceIf(result)
    ctx.model.Add(total < threshold).OnlyEnforceIf(result.Not())
    return result


def _all_indicator(ctx: OptimizerModel, indicators: list[cp_model.IntVar]) -> cp_model.IntVar:
    """Return a 0/1 indicator that every given indicator is 1 (vacuously true if empty)."""
    if not indicators:
        return _constant_bool(ctx, True)
    return _at_least_indicator(ctx, indicators, len(indicators))


def scaled_credits(value: float) -> int:
    """Scale a decimal credit-hours value to a CP-SAT-friendly integer (tenths of a credit)."""
    return round(value * 10)


def _create_assignment_variables(ctx: OptimizerModel) -> None:
    """Create one BoolVar per (course, term) pair where the course is offered that term type."""
    for course_id in ctx.candidates.assignable_course_ids:
        course = ctx.candidates.courses_by_id[course_id]
        for term in ctx.terms:
            if _course_offered_in_term(course, term):
                ctx.assign[(course_id, term.term_id)] = ctx.model.NewBoolVar(
                    f"assign_{course_id}_{term.term_id}"
                )


def _course_offered_in_term(course: CourseOut, term: Term) -> bool:
    """Return whether `course` is offered during `term`'s term type."""
    field_name = _TERM_TYPE_OFFERING_FIELDS.get(term.term_type)
    return bool(field_name) and getattr(course, field_name)


def _add_single_term_constraints(ctx: OptimizerModel) -> None:
    """Constrain each candidate course to be assigned to at most one term."""
    for course_id in ctx.candidates.assignable_course_ids:
        term_vars = [var for (cid, _tid), var in ctx.assign.items() if cid == course_id]
        if term_vars:
            ctx.model.Add(sum(term_vars) <= 1)


def _add_course_relation_constraints(ctx: OptimizerModel) -> None:
    """Prevent equivalent and duplicate-credit courses from both receiving full plan credit."""
    seen_pairs: set[tuple[int, int]] = set()
    for course_id, equivalent_ids in ctx.candidates.equivalent_course_ids.items():
        for equivalent_id in equivalent_ids:
            pair = tuple(sorted((course_id, equivalent_id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            _limit_related_pair(ctx, course_id, equivalent_id, None)
    for relation in ctx.candidates.duplicate_credit_relations:
        _limit_related_pair(
            ctx,
            relation.course_id,
            relation.related_course_id,
            float(relation.maximum_combined_credits) if relation.maximum_combined_credits is not None else None,
        )


def _limit_related_pair(
    ctx: OptimizerModel, course_a_id: int, course_b_id: int, maximum_combined_credits: float | None
) -> None:
    """Constrain a related pair so duplicate academic credit cannot be earned twice."""
    first = course_assigned_any_term(ctx, course_a_id)
    second = course_assigned_any_term(ctx, course_b_id)
    completed_count = int(course_a_id in ctx.candidates.completed_course_ids) + int(
        course_b_id in ctx.candidates.completed_course_ids
    )
    if maximum_combined_credits is None:
        ctx.model.Add(first + second == 0 if completed_count else first + second <= 1)
        return
    first_credits = scaled_credits(ctx.candidates.credit_hours_by_course_id.get(course_a_id, 0))
    second_credits = scaled_credits(ctx.candidates.credit_hours_by_course_id.get(course_b_id, 0))
    completed_credits = min(
        first_credits * int(course_a_id in ctx.candidates.completed_course_ids)
        + second_credits * int(course_b_id in ctx.candidates.completed_course_ids),
        scaled_credits(maximum_combined_credits),
    )
    ctx.model.Add(
        completed_credits + first_credits * first + second_credits * second
        <= scaled_credits(maximum_combined_credits)
    )


def _add_overlap_policy_constraints(ctx: OptimizerModel) -> None:
    """Enforce explicit policy limits against actual cross-program allocations."""
    for policy in ctx.candidates.overlap_policies:
        set_ids_a, set_ids_b = _policy_requirement_set_ids(ctx, policy)
        shared_indicators = _shared_allocation_indicators(ctx, set_ids_a, set_ids_b)
        policy_type = policy.policy_type.upper()
        if policy_type in {"DISALLOW", "NO_SHARING", "DISALLOW_SHARING"}:
            for indicator in shared_indicators.values():
                ctx.model.Add(indicator == 0)
        elif policy_type in {"MAX_SHARED_CREDITS", "MAX_CREDITS"} and policy.credit_value is not None:
            total = sum(
                scaled_credits(ctx.candidates.credit_hours_by_course_id.get(course_id, 0)) * indicator
                for course_id, indicator in shared_indicators.items()
            )
            ctx.model.Add(total <= scaled_credits(float(policy.credit_value)))


def _policy_requirement_set_ids(
    ctx: OptimizerModel, policy: OverlapPolicy
) -> tuple[set[int], set[int]]:
    """Return non-inherited requirement-set scopes for both sides of a policy."""
    if policy.requirement_set_a_id is not None:
        set_ids_a = {policy.requirement_set_a_id}
    else:
        set_ids_a = _program_requirement_set_ids(ctx, policy.program_a_id)
    if policy.requirement_set_b_id is not None:
        set_ids_b = {policy.requirement_set_b_id}
    else:
        set_ids_b = _program_requirement_set_ids(ctx, policy.program_b_id)
    inherited = set_ids_a & set_ids_b
    return set_ids_a - inherited, set_ids_b - inherited


def _program_requirement_set_ids(ctx: OptimizerModel, program_id: int | None) -> set[int]:
    """Return requirement-set ids linked to one policy program."""
    if program_id is None:
        return set()
    rows = ctx.db.query(ProgramRequirementSet.requirement_set_id).filter(
        ProgramRequirementSet.academic_program_id == program_id
    ).all()
    return {requirement_set_id for (requirement_set_id,) in rows}


def _shared_allocation_indicators(
    ctx: OptimizerModel, set_ids_a: set[int], set_ids_b: set[int]
) -> dict[int, cp_model.IntVar]:
    """Return per-course indicators for actual use on both sides of a policy."""
    course_ids = {course_id for (_node_id, course_id) in ctx.node_course_usage_indicators}
    shared: dict[int, cp_model.IntVar] = {}
    for course_id in course_ids:
        used_a = _course_used_in_requirement_sets(ctx, course_id, set_ids_a, "policy_a")
        used_b = _course_used_in_requirement_sets(ctx, course_id, set_ids_b, "policy_b")
        if used_a is None or used_b is None:
            continue
        indicator = ctx.model.NewBoolVar(_next_name(ctx, f"policy_shared_{course_id}"))
        ctx.model.Add(indicator <= used_a)
        ctx.model.Add(indicator <= used_b)
        ctx.model.Add(indicator >= used_a + used_b - 1)
        shared[course_id] = indicator
    return shared


def _course_used_in_requirement_sets(
    ctx: OptimizerModel, course_id: int, requirement_set_ids: set[int], name: str
) -> cp_model.IntVar | None:
    """Return whether a course is allocated to any node in the requested sets."""
    usages = [
        usage
        for (node_id, used_course_id), usage in ctx.node_course_usage_indicators.items()
        if used_course_id == course_id
        and ctx.candidates.requirement_set_id_by_node_id.get(node_id) in requirement_set_ids
    ]
    if not usages:
        return None
    indicator = ctx.model.NewBoolVar(_next_name(ctx, f"{name}_{course_id}"))
    ctx.model.AddMaxEquality(indicator, usages)
    return indicator


def course_assigned_any_term(ctx: OptimizerModel, course_id: int) -> cp_model.IntVar:
    """Return a cached 0/1 indicator that `course_id` is assigned to at least one term."""
    if course_id in ctx.course_assigned_indicators:
        return ctx.course_assigned_indicators[course_id]
    term_vars = [var for (cid, _tid), var in ctx.assign.items() if cid == course_id]
    indicator = ctx.model.NewBoolVar(_next_name(ctx, f"assigned_any_term_{course_id}"))
    if term_vars:
        ctx.model.AddMaxEquality(indicator, term_vars)
    else:
        ctx.model.Add(indicator == 0)
    ctx.course_assigned_indicators[course_id] = indicator
    return indicator


def course_satisfaction_indicator(ctx: OptimizerModel, course_id: int) -> cp_model.IntVar:
    """Return a cached 0/1 indicator for whether `course_id` counts as done in this
    plan: already completed (per student_credits -- ignoring per-node minimum-grade
    nuance, which the COURSE-leaf fast path already handles precisely) or assigned
    to some term by the solver. Shared with `optimizer_objectives` (e.g. to reward
    genuine cross-program double counting) so it reuses the same cached indicators."""
    if course_id in ctx.course_satisfaction_indicators:
        return ctx.course_satisfaction_indicators[course_id]
    if course_id in ctx.candidates.completed_course_ids:
        indicator = _constant_bool(ctx, True)
    else:
        indicator = course_assigned_any_term(ctx, course_id)
    ctx.course_satisfaction_indicators[course_id] = indicator
    return indicator


def _add_requirement_coverage_constraints(ctx: OptimizerModel) -> None:
    """Force every top-level node of every resolved requirement set to be satisfied."""
    for req_set in ctx.candidates.requirement_sets:
        for node in req_set.nodes:
            indicator = _build_node_indicator(ctx, node)
            ctx.model.Add(indicator == 1)


def _build_node_indicator(ctx: OptimizerModel, node: RequirementNodeOut) -> cp_model.IntVar:
    """Build (or return the cached) 0/1 indicator for whether a requirement node is
    satisfied in the solved plan, recursively building its children's indicators first."""
    if node.requirement_node_id in ctx.node_indicators:
        return ctx.node_indicators[node.requirement_node_id]
    child_indicators = [_build_node_indicator(ctx, child) for child in node.children]
    indicator = _node_satisfaction_indicator(ctx, node, child_indicators)
    ctx.node_indicators[node.requirement_node_id] = indicator
    return indicator


def _node_satisfaction_indicator(
    ctx: OptimizerModel, node: RequirementNodeOut, child_indicators: list[cp_model.IntVar]
) -> cp_model.IntVar:
    """Dispatch one requirement node to a 0/1 satisfaction indicator by type. A node
    already satisfied by completed coursework (`node.is_satisfied`) short-circuits to
    a constant, which composes correctly into a not-yet-fully-satisfied parent."""
    if node.is_satisfied:
        return _constant_bool(ctx, True)
    if node.node_type == "COURSE" and node.required_course is not None:
        return _course_requirement_indicator(ctx, node)
    if node.node_type == "COURSE_GROUP" and node.course_group is not None:
        return _group_satisfaction_indicator(ctx, node)
    if node.node_type == "CREDIT_REQUIREMENT":
        ctx.credit_requirement_node_ids.add(node.requirement_node_id)
        return _constant_bool(ctx, True)
    if child_indicators:
        return _aggregate_indicator(ctx, node, child_indicators)
    return _constant_bool(ctx, False)


def _group_satisfaction_indicator(ctx: OptimizerModel, node: RequirementNodeOut) -> cp_model.IntVar:
    """Return a 0/1 indicator for a COURSE_GROUP leaf, enforcing whichever thresholds
    the node actually carries: a member count (`required_count`), a credit-hour total
    (`required_credit_hours`), or both. Credit hours matter here: 240 of the catalog's
    252 COURSE_GROUP nodes state their
    requirement in credit hours only ("Gen Ed HASS, 15 credit hours"). This used to
    read `required_count or 1` and ignore credit hours entirely, so the solver treated
    a 15-credit elective block as covered by a single 3-credit course and every plan
    it produced was short of the real requirement. Mirrors
    `credit_matching_service._is_group_satisfied`, which evaluates the same rule
    against already-completed coursework."""
    member_ids = sorted(_eligible_group_member_ids(ctx, node))
    member_indicators = [
        _node_course_usage_indicator(
            ctx, node.requirement_node_id, cid, course_satisfaction_indicator(ctx, cid)
        )
        for cid in member_ids
    ]
    thresholds: list[cp_model.IntVar] = []
    if node.required_count is not None:
        thresholds.append(_at_least_indicator(ctx, member_indicators, node.required_count))
    if node.required_credit_hours is not None:
        thresholds.append(_group_credit_threshold_indicator(ctx, node, member_ids, member_indicators))
    if node.minimum_distinct_subjects is not None:
        thresholds.append(_distinct_subject_threshold_indicator(ctx, node, member_ids))
    if not thresholds:
        thresholds.append(_at_least_indicator(ctx, member_indicators, 1))
    result = _all_indicator(ctx, thresholds)
    ctx.model.Add(sum(member_indicators) <= len(member_indicators) * result)
    if node.required_count is not None and node.required_credit_hours is None:
        ctx.model.Add(sum(member_indicators) <= node.required_count)
    if node.required_credit_hours is not None and member_ids:
        credit_hours = ctx.candidates.credit_hours_by_course_id
        total = sum(
            scaled_credits(credit_hours.get(course_id, 0)) * indicator
            for course_id, indicator in zip(member_ids, member_indicators)
        )
        maximum_member = max(scaled_credits(credit_hours.get(course_id, 0)) for course_id in member_ids)
        ctx.model.Add(total <= scaled_credits(node.required_credit_hours) + maximum_member - 1)
    return result


def _course_requirement_indicator(ctx: OptimizerModel, node: RequirementNodeOut) -> cp_model.IntVar:
    """Return whether the named course or an allowed equivalent satisfies this requirement leaf."""
    required_id = node.required_course.course_id
    eligible_ids = {required_id} | ctx.candidates.equivalent_course_ids.get(required_id, set())
    eligible_ids = {
        course_id
        for course_id in eligible_ids
        if node.minimum_course_level is None
        or ctx.candidates.course_level_by_course_id.get(course_id, 0) >= node.minimum_course_level
    }
    usage = [
        _node_course_usage_indicator(
            ctx, node.requirement_node_id, course_id, course_satisfaction_indicator(ctx, course_id)
        )
        for course_id in sorted(eligible_ids)
    ]
    result = _at_least_indicator(ctx, usage, 1)
    ctx.model.Add(sum(usage) == result)
    return result


def _node_course_usage_indicator(
    ctx: OptimizerModel,
    requirement_node_id: int,
    course_id: int,
    satisfaction_indicator: cp_model.IntVar,
) -> cp_model.IntVar:
    """Return an allocation variable limited to courses actually satisfied in the plan."""
    key = (requirement_node_id, course_id)
    if key in ctx.node_course_usage_indicators:
        return ctx.node_course_usage_indicators[key]
    usage = ctx.model.NewBoolVar(_next_name(ctx, f"use_{requirement_node_id}_{course_id}"))
    ctx.model.Add(usage <= satisfaction_indicator)
    ctx.node_course_usage_indicators[key] = usage
    return usage


def _eligible_group_member_ids(ctx: OptimizerModel, node: RequirementNodeOut) -> set[int]:
    """Return level-eligible group members and their directed equivalents."""
    base_ids = ctx.candidates.group_members.get(node.course_group.course_group_id, set())
    member_ids = set(base_ids)
    for course_id in base_ids:
        member_ids |= ctx.candidates.equivalent_course_ids.get(course_id, set())
    if node.minimum_course_level is None:
        return member_ids
    return {
        course_id
        for course_id in member_ids
        if ctx.candidates.course_level_by_course_id.get(course_id, 0) >= node.minimum_course_level
    }


def _distinct_subject_threshold_indicator(
    ctx: OptimizerModel, node: RequirementNodeOut, member_ids: list[int]
) -> cp_model.IntVar:
    """Return whether satisfying group courses span the node's minimum number of subjects."""
    ids_by_subject: dict[int, list[int]] = {}
    for course_id in member_ids:
        subject_id = ctx.candidates.subject_id_by_course_id.get(course_id)
        if subject_id is not None:
            ids_by_subject.setdefault(subject_id, []).append(course_id)
    subject_indicators = [
        _at_least_indicator(
            ctx,
            [ctx.node_course_usage_indicators[(node.requirement_node_id, course_id)] for course_id in course_ids],
            1,
        )
        for course_ids in ids_by_subject.values()
    ]
    return _at_least_indicator(ctx, subject_indicators, node.minimum_distinct_subjects or 0)


def _group_credit_threshold_indicator(
    ctx: OptimizerModel,
    node: RequirementNodeOut,
    member_ids: list[int],
    member_indicators: list[cp_model.IntVar],
) -> cp_model.IntVar:
    """Return a 0/1 indicator that the satisfied members of one COURSE_GROUP leaf add
    up to at least its `required_credit_hours`."""
    credit_hours = ctx.candidates.credit_hours_by_course_id
    scaled_terms = [
        scaled_credits(credit_hours.get(course_id, 0.0)) * indicator
        for course_id, indicator in zip(member_ids, member_indicators)
    ]
    threshold = scaled_credits(node.required_credit_hours)
    result = ctx.model.NewBoolVar(_next_name(ctx, f"group_credits_{node.requirement_node_id}"))
    total = sum(scaled_terms) if scaled_terms else 0
    ctx.model.Add(total >= threshold).OnlyEnforceIf(result)
    ctx.model.Add(total < threshold).OnlyEnforceIf(result.Not())
    return result


def _aggregate_indicator(
    ctx: OptimizerModel, node: RequirementNodeOut, child_indicators: list[cp_model.IntVar]
) -> cp_model.IntVar:
    """Combine already-built child indicators per the node's operator (ALL/ANY/N_OF/
    CREDITS_FROM/UNITS_FROM; ALL is also the default when no operator is set)."""
    operator = node.node_operator
    if operator == "ANY":
        return _at_least_indicator(ctx, child_indicators, 1)
    if operator == "N_OF":
        return _at_least_indicator(ctx, child_indicators, node.required_count or 1)
    if operator in ("CREDITS_FROM", "UNITS_FROM"):
        return _credit_threshold_indicator(ctx, node, child_indicators)
    return _all_indicator(ctx, child_indicators)


def _credit_threshold_indicator(
    ctx: OptimizerModel, node: RequirementNodeOut, child_indicators: list[cp_model.IntVar]
) -> cp_model.IntVar:
    """Return a 0/1 indicator that enough credit hours are covered by satisfied children
    to meet `node.required_credit_hours` (CREDITS_FROM/UNITS_FROM operators)."""
    scaled_terms = [
        scaled_credits(_child_credit_hours(child)) * indicator
        for child, indicator in zip(node.children, child_indicators)
    ]
    threshold = scaled_credits(node.required_credit_hours or 0.0)
    result = ctx.model.NewBoolVar(_next_name(ctx, f"credits_from_{node.requirement_node_id}"))
    total = sum(scaled_terms) if scaled_terms else 0
    ctx.model.Add(total >= threshold).OnlyEnforceIf(result)
    ctx.model.Add(total < threshold).OnlyEnforceIf(result.Not())
    return result


def _child_credit_hours(node: RequirementNodeOut) -> float:
    """Return the credit hours a satisfied child contributes toward a CREDITS_FROM/UNITS_FROM total."""
    return node.required_course.credit_hours if node.required_course else 0.0


def _add_prerequisite_ordering_constraints(ctx: OptimizerModel) -> None:
    """For each candidate course assigned to a term, require its prerequisite/
    corequisite tree (`course_rule_nodes`, reusing `catalog_service.get_prerequisite_tree`)
    to already be satisfied by that term."""
    for course_id in ctx.candidates.assignable_course_ids:
        prerequisite_roots = catalog_service.get_prerequisite_tree(ctx.db, course_id)
        if not prerequisite_roots:
            continue
        ctx.active_prerequisite_target_course_id = course_id
        _add_prerequisite_constraints_for_course(ctx, course_id, prerequisite_roots)
        ctx.active_prerequisite_target_course_id = None


def _add_prerequisite_constraints_for_course(
    ctx: OptimizerModel, course_id: int, prerequisite_roots: list[PrerequisiteNodeOut]
) -> None:
    """Require every prerequisite root of one course to hold by the term it's assigned to."""
    for (cid, term_id), assign_var in ctx.assign.items():
        if cid != course_id:
            continue
        before_term = _term_by_id(ctx, term_id)
        for root in prerequisite_roots:
            indicator = _prerequisite_node_satisfied_by(ctx, root, before_term)
            ctx.model.AddImplication(assign_var, indicator)


def _term_by_id(ctx: OptimizerModel, term_id: int) -> Term:
    """Look up one term in the scenario's horizon by id."""
    return next(term for term in ctx.terms if term.term_id == term_id)


def _prerequisite_node_satisfied_by(
    ctx: OptimizerModel, node: PrerequisiteNodeOut, before_term: Term
) -> cp_model.IntVar:
    """Return a cached 0/1 indicator that prerequisite subtree `node` is satisfied by
    courses completed or assigned before `before_term` (same term allowed for co-requisites)."""
    same_term_allowed = node.requisite_type in _SAME_TERM_ALLOWED_REQUISITE_TYPES
    cache_key = (node.course_rule_node_id, before_term.term_id, same_term_allowed)
    if cache_key in ctx.prerequisite_indicators:
        return ctx.prerequisite_indicators[cache_key]
    indicator = _build_prerequisite_indicator(ctx, node, before_term, same_term_allowed)
    ctx.prerequisite_indicators[cache_key] = indicator
    return indicator


def _build_prerequisite_indicator(
    ctx: OptimizerModel, node: PrerequisiteNodeOut, before_term: Term, same_term_allowed: bool
) -> cp_model.IntVar:
    """Dispatch one prerequisite-subtree node to a 0/1 satisfaction indicator. A
    RECOMMENDED node (advisory by definition, e.g. "students should enroll in X and
    Y simultaneously") is never a hard gate -- enforcing it as strict ordering once
    deadlocked two courses that each RECOMMENDED/PRE_OR_COREQUISITE'd the other into
    going first. STANDING and SUBJECT_LEVEL leaves are checked against a credit-hours
    class-standing proxy (see `_STANDING_MINIMUM_CREDIT_HOURS`); other leaf types the
    solver has no data to verify (EXAM/CONSENT/OTHER/COURSE_GROUP/etc.) are assumed
    satisfiable and flagged, except an OTHER leaf explicitly representing a missing
    catalog course. A missing course cannot satisfy an alternative and bypass the
    available modeled prerequisite. External conditions remain advisor-verifiable,
    matching how CREDIT_REQUIREMENT leaves are handled (see PDS §12)."""
    if node.requisite_type == RequisiteType.RECOMMENDED:
        _record_unmodeled_prerequisite_node(ctx, node.course_rule_node_id)
        return _constant_bool(ctx, True)
    if node.node_type == "COURSE" and node.required_course is not None:
        return _course_satisfied_before(
            ctx, node.required_course.course_id, before_term, same_term_allowed
        )
    if node.node_type == "STANDING" and node.minimum_standing is not None:
        return _standing_satisfied_before(ctx, node.minimum_standing, before_term)
    if node.node_type == "SUBJECT_LEVEL" and node.minimum_course_level:
        return _course_level_satisfied_before(ctx, node.minimum_course_level, before_term)
    if node.node_type == "CREDIT_HOURS" and node.minimum_total_credits is not None:
        return _cumulative_credits_at_least(ctx, before_term, node.minimum_total_credits)
    if node.node_type == "PROGRAM_MEMBERSHIP" and node.required_academic_program_id is not None:
        return _constant_bool(
            ctx, node.required_academic_program_id in ctx.candidates.selected_program_ids
        )
    if _is_missing_catalog_course_node(node):
        _record_unmodeled_prerequisite_node(ctx, node.course_rule_node_id)
        return _constant_bool(ctx, False)
    if node.children:
        return _aggregate_prerequisite_indicator(ctx, node, before_term, same_term_allowed)
    _record_unmodeled_prerequisite_node(ctx, node.course_rule_node_id)
    return _constant_bool(ctx, True)


def _is_missing_catalog_course_node(node: PrerequisiteNodeOut) -> bool:
    """Return whether an OTHER leaf represents a course absent from the snapshot."""
    return node.node_type == "OTHER" and bool(
        node.text_value and node.text_value.startswith(_MISSING_CATALOG_COURSE_PREFIX)
    )


def _record_unmodeled_prerequisite_node(ctx: OptimizerModel, node_id: int) -> None:
    """Record an unverifiable prerequisite node globally and for its target course."""
    ctx.unmodeled_prerequisite_node_ids.add(node_id)
    target_id = ctx.active_prerequisite_target_course_id
    if target_id is not None:
        ctx.unmodeled_prerequisite_node_ids_by_target.setdefault(target_id, set()).add(node_id)


def _standing_satisfied_before(
    ctx: OptimizerModel, minimum_standing: str, before_term: Term
) -> cp_model.IntVar:
    """Return a 0/1 indicator that the student has reached `minimum_standing`
    (e.g. "SENIOR") by `before_term`, per the credit-hour proxy in
    `_STANDING_MINIMUM_CREDIT_HOURS`."""
    threshold = _STANDING_MINIMUM_CREDIT_HOURS.get(minimum_standing, 0.0)
    return _cumulative_credits_at_least(ctx, before_term, threshold)


def _course_level_satisfied_before(
    ctx: OptimizerModel, minimum_course_level: int, before_term: Term
) -> cp_model.IntVar:
    """Return a 0/1 indicator that the student has earned enough credit hours by
    `before_term` to plausibly have reached `minimum_course_level` coursework (e.g.
    a "4000-level or above" gate), per the same credit-hour proxy used for STANDING."""
    course_level_years = max(minimum_course_level // 1000 - 1, 0)
    threshold = course_level_years * _CREDITS_PER_COURSE_LEVEL_YEAR
    return _cumulative_credits_at_least(ctx, before_term, threshold)


def _cumulative_credits_at_least(
    ctx: OptimizerModel, before_term: Term, minimum_credits: float
) -> cp_model.IntVar:
    """Return a 0/1 indicator that the student's completed-plus-already-scheduled
    credit hours, counting only terms strictly before `before_term`, reach at least
    `minimum_credits`. The class-standing proxy shared by STANDING and SUBJECT_LEVEL
    prerequisite leaves."""
    if minimum_credits <= 0:
        return _constant_bool(ctx, True)
    total = _cumulative_credit_hours_before(ctx, before_term)
    threshold = scaled_credits(minimum_credits)
    result = ctx.model.NewBoolVar(_next_name(ctx, f"standing_before_{before_term.term_id}"))
    ctx.model.Add(total >= threshold).OnlyEnforceIf(result)
    ctx.model.Add(total < threshold).OnlyEnforceIf(result.Not())
    return result


def _cumulative_credit_hours_before(ctx: OptimizerModel, before_term: Term) -> cp_model.IntVar:
    """Return (and cache) an IntVar materializing the scaled credit-hour total of
    everything the student will have completed or been assigned strictly before
    `before_term`: already-completed coursework plus a running total chained off
    each earlier term's own credit total (`ctx.term_credit_totals`). Materialized as
    one compact variable per term, instead of a raw linear expression, so the many
    STANDING/SUBJECT_LEVEL threshold checks that share a `before_term` each add a
    cheap comparison against it instead of re-expanding the whole prior-terms sum."""
    if before_term.term_id in ctx.cumulative_credit_totals:
        return ctx.cumulative_credit_totals[before_term.term_id]
    previous_term = _term_immediately_before(ctx, before_term)
    if previous_term is None:
        expr = scaled_credits(ctx.candidates.completed_credit_hours)
    else:
        earlier_total = _cumulative_credit_hours_before(ctx, previous_term)
        expr = earlier_total + ctx.term_credit_totals.get(previous_term.term_id, 0)
    upper_bound = scaled_credits(_MAX_PLAUSIBLE_CUMULATIVE_CREDITS)
    cumulative_var = ctx.model.NewIntVar(
        0, upper_bound, _next_name(ctx, f"cumulative_before_{before_term.term_id}")
    )
    ctx.model.Add(cumulative_var == expr)
    ctx.cumulative_credit_totals[before_term.term_id] = cumulative_var
    return cumulative_var


def _term_immediately_before(ctx: OptimizerModel, term: Term) -> Term | None:
    """Return the horizon term with the next-lower sequence_index before `term`, or
    None if `term` is the first term in the scenario's horizon."""
    earlier_terms = [t for t in ctx.terms if t.sequence_index < term.sequence_index]
    return max(earlier_terms, key=lambda t: t.sequence_index, default=None)


def _aggregate_prerequisite_indicator(
    ctx: OptimizerModel, node: PrerequisiteNodeOut, before_term: Term, same_term_allowed: bool
) -> cp_model.IntVar:
    """Combine a prerequisite GROUP node's children per its rule_operator (defaults to ALL;
    CREDITS_FROM/UNITS_FROM aren't used by real prerequisite trees, so they also fall back to ALL)."""
    child_indicators = [
        _prerequisite_node_satisfied_by(ctx, child, before_term) for child in node.children
    ]
    if node.rule_operator == "ANY":
        return _at_least_indicator(ctx, child_indicators, 1)
    if node.rule_operator == "N_OF":
        return _at_least_indicator(ctx, child_indicators, node.required_count or 1)
    return _all_indicator(ctx, child_indicators)


def _course_satisfied_before(
    ctx: OptimizerModel, course_id: int, before_term: Term, same_term_allowed: bool
) -> cp_model.IntVar:
    """Return a 0/1 indicator that `course_id` is completed, or assigned to an eligible
    earlier term (same term too, if `same_term_allowed`). Treat policy-filtered
    non-standard prerequisites as unavailable; assume closure-capped prerequisites
    are satisfiable and flag them so a modeling limit cannot create infeasibility."""
    if course_id in ctx.candidates.completed_course_ids:
        return _constant_bool(ctx, True)
    if course_id not in ctx.candidates.courses_by_id:
        if course_id in ctx.candidates.excluded_nonstandard_course_ids:
            return _constant_bool(ctx, False)
        _record_unmodeled_prerequisite_course(ctx, course_id)
        return _constant_bool(ctx, True)
    eligible_vars = [
        var
        for (cid, tid), var in ctx.assign.items()
        if cid == course_id and _term_precedes(_term_by_id(ctx, tid), before_term, same_term_allowed)
    ]
    result = ctx.model.NewBoolVar(_next_name(ctx, f"prereq_{course_id}_before_{before_term.term_id}"))
    if eligible_vars:
        ctx.model.AddMaxEquality(result, eligible_vars)
    else:
        ctx.model.Add(result == 0)
    return result


def _record_unmodeled_prerequisite_course(ctx: OptimizerModel, course_id: int) -> None:
    """Record an unmodeled prerequisite course globally and for its target course."""
    ctx.unmodeled_prerequisite_course_ids.add(course_id)
    target_id = ctx.active_prerequisite_target_course_id
    if target_id is not None:
        ctx.unmodeled_prerequisite_course_ids_by_target.setdefault(target_id, set()).add(course_id)


def _term_precedes(term: Term, before_term: Term, same_term_allowed: bool) -> bool:
    """Return whether `term` is early enough to satisfy a requisite that must be
    done before (or, if `same_term_allowed`, together with) `before_term`."""
    if same_term_allowed:
        return term.sequence_index <= before_term.sequence_index
    return term.sequence_index < before_term.sequence_index


def _add_term_credit_constraints(ctx: OptimizerModel) -> None:
    """Bound each term's total assigned credit hours by a `scenario_terms` override,
    falling back to the scenario's default min/max credits. A minimum is only enforced
    on terms that actually have a course assigned (skipping a term entirely is fine)."""
    bounds_by_term_id = _load_term_credit_bounds(ctx.db, ctx.scenario)
    for term in ctx.terms:
        _add_one_term_credit_constraint(ctx, term, bounds_by_term_id)


def _load_term_credit_bounds(
    db: Session, scenario: PlanningScenario
) -> dict[int, tuple[float | None, float | None]]:
    """Return each `scenario_terms` override's (minimum_credits, maximum_credits), keyed by term_id."""
    rows = (
        db.query(ScenarioTerm).filter(ScenarioTerm.planning_scenario_id == scenario.planning_scenario_id).all()
    )
    return {row.term_id: (row.minimum_credits, row.maximum_credits) for row in rows}


def _add_one_term_credit_constraint(
    ctx: OptimizerModel,
    term: Term,
    bounds_by_term_id: dict[int, tuple[float | None, float | None]],
) -> None:
    """Bound one term's total credit hours, given its (minimum, maximum) override or scenario default."""
    summer_term = term.term_type == "SUMMER"
    default_minimum = None if summer_term else ctx.scenario.default_minimum_credits
    default_maximum = ctx.scenario.summer_maximum_credits if summer_term else ctx.scenario.default_maximum_credits
    override = bounds_by_term_id.get(term.term_id)
    minimum = override[0] if override is not None and override[0] is not None else default_minimum
    maximum = override[1] if override is not None and override[1] is not None else default_maximum
    term_assignments = [
        (var, ctx.candidates.courses_by_id[cid].credit_hours)
        for (cid, tid), var in ctx.assign.items()
        if tid == term.term_id
    ]
    if not term_assignments:
        return
    total = sum(scaled_credits(hours) * var for var, hours in term_assignments)
    ctx.term_credit_totals[term.term_id] = total
    if maximum is not None:
        ctx.model.Add(total <= scaled_credits(maximum))
    if minimum is not None:
        term_used = term_used_indicator(ctx, term)
        ctx.model.Add(total >= scaled_credits(minimum)).OnlyEnforceIf(term_used)


def term_used_indicator(ctx: OptimizerModel, term: Term) -> cp_model.IntVar:
    """Return a cached 0/1 indicator that at least one course is assigned to `term`.
    Shared with `optimizer_objectives` (e.g. for the earliest-graduation objective)."""
    if term.term_id in ctx.term_used_indicators:
        return ctx.term_used_indicators[term.term_id]
    assign_vars = [var for (_cid, tid), var in ctx.assign.items() if tid == term.term_id]
    indicator = ctx.model.NewBoolVar(_next_name(ctx, f"term_used_{term.term_id}"))
    if assign_vars:
        ctx.model.AddMaxEquality(indicator, assign_vars)
    else:
        ctx.model.Add(indicator == 0)
    ctx.term_used_indicators[term.term_id] = indicator
    return indicator


def _add_hard_preference_constraints(ctx: OptimizerModel) -> None:
    """Enforce REQUIRE_COURSE, AVOID_COURSE, and FIX_COURSE_TO_TERM `scenario_preferences`
    as hard constraints. The model has no separate is_hard_constraint flag; these three
    preference types are inherently mandatory by name, while PREFER_*/AVOID_TAG stay soft
    (folded into `optimizer_objectives` instead)."""
    preferences = (
        ctx.db.query(ScenarioPreference)
        .filter(ScenarioPreference.planning_scenario_id == ctx.scenario.planning_scenario_id)
        .all()
    )
    for preference in preferences:
        _apply_hard_preference(ctx, preference)


def _apply_hard_preference(ctx: OptimizerModel, preference: ScenarioPreference) -> None:
    """Apply one `scenario_preferences` row to the model, if it's a hard preference type."""
    if preference.preference_type == ScenarioPreferenceType.REQUIRE_COURSE and preference.course_id:
        _require_course_assigned(ctx, preference.course_id)
    elif preference.preference_type == ScenarioPreferenceType.AVOID_COURSE and preference.course_id:
        _forbid_course_assignment(ctx, preference.course_id)
    elif preference.preference_type == ScenarioPreferenceType.FIX_COURSE_TO_TERM and (
        preference.course_id and preference.term_id
    ):
        _fix_course_to_term(ctx, preference.course_id, preference.term_id)


def _require_course_assigned(ctx: OptimizerModel, course_id: int) -> None:
    """Force `course_id` to be assigned to exactly one term (a no-op if already completed)."""
    if course_id in ctx.candidates.completed_course_ids:
        return
    term_vars = [var for (cid, _tid), var in ctx.assign.items() if cid == course_id]
    if term_vars:
        ctx.model.Add(sum(term_vars) == 1)


def _forbid_course_assignment(ctx: OptimizerModel, course_id: int) -> None:
    """Force `course_id` to never be assigned to any term."""
    for (cid, _tid), var in ctx.assign.items():
        if cid == course_id:
            ctx.model.Add(var == 0)


def _fix_course_to_term(ctx: OptimizerModel, course_id: int, term_id: int) -> None:
    """Force `course_id` to be assigned specifically to `term_id`, and no other term."""
    for (cid, tid), var in ctx.assign.items():
        if cid == course_id:
            ctx.model.Add(var == (1 if tid == term_id else 0))


def _add_program_credit_floor_constraint(ctx: OptimizerModel) -> None:
    """Force the plan's newly-assigned credit hours to reach the scenario's
    major(s)' officially published total_credit_hours, net of what the student
    already earned -- `_add_requirement_coverage_constraints` alone only forces
    each *named* requirement node, which can understate a real degree's total
    (e.g. an unmodeled free-elective slot). Skipped if the scenario opted out
    via enforce_program_credit_minimum, or if no in-scope program has a
    published total to compare against."""
    if not ctx.scenario.enforce_program_credit_minimum:
        return
    remaining = ctx.candidates.credit_floor_remaining
    if remaining is None or remaining <= 0:
        return
    total_scaled_credits = sum(
        scaled_credits(ctx.candidates.courses_by_id[course_id].credit_hours) * var
        for (course_id, _term_id), var in ctx.assign.items()
    )
    ctx.model.Add(total_scaled_credits >= scaled_credits(remaining))


def collect_leaf_satisfactions(
    ctx: OptimizerModel, solver: cp_model.CpSolver
) -> dict[int, set[int]]:
    """After solving, return each satisfied COURSE/COURSE_GROUP leaf's requirement_node_id
    mapped to its satisfying course id(s) (for COURSE, just its own course; for
    COURSE_GROUP, every member whose indicator solved to 1). Used by
    `optimizer_persistence` to build `requirement_allocations` rows."""
    result: dict[int, set[int]] = {}
    for req_set in ctx.candidates.requirement_sets:
        _collect_leaf_satisfactions_from_nodes(ctx, solver, req_set.nodes, result)
    return result


def _collect_leaf_satisfactions_from_nodes(
    ctx: OptimizerModel,
    solver: cp_model.CpSolver,
    nodes: list[RequirementNodeOut],
    result: dict[int, set[int]],
) -> None:
    """Recursively populate `result` for every COURSE/COURSE_GROUP leaf under `nodes`."""
    for node in nodes:
        _collect_leaf_satisfaction_for_node(ctx, solver, node, result)
        _collect_leaf_satisfactions_from_nodes(ctx, solver, node.children, result)


def _collect_leaf_satisfaction_for_node(
    ctx: OptimizerModel,
    solver: cp_model.CpSolver,
    node: RequirementNodeOut,
    result: dict[int, set[int]],
) -> None:
    """Record one node's satisfying course id(s) in `result`, if it's a solved-satisfied
    COURSE or COURSE_GROUP leaf."""
    indicator = ctx.node_indicators.get(node.requirement_node_id)
    if indicator is None or not solver.Value(indicator):
        return
    if node.node_type == "COURSE" and node.required_course is not None:
        satisfied = {
            course_id
            for (node_id, course_id), usage in ctx.node_course_usage_indicators.items()
            if node_id == node.requirement_node_id and solver.Value(usage)
        }
        if not satisfied and node.is_satisfied:
            eligible_ids = {node.required_course.course_id} | ctx.candidates.equivalent_course_ids.get(
                node.required_course.course_id, set()
            )
            satisfied = eligible_ids & ctx.candidates.completed_course_ids
        if satisfied:
            result[node.requirement_node_id] = satisfied
    elif node.node_type == "COURSE_GROUP" and node.course_group is not None:
        member_ids = _eligible_group_member_ids(ctx, node)
        satisfied = {
            course_id
            for (node_id, course_id), usage in ctx.node_course_usage_indicators.items()
            if node_id == node.requirement_node_id and course_id in member_ids and solver.Value(usage)
        }
        if not satisfied and node.is_satisfied:
            completed_candidates = {
                equivalent_id
                for member_id in member_ids
                for equivalent_id in ({member_id} | ctx.candidates.equivalent_course_ids.get(member_id, set()))
            }
            satisfied = completed_candidates & ctx.candidates.completed_course_ids
        if satisfied:
            result[node.requirement_node_id] = satisfied
