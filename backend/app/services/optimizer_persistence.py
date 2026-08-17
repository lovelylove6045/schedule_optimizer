"""Writes one solver-generated `optimizer_service.GeneratedPlan` out to `degree_plans`
plus its `plan_courses`, `requirement_allocations` (including already-completed
`student_credits` allocations), and `optimization_messages`. A course satisfying more
than one requirement node is represented by multiple `requirement_allocations` rows
pointing at the same `plan_course`/`student_credit` -- the schema has no separate
`is_shared` flag, so that's how double counting shows up.

`persist_plan` only flushes, never commits: like the rest of this codebase's request-
scoped `Session` (see `app/database.py`), committing is the caller's decision (the
Phase 4 API route, or a test's transaction-rollback fixture)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.degree_plan import DegreePlan
from app.models.enums import ScenarioPreferenceType, ScenarioProgramRole
from app.models.optimization_message import OptimizationMessage
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.scenario_preference import ScenarioPreference
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_term import ScenarioTerm
from app.models.student_credit import StudentCredit
from app.models.overlap_policy import OverlapPolicy
from app.schemas.course import CourseOut
from app.schemas.plan import DegreePlanOut, OptimizationMessageOut, PlanCourseOut
from app.services.common import load_courses_by_id
from app.services.credit_matching_service import COMPLETED_STATUS
from app.services.optimizer_service import GeneratedPlan

INFEASIBLE_STATUS = "INFEASIBLE"
VALID_STATUS = "VALID"
VALID_WITH_WARNINGS_STATUS = "VALID_WITH_WARNINGS"


def persist_plan(
    db: Session, planning_scenario_id: int, student_id: int, generated_plan: GeneratedPlan
) -> DegreePlan:
    """Persist (flush, not commit) one `GeneratedPlan`: a `degree_plans` row, its
    `plan_courses`/`requirement_allocations` (skipped if infeasible), and any
    `optimization_messages`."""
    plan = _create_degree_plan(db, planning_scenario_id, generated_plan)
    db.flush()
    if generated_plan.infeasibility_reason is not None:
        _add_message(db, plan.degree_plan_id, "ERROR", "INFEASIBLE", generated_plan.infeasibility_reason)
        _add_suggested_adjustments_message(db, plan.degree_plan_id, planning_scenario_id)
        db.flush()
        return plan
    plan_courses_by_course_id = _create_plan_courses(db, plan.degree_plan_id, generated_plan)
    db.flush()
    _create_requirement_allocations(db, plan.degree_plan_id, student_id, generated_plan, plan_courses_by_course_id)
    _add_diagnostic_messages(db, plan.degree_plan_id, generated_plan)
    db.flush()
    _refresh_warning_status(db, plan)
    db.flush()
    return plan


def _create_degree_plan(db: Session, planning_scenario_id: int, generated_plan: GeneratedPlan) -> DegreePlan:
    """Insert (unflushed) the `degree_plans` row summarizing one generated plan. The
    strategy label lives in `plan_name` -- the schema has no dedicated strategy_code column."""
    plan = DegreePlan(
        planning_scenario_id=planning_scenario_id,
        plan_name=generated_plan.strategy_code,
        status=_generated_plan_status(generated_plan),
        total_credit_hours=generated_plan.total_credit_hours or None,
        additional_credit_hours=generated_plan.additional_credit_hours,
        projected_graduation_term_id=generated_plan.projected_graduation_term_id,
        solver_status=generated_plan.status,
    )
    db.add(plan)
    return plan


def _generated_plan_status(generated_plan: GeneratedPlan) -> str:
    """Return a status that distinguishes verified modeled validity from unresolved obligations."""
    if generated_plan.infeasibility_reason is not None:
        return INFEASIBLE_STATUS
    has_unresolved = bool(
        generated_plan.credit_requirement_node_ids
        or generated_plan.unmodeled_prerequisite_course_ids
    )
    return VALID_WITH_WARNINGS_STATUS if has_unresolved else VALID_STATUS


def _refresh_warning_status(db: Session, plan: DegreePlan) -> None:
    """Promote a valid plan when persisted diagnostics contain academic warnings."""
    if plan.status != VALID_STATUS:
        return
    has_warning = db.query(OptimizationMessage).filter(
        OptimizationMessage.degree_plan_id == plan.degree_plan_id,
        OptimizationMessage.severity == "WARNING",
    ).first() is not None
    if has_warning:
        plan.status = VALID_WITH_WARNINGS_STATUS


def _create_plan_courses(
    db: Session, degree_plan_id: int, generated_plan: GeneratedPlan
) -> dict[int, PlanCourse]:
    """Insert (unflushed) one `plan_courses` row per assigned course, returning them
    keyed by course_id for the requirement_allocations step."""
    plan_courses_by_course_id: dict[int, PlanCourse] = {}
    for course_id, term_id in generated_plan.assignments.items():
        plan_course = PlanCourse(
            degree_plan_id=degree_plan_id,
            course_id=course_id,
            term_id=term_id,
            credit_hours=generated_plan.courses_by_id[course_id].credit_hours,
        )
        db.add(plan_course)
        plan_courses_by_course_id[course_id] = plan_course
    return plan_courses_by_course_id


def _create_requirement_allocations(
    db: Session,
    degree_plan_id: int,
    student_id: int,
    generated_plan: GeneratedPlan,
    plan_courses_by_course_id: dict[int, PlanCourse],
) -> None:
    """Insert one `requirement_allocations` row per (node, satisfying course) pair."""
    completed_credit_by_course_id = _completed_credit_by_course_id(db, student_id)
    for node_id, course_ids in generated_plan.node_satisfying_course_ids.items():
        for course_id in course_ids:
            _add_one_requirement_allocation(
                db, degree_plan_id, node_id, course_id, plan_courses_by_course_id, completed_credit_by_course_id
            )


def _completed_credit_by_course_id(db: Session, student_id: int) -> dict[int, StudentCredit]:
    """Return the student's completed `student_credits` rows, keyed by course_id."""
    rows = (
        db.query(StudentCredit)
        .filter(StudentCredit.student_id == student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    return {row.course_id: row for row in rows if row.course_id is not None}


def _add_one_requirement_allocation(
    db: Session,
    degree_plan_id: int,
    requirement_node_id: int,
    course_id: int,
    plan_courses_by_course_id: dict[int, PlanCourse],
    completed_credit_by_course_id: dict[int, StudentCredit],
) -> None:
    """Insert one `requirement_allocations` row, linking to whichever of the newly
    assigned `plan_courses` or the student's own `student_credits` accounts for this course."""
    plan_course = plan_courses_by_course_id.get(course_id)
    student_credit = completed_credit_by_course_id.get(course_id)
    if plan_course is None and student_credit is None:
        return
    db.add(
        RequirementAllocation(
            degree_plan_id=degree_plan_id,
            requirement_node_id=requirement_node_id,
            plan_course_id=plan_course.plan_course_id if plan_course else None,
            student_credit_id=student_credit.student_credit_id if student_credit else None,
            credit_hours_applied=_allocation_credit_hours(plan_course, student_credit),
        )
    )


def _allocation_credit_hours(
    plan_course: PlanCourse | None, student_credit: StudentCredit | None
) -> float | None:
    """Return the credit hours to record for one `requirement_allocations` row."""
    if plan_course is not None:
        return plan_course.credit_hours
    if student_credit is not None:
        return student_credit.credits_earned
    return None


def _add_diagnostic_messages(db: Session, degree_plan_id: int, generated_plan: GeneratedPlan) -> None:
    """Add the plan's advisor-signoff and unverified-prerequisite caveats.
    Each caveat is written as exactly one aggregated row. Earlier this emitted one
    row *per* affected node/course, which produced pages of byte-identical warnings
    on a real plan (Aerospace BS surfaced the same closure-cap sentence 24 times) --
    the same information, but unreadable. The trade-off is losing the per-row
    `requirement_node_id`/`course_id` link, so the aggregated text names the
    affected courses instead."""
    _add_credit_requirement_message(db, degree_plan_id, generated_plan)
    _add_unmodeled_prerequisite_course_message(db, degree_plan_id, generated_plan)
    _add_unverified_prerequisite_condition_message(db, degree_plan_id, generated_plan)
    _add_unallocated_external_credit_message(db, degree_plan_id)
    _add_solver_quality_message(db, degree_plan_id, generated_plan)
    _add_overlap_assumption_message(db, degree_plan_id)


def _add_credit_requirement_message(
    db: Session, degree_plan_id: int, generated_plan: GeneratedPlan
) -> None:
    """Warn once that the plan assumes N CREDIT_REQUIREMENT nodes are satisfied elsewhere."""
    count = len(generated_plan.credit_requirement_node_ids)
    if count == 0:
        return
    _add_message(
        db,
        degree_plan_id,
        "WARNING",
        "ADVISOR_SIGNOFF_NEEDED",
        f"{count} requirement(s) are credit-hour placeholders with no specific course attached "
        "(e.g. an unlisted ROTC or approved-minor credit slot). This plan assumes they're "
        "satisfied outside the tool -- confirm them with an advisor.",
    )


def _add_unmodeled_prerequisite_course_message(
    db: Session, degree_plan_id: int, generated_plan: GeneratedPlan
) -> None:
    """Warn once, naming the courses, that some prerequisites sit outside the modeled
    candidate set and were assumed satisfiable rather than scheduled."""
    course_ids = generated_plan.unmodeled_prerequisite_course_ids
    if not course_ids:
        return
    _add_message(
        db,
        degree_plan_id,
        "WARNING",
        "PREREQUISITE_NOT_MODELED",
        f"{len(course_ids)} prerequisite course(s) fall outside this plan's modeled course set "
        f"({_course_code_summary(db, course_ids)}). The plan assumes you can satisfy them and "
        "doesn't schedule them -- double-check these with an advisor.",
    )


def _add_unverified_prerequisite_condition_message(
    db: Session, degree_plan_id: int, generated_plan: GeneratedPlan
) -> None:
    """Note once how many non-course prerequisite conditions the solver can't verify."""
    count = len(generated_plan.unmodeled_prerequisite_node_ids)
    if count == 0:
        return
    _add_message(
        db,
        degree_plan_id,
        "INFO",
        "UNVERIFIED_PREREQUISITE_TYPE",
        f"{count} prerequisite condition(s) attached to scheduled courses are advisory "
        "recommendations, placement exams, consent, or other catalog conditions the optimizer "
        "can't verify. They don't affect optimization proof status; confirm them with an advisor.",
    )


def _add_unallocated_external_credit_message(db: Session, degree_plan_id: int) -> None:
    """Warn when unstructured transfer/external credit was not counted toward the degree."""
    plan = db.get(DegreePlan, degree_plan_id)
    scenario = db.get(PlanningScenario, plan.planning_scenario_id)
    count = db.query(StudentCredit).filter(
        StudentCredit.student_id == scenario.student_id,
        StudentCredit.status == COMPLETED_STATUS,
        StudentCredit.course_id.is_(None),
    ).count()
    if count == 0:
        return
    _add_message(
        db,
        degree_plan_id,
        "WARNING",
        "EXTERNAL_CREDIT_NOT_AUTO_APPLIED",
        f"{count} external or transfer credit record(s) have no catalog-course mapping and "
        "were not automatically counted toward the degree minimum. Confirm applicability "
        "with an advisor.",
    )


def _add_solver_quality_message(
    db: Session, degree_plan_id: int, generated_plan: GeneratedPlan
) -> None:
    """Report objective-stage proof status and deadline truncation without overstating optimality."""
    if generated_plan.objective_stage_results:
        _add_message(
            db,
            degree_plan_id,
            "INFO",
            "OBJECTIVE_STAGE_RESULTS",
            "Lexicographic objective stages: " + ", ".join(generated_plan.objective_stage_results) + ".",
        )
    if generated_plan.deadline_exhausted:
        _add_message(
            db,
            degree_plan_id,
            "INFO",
            "SOLVER_DEADLINE_REACHED",
            "The hard solver deadline was reached. This is the best valid solution found; later stages or alternatives may be skipped.",
        )


def _add_overlap_assumption_message(db: Session, degree_plan_id: int) -> None:
    """Warn when a plan actually shares coursework without an explicit policy."""
    plan = db.get(DegreePlan, degree_plan_id)
    selected_ids = {
        program_id
        for (program_id,) in db.query(ScenarioProgram.academic_program_id)
        .filter(ScenarioProgram.planning_scenario_id == plan.planning_scenario_id)
        .all()
    }
    if len(selected_ids) < 2:
        return
    matching_policy = db.query(OverlapPolicy).filter(
        OverlapPolicy.program_a_id.in_(selected_ids),
        OverlapPolicy.program_b_id.in_(selected_ids),
    ).first()
    if matching_policy is not None or not _has_cross_program_sharing(
        db, degree_plan_id, selected_ids
    ):
        return
    _add_message(
        db,
        degree_plan_id,
        "WARNING",
        "OVERLAP_POLICY_UNVERIFIED",
        "Cross-program sharing is optimized using the prototype's current catalog model. Some program-specific double-counting policies may require advisor verification.",
    )


def _has_cross_program_sharing(
    db: Session, degree_plan_id: int, selected_program_ids: set[int]
) -> bool:
    """Return whether one planned or completed course serves multiple selected programs."""
    allocations = db.query(RequirementAllocation).filter(
        RequirementAllocation.degree_plan_id == degree_plan_id
    ).all()
    set_by_node = _requirement_set_by_node(db, allocations)
    programs_by_set = _selected_programs_by_requirement_set(db, selected_program_ids)
    allocations_by_source: dict[tuple[int | None, int | None], list[RequirementAllocation]] = {}
    for allocation in allocations:
        source = (allocation.plan_course_id, allocation.student_credit_id)
        allocations_by_source.setdefault(source, []).append(allocation)
    return any(
        len(_exclusive_programs_for_allocations(rows, set_by_node, programs_by_set)) > 1
        for rows in allocations_by_source.values()
    )


def _requirement_set_by_node(
    db: Session, allocations: list[RequirementAllocation]
) -> dict[int, int]:
    """Map allocated requirement nodes to their owning requirement sets."""
    node_ids = {allocation.requirement_node_id for allocation in allocations}
    return dict(
        db.query(RequirementNode.requirement_node_id, RequirementNode.requirement_set_id)
        .filter(RequirementNode.requirement_node_id.in_(node_ids))
        .all()
    )


def _selected_programs_by_requirement_set(
    db: Session, selected_program_ids: set[int]
) -> dict[int, set[int]]:
    """Map requirement sets to their selected academic-program owners."""
    rows = db.query(
        ProgramRequirementSet.requirement_set_id,
        ProgramRequirementSet.academic_program_id,
    ).filter(ProgramRequirementSet.academic_program_id.in_(selected_program_ids)).all()
    result: dict[int, set[int]] = {}
    for requirement_set_id, program_id in rows:
        result.setdefault(requirement_set_id, set()).add(program_id)
    return result


def _exclusive_programs_for_allocations(
    allocations: list[RequirementAllocation],
    set_by_node: dict[int, int],
    programs_by_set: dict[int, set[int]],
) -> set[int]:
    """Return exclusive program owners represented by one course's allocations."""
    programs: set[int] = set()
    for allocation in allocations:
        requirement_set_id = set_by_node.get(allocation.requirement_node_id)
        owners = programs_by_set.get(requirement_set_id, set())
        if len(owners) == 1:
            programs |= owners
    return programs


def _course_code_summary(db: Session, course_ids: set[int], limit: int = 6) -> str:
    """Render a set of course ids as a short "SUBJ 1234, SUBJ 2345, +N more" string."""
    courses = load_courses_by_id(db, course_ids)
    codes = sorted(f"{course.subject_code} {course.course_number}" for course in courses.values())
    unnamed = len(course_ids) - len(codes)
    shown = codes[:limit]
    remaining = len(codes) - len(shown) + unnamed
    if remaining > 0:
        shown.append(f"+{remaining} more")
    return ", ".join(shown) if shown else "no catalog details available"


def _add_suggested_adjustments_message(
    db: Session, degree_plan_id: int, planning_scenario_id: int
) -> None:
    """For an infeasible plan, add one INFO row listing the specific constraints in
    *this* scenario that could be relaxed to make it solvable (PDS UC-57). Without
    this, an infeasible result only says "no schedule satisfies every hard
    constraint" and leaves the student guessing which knob to turn."""
    scenario = db.get(PlanningScenario, planning_scenario_id)
    if scenario is None:
        return
    suggestions = _collect_relaxation_suggestions(db, scenario)
    if not suggestions:
        return
    _add_message(
        db,
        degree_plan_id,
        "INFO",
        "SUGGESTED_ADJUSTMENTS",
        "Things you could change to make this plan possible: " + "; ".join(suggestions) + ".",
    )


def _collect_relaxation_suggestions(db: Session, scenario: PlanningScenario) -> list[str]:
    """Return the plain-language relaxations available for one scenario, most
    commonly-binding first."""
    suggestions: list[str] = []
    if scenario.target_graduation_term_id is not None:
        suggestions.append("push back or clear your target graduation term")
    if scenario.default_maximum_credits is not None:
        # float() first: the column is Numeric(5, 2), so a persisted scenario reads
        # back as Decimal("9.00") and ":g" would render that literally as "9.00".
        suggestions.append(
            f"raise your per-term maximum above {float(scenario.default_maximum_credits):g} credits"
        )
    if not scenario.allow_summer:
        suggestions.append("allow summer terms")
    if scenario.enforce_program_credit_minimum:
        suggestions.append("turn off requiring the full published credit-hour total for your major")
    suggestions.extend(_scenario_scoped_suggestions(db, scenario.planning_scenario_id))
    return suggestions


def _scenario_scoped_suggestions(db: Session, planning_scenario_id: int) -> list[str]:
    """Return relaxations that depend on the scenario's child rows: excluded terms,
    locked course choices, and additional programs beyond the primary major."""
    suggestions: list[str] = []
    excluded_terms = (
        db.query(ScenarioTerm)
        .filter(ScenarioTerm.planning_scenario_id == planning_scenario_id, ScenarioTerm.is_excluded.is_(True))
        .count()
    )
    if excluded_terms:
        suggestions.append(f"make one of the {excluded_terms} term(s) you excluded available again")
    required_courses = (
        db.query(ScenarioPreference)
        .filter(
            ScenarioPreference.planning_scenario_id == planning_scenario_id,
            ScenarioPreference.preference_type == ScenarioPreferenceType.REQUIRE_COURSE,
        )
        .count()
    )
    if required_courses:
        suggestions.append(f"unlock one of your {required_courses} chosen course(s)")
    extra_programs = (
        db.query(ScenarioProgram)
        .filter(
            ScenarioProgram.planning_scenario_id == planning_scenario_id,
            ScenarioProgram.program_role != ScenarioProgramRole.PRIMARY_MAJOR,
        )
        .count()
    )
    if extra_programs:
        suggestions.append(f"drop one of the {extra_programs} additional program(s)")
    return suggestions


def _add_message(
    db: Session,
    degree_plan_id: int,
    severity: str,
    message_code: str,
    message_text: str,
    requirement_node_id: int | None = None,
    course_id: int | None = None,
) -> None:
    """Insert one `optimization_messages` row (unflushed)."""
    db.add(
        OptimizationMessage(
            degree_plan_id=degree_plan_id,
            severity=severity,
            message_code=message_code,
            message_text=message_text,
            requirement_node_id=requirement_node_id,
            course_id=course_id,
        )
    )


def list_degree_plans_for_scenario(db: Session, planning_scenario_id: int) -> list[DegreePlanOut]:
    """Read back every persisted `DegreePlan` for one scenario, newest first. Lets
    the frontend's results page refetch on page refresh instead of re-running
    `/generate` (which would create new plan rows) every time."""
    plan_ids = (
        db.query(DegreePlan.degree_plan_id)
        .filter(DegreePlan.planning_scenario_id == planning_scenario_id)
        .order_by(DegreePlan.degree_plan_id.desc())
        .all()
    )
    plans = [load_degree_plan(db, plan_id) for (plan_id,) in plan_ids]
    return [plan for plan in plans if plan is not None]


def load_degree_plan(db: Session, degree_plan_id: int) -> DegreePlanOut | None:
    """Read a persisted `DegreePlan` back out, with its courses and messages, as a
    `DegreePlanOut` (used by tests now, and Phase 4's API layer later)."""
    plan = db.get(DegreePlan, degree_plan_id)
    if plan is None:
        return None
    courses_by_id = _load_plan_course_details(db, degree_plan_id)
    return DegreePlanOut(
        degree_plan_id=plan.degree_plan_id,
        planning_scenario_id=plan.planning_scenario_id,
        plan_name=plan.plan_name,
        status=plan.status,
        total_credit_hours=plan.total_credit_hours,
        scheduled_credit_hours=sum(course.credit_hours for course in courses_by_id),
        additional_credit_hours=plan.additional_credit_hours,
        projected_graduation_term_id=plan.projected_graduation_term_id,
        solver_objective_value=plan.solver_objective_value,
        solver_status=plan.solver_status,
        courses=courses_by_id,
        messages=_load_plan_messages(db, degree_plan_id),
    )


def _load_plan_course_details(db: Session, degree_plan_id: int) -> list[PlanCourseOut]:
    """Load one `PlanCourseOut` (with its full course) per `plan_courses` row on this plan."""
    plan_courses = db.query(PlanCourse).filter(PlanCourse.degree_plan_id == degree_plan_id).all()
    courses_by_id = load_courses_by_id(db, {pc.course_id for pc in plan_courses})
    metadata = _plan_course_metadata(db, degree_plan_id, plan_courses)
    return [_plan_course_out(pc, courses_by_id, metadata.get(pc.plan_course_id, {})) for pc in plan_courses]


def _plan_course_out(
    plan_course: PlanCourse, courses_by_id: dict[int, CourseOut], metadata: dict
) -> PlanCourseOut:
    """Convert one `PlanCourse` ORM row plus its already-joined course into a `PlanCourseOut`."""
    return PlanCourseOut(
        plan_course_id=plan_course.plan_course_id,
        course=courses_by_id[plan_course.course_id],
        term_id=plan_course.term_id,
        credit_hours=plan_course.credit_hours,
        placement_source=plan_course.placement_source,
        academic_role=metadata.get("academic_role", "CREDIT_FLOOR"),
        is_removable=metadata.get("is_removable", False),
        is_movable=True,
        is_replaceable=metadata.get("is_replaceable", False),
        selection_reasons=metadata.get("selection_reasons", ["Selected to support degree completion"]),
    )


def _plan_course_metadata(
    db: Session, degree_plan_id: int, plan_courses: list[PlanCourse]
) -> dict[int, dict]:
    """Derive accessible role, editability, and explanation metadata from allocations."""
    plan = db.get(DegreePlan, degree_plan_id)
    scenario_roles = {
        row.academic_program_id: row.program_role
        for row in db.query(ScenarioProgram).filter(
            ScenarioProgram.planning_scenario_id == plan.planning_scenario_id
        ).all()
    }
    allocations = db.query(RequirementAllocation).filter(
        RequirementAllocation.degree_plan_id == degree_plan_id,
        RequirementAllocation.plan_course_id.isnot(None),
    ).all()
    allocations_by_course: dict[int, list[RequirementAllocation]] = {}
    for allocation in allocations:
        allocations_by_course.setdefault(allocation.plan_course_id, []).append(allocation)
    node_ids = {allocation.requirement_node_id for allocation in allocations}
    nodes = {node.requirement_node_id: node for node in db.query(RequirementNode).filter(RequirementNode.requirement_node_id.in_(node_ids)).all()}
    links = db.query(ProgramRequirementSet).filter(
        ProgramRequirementSet.academic_program_id.in_(set(scenario_roles))
    ).all()
    program_ids_by_set: dict[int, set[int]] = {}
    for link in links:
        program_ids_by_set.setdefault(link.requirement_set_id, set()).add(link.academic_program_id)
    return {
        course.plan_course_id: _one_plan_course_metadata(
            course, allocations_by_course.get(course.plan_course_id, []), nodes, program_ids_by_set, scenario_roles
        )
        for course in plan_courses
    }


def _one_plan_course_metadata(
    plan_course: PlanCourse,
    allocations: list[RequirementAllocation],
    nodes: dict[int, RequirementNode],
    program_ids_by_set: dict[int, set[int]],
    scenario_roles: dict[int, ScenarioProgramRole],
) -> dict:
    """Classify and explain one plan course from its actual requirement allocations."""
    requirement_set_ids = {
        nodes[allocation.requirement_node_id].requirement_set_id
        for allocation in allocations
    }
    all_program_ids = {
        program_id
        for requirement_set_id in requirement_set_ids
        for program_id in program_ids_by_set.get(requirement_set_id, set())
    }
    exclusive_program_ids = {
        next(iter(program_ids_by_set[requirement_set_id]))
        for requirement_set_id in requirement_set_ids
        if len(program_ids_by_set.get(requirement_set_id, set())) == 1
    }
    program_ids = exclusive_program_ids or all_program_ids
    roles = {scenario_roles[program_id] for program_id in program_ids if program_id in scenario_roles}
    shared = len(exclusive_program_ids) > 1
    if shared:
        academic_role = "SHARED"
        reasons = ["Satisfies requirements in multiple selected programs"]
    elif ScenarioProgramRole.PRIMARY_MAJOR in roles or allocations and not roles:
        academic_role = "PRIMARY_REQUIRED"
        reasons = ["Satisfies a selected program requirement"]
    elif roles & {ScenarioProgramRole.MINOR, ScenarioProgramRole.EMPHASIS, ScenarioProgramRole.SECOND_MAJOR}:
        academic_role = "ADDITIONAL_PROGRAM"
        reasons = ["Supports an additional academic goal"]
    elif plan_course.placement_source == "STUDENT_ADDED":
        academic_role = "EXPLORATORY"
        reasons = ["Added by the student; not currently counted toward degree progress"]
    else:
        academic_role = "CREDIT_FLOOR"
        reasons = ["Selected to reach the published degree credit minimum"]
    replaceable = any(nodes[allocation.requirement_node_id].node_type == "COURSE_GROUP" for allocation in allocations)
    return {
        "academic_role": academic_role,
        "is_removable": not allocations and plan_course.placement_source == "STUDENT_ADDED",
        "is_replaceable": replaceable,
        "selection_reasons": reasons,
    }


def _load_plan_messages(db: Session, degree_plan_id: int) -> list[OptimizationMessageOut]:
    """Load every `optimization_messages` row for this plan as `OptimizationMessageOut`."""
    rows = db.query(OptimizationMessage).filter(OptimizationMessage.degree_plan_id == degree_plan_id).all()
    return [OptimizationMessageOut.model_validate(row) for row in rows]
