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
    prerequisite_indicators: dict[tuple[int, int, bool], cp_model.IntVar] = field(default_factory=dict)
    term_credit_totals: dict[int, cp_model.LinearExpr] = field(default_factory=dict)
    term_used_indicators: dict[int, cp_model.IntVar] = field(default_factory=dict)
    graduation_index_var: cp_model.IntVar | None = None
    heaviest_term_credits_var: cp_model.IntVar | None = None
    credit_requirement_node_ids: set[int] = field(default_factory=set)
    unmodeled_prerequisite_course_ids: set[int] = field(default_factory=set)
    unmodeled_prerequisite_node_ids: set[int] = field(default_factory=set)
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
    _add_prerequisite_ordering_constraints(ctx)
    _add_term_credit_constraints(ctx)
    _add_requirement_coverage_constraints(ctx)
    _add_hard_preference_constraints(ctx)
    return ctx


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
        return course_assigned_any_term(ctx, node.required_course.course_id)
    if node.node_type == "COURSE_GROUP" and node.course_group is not None:
        return _group_satisfaction_indicator(ctx, node)
    if node.node_type == "CREDIT_REQUIREMENT":
        ctx.credit_requirement_node_ids.add(node.requirement_node_id)
        return _constant_bool(ctx, True)
    if child_indicators:
        return _aggregate_indicator(ctx, node, child_indicators)
    return _constant_bool(ctx, False)


def _group_satisfaction_indicator(ctx: OptimizerModel, node: RequirementNodeOut) -> cp_model.IntVar:
    """Return a 0/1 indicator for a COURSE_GROUP leaf: satisfied once at least
    `required_count` members are done (completed or assigned by the solver)."""
    member_ids = ctx.candidates.group_members.get(node.course_group.course_group_id, set())
    member_indicators = [course_satisfaction_indicator(ctx, cid) for cid in member_ids]
    threshold = node.required_count or 1
    return _at_least_indicator(ctx, member_indicators, threshold)


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
        _add_prerequisite_constraints_for_course(ctx, course_id, prerequisite_roots)


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
    """Dispatch one prerequisite-subtree node to a 0/1 satisfaction indicator. Leaf types
    the solver has no data to verify (STANDING/EXAM/CONSENT/OTHER/COURSE_GROUP/etc.) are
    assumed satisfiable and flagged, mirroring how CREDIT_REQUIREMENT requirement-tree
    leaves are handled -- the product spec already assumes these are pre-approved outside
    the tool (see PDS §12)."""
    if node.node_type == "COURSE" and node.required_course is not None:
        return _course_satisfied_before(
            ctx, node.required_course.course_id, before_term, same_term_allowed
        )
    if node.children:
        return _aggregate_prerequisite_indicator(ctx, node, before_term, same_term_allowed)
    ctx.unmodeled_prerequisite_node_ids.add(node.course_rule_node_id)
    return _constant_bool(ctx, True)


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
    earlier term (same term too, if `same_term_allowed`). A prerequisite course the
    closure cap excluded from the candidate set is assumed satisfiable (flagged, not
    force-failed), so a modeling limit never manufactures false infeasibility."""
    if course_id in ctx.candidates.completed_course_ids:
        return _constant_bool(ctx, True)
    if course_id not in ctx.candidates.courses_by_id:
        ctx.unmodeled_prerequisite_course_ids.add(course_id)
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
    minimum, maximum = bounds_by_term_id.get(
        term.term_id, (ctx.scenario.default_minimum_credits, ctx.scenario.default_maximum_credits)
    )
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
        result[node.requirement_node_id] = {node.required_course.course_id}
    elif node.node_type == "COURSE_GROUP" and node.course_group is not None:
        member_ids = ctx.candidates.group_members.get(node.course_group.course_group_id, set())
        satisfied = {
            cid
            for cid in member_ids
            if cid in ctx.course_satisfaction_indicators and solver.Value(ctx.course_satisfaction_indicators[cid])
        }
        if satisfied:
            result[node.requirement_node_id] = satisfied
