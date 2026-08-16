"""Revalidate academic coverage and rebuild allocations after manual plan edits."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_relation import CourseRelation
from app.models.enums import CourseRelationType
from app.models.course_group_member import CourseGroupMember
from app.models.degree_plan import DegreePlan
from app.models.optimization_message import OptimizationMessage
from app.models.overlap_policy import OverlapPolicy
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.scenario_program import ScenarioProgram
from app.models.student_credit import StudentCredit
from app.models.term import Term
from app.schemas.requirement import RequirementNodeOut
from app.services import optimizer_candidates, plan_requirement_service, plan_swap_validation


class PlanAcademicValidationError(Exception):
    """Raised when a proposed manual edit would make the plan academically invalid."""


def validate_and_reallocate_plan(db: Session, degree_plan_id: int) -> DegreePlan:
    """Validate the whole edited plan, rebuild allocations, and refresh its derived totals."""
    plan = db.get(DegreePlan, degree_plan_id)
    plan_swap_validation.validate_existing_plan(db, degree_plan_id)
    _validate_requirement_coverage(db, degree_plan_id)
    _validate_degree_credit_floor(db, plan)
    _rebuild_plan_course_allocations(db, degree_plan_id)
    _validate_overlap_policies(db, degree_plan_id)
    _refresh_plan_metrics(db, plan)
    plan.status = "VALID_WITH_WARNINGS" if _has_academic_warnings(db, degree_plan_id) else "VALID"
    db.flush()
    return plan


def _validate_requirement_coverage(db: Session, degree_plan_id: int) -> None:
    """Raise when any modeled top-level requirement becomes unsatisfied."""
    coverage = plan_requirement_service.get_plan_requirement_coverage(db, degree_plan_id) or []
    unsatisfied = [
        node.node_name or f"requirement #{node.requirement_node_id}"
        for requirement_set in coverage
        for node in requirement_set.nodes
        if not _node_valid_with_unresolved_credit(node)
    ]
    if unsatisfied:
        raise PlanAcademicValidationError(
            "This edit would leave required academic coverage incomplete: " + ", ".join(unsatisfied[:4])
        )


def _node_valid_with_unresolved_credit(node: RequirementNodeOut) -> bool:
    """Treat CREDIT_REQUIREMENT leaves as unresolved warnings while checking modeled coverage."""
    if node.node_type == "CREDIT_REQUIREMENT":
        return True
    if node.is_satisfied:
        return True
    if not node.children:
        return bool(node.is_satisfied)
    child_results = [_node_valid_with_unresolved_credit(child) for child in node.children]
    if node.node_operator == "ANY":
        return any(child_results)
    if node.node_operator == "N_OF":
        return sum(child_results) >= (node.required_count or 1)
    return all(child_results)


def _validate_degree_credit_floor(db: Session, plan: DegreePlan) -> None:
    """Require enough degree-applicable planned credit to preserve the published major floor."""
    scenario = db.get(PlanningScenario, plan.planning_scenario_id)
    if not scenario.enforce_program_credit_minimum:
        return
    candidates = optimizer_candidates.build_candidate_course_set(db, scenario)
    if candidates.credit_floor_remaining is None:
        return
    rows = db.query(PlanCourse.course_id, PlanCourse.credit_hours).filter(
        PlanCourse.degree_plan_id == plan.degree_plan_id
    ).all()
    applicable = sum(
        float(credits) for course_id, credits in rows if course_id in candidates.assignable_course_ids
    )
    if applicable + 0.01 < candidates.credit_floor_remaining:
        raise PlanAcademicValidationError(
            "This edit would drop degree-applicable credits below the published major minimum."
        )


def _rebuild_plan_course_allocations(db: Session, degree_plan_id: int) -> None:
    """Replace stale plan-course allocations with allocations supported by the edited courses."""
    nodes = _scenario_leaf_nodes(db, degree_plan_id)
    if not nodes:
        return
    db.query(RequirementAllocation).filter(
        RequirementAllocation.degree_plan_id == degree_plan_id,
        RequirementAllocation.plan_course_id.isnot(None),
    ).delete(synchronize_session=False)
    plan_courses = db.query(PlanCourse).filter(PlanCourse.degree_plan_id == degree_plan_id).all()
    plan_courses_by_course_id = {row.course_id: row for row in plan_courses}
    for node in nodes:
        matching_ids = _matching_plan_course_ids(db, node, set(plan_courses_by_course_id))
        for course_id in _minimal_contributing_ids(db, node, matching_ids):
            plan_course = plan_courses_by_course_id[course_id]
            db.add(
                RequirementAllocation(
                    degree_plan_id=degree_plan_id,
                    requirement_node_id=node.requirement_node_id,
                    plan_course_id=plan_course.plan_course_id,
                    credit_hours_applied=plan_course.credit_hours,
                )
            )


def _scenario_leaf_nodes(db: Session, degree_plan_id: int) -> list[RequirementNode]:
    """Return course and course-group leaves attached to the plan's selected programs."""
    plan = db.get(DegreePlan, degree_plan_id)
    program_ids = [
        program_id
        for (program_id,) in db.query(ScenarioProgram.academic_program_id)
        .filter(ScenarioProgram.planning_scenario_id == plan.planning_scenario_id)
        .all()
    ]
    requirement_set_ids = db.query(ProgramRequirementSet.requirement_set_id).filter(
        ProgramRequirementSet.academic_program_id.in_(program_ids)
    )
    return db.query(RequirementNode).filter(
        RequirementNode.requirement_set_id.in_(requirement_set_ids),
        RequirementNode.node_type.in_(("COURSE", "COURSE_GROUP")),
    ).all()


def _matching_plan_course_ids(
    db: Session, node: RequirementNode, plan_course_ids: set[int]
) -> list[int]:
    """Return edited-plan courses that are legitimate candidates for one leaf node."""
    if node.node_type == "COURSE" and node.required_course_id is not None:
        eligible_ids = {node.required_course_id} | _equivalent_ids(db, {node.required_course_id})
        return sorted(eligible_ids & plan_course_ids)
    if node.node_type != "COURSE_GROUP" or node.course_group_id is None:
        return []
    member_ids = {
        course_id
        for (course_id,) in db.query(CourseGroupMember.course_id)
        .filter(CourseGroupMember.course_group_id == node.course_group_id)
        .all()
    }
    eligible_member_ids = member_ids | _equivalent_ids(db, member_ids)
    rows = db.query(Course.course_id, Course.course_level).filter(
        Course.course_id.in_(eligible_member_ids & plan_course_ids)
    ).all()
    return [
        course_id
        for course_id, level in rows
        if node.minimum_course_level is None or level >= node.minimum_course_level
    ]


def _equivalent_ids(db: Session, required_ids: set[int]) -> set[int]:
    """Return directionally valid cross-listed/equivalent alternatives for requirement ids."""
    if not required_ids:
        return set()
    rows = db.query(CourseRelation).filter(
        CourseRelation.relation_type.in_(
            (CourseRelationType.CROSS_LISTED, CourseRelationType.EQUIVALENT)
        ),
        (CourseRelation.course_id.in_(required_ids) | CourseRelation.related_course_id.in_(required_ids)),
    ).all()
    equivalents: set[int] = set()
    for relation in rows:
        if relation.related_course_id in required_ids:
            equivalents.add(relation.course_id)
        if relation.is_bidirectional and relation.course_id in required_ids:
            equivalents.add(relation.related_course_id)
    return equivalents


def _minimal_contributing_ids(
    db: Session, node: RequirementNode, matching_ids: list[int]
) -> list[int]:
    """Choose only the courses needed for this leaf instead of allocating every candidate."""
    if node.node_type == "COURSE":
        return matching_ids[:1]
    courses = db.query(Course).filter(Course.course_id.in_(matching_ids)).order_by(Course.course_id).all()
    selected: list[int] = []
    credits = 0.0
    subjects: set[int] = set()
    required_count = node.required_count or (0 if node.required_credit_hours is not None else 1)
    for course in courses:
        selected.append(course.course_id)
        credits += float(course.credit_hours)
        subjects.add(course.subject_id)
        count_met = len(selected) >= required_count
        credits_met = node.required_credit_hours is None or credits >= float(node.required_credit_hours)
        subjects_met = node.minimum_distinct_subjects is None or len(subjects) >= node.minimum_distinct_subjects
        if count_met and credits_met and subjects_met:
            break
    return selected


def _refresh_plan_metrics(db: Session, plan: DegreePlan) -> None:
    """Refresh degree-applicable credits and projected graduation after an edit."""
    rows = db.query(PlanCourse).filter(PlanCourse.degree_plan_id == plan.degree_plan_id).all()
    scenario = db.get(PlanningScenario, plan.planning_scenario_id)
    candidates = optimizer_candidates.build_candidate_course_set(db, scenario)
    previous_total = float(plan.total_credit_hours or 0)
    if candidates.assignable_course_ids:
        refreshed_total = sum(
            float(row.credit_hours) for row in rows if row.course_id in candidates.assignable_course_ids
        )
    else:
        refreshed_total = sum(float(row.credit_hours) for row in rows)
    plan.total_credit_hours = refreshed_total
    if plan.additional_credit_hours is not None:
        plan.additional_credit_hours = float(plan.additional_credit_hours) + refreshed_total - previous_total
    if rows:
        terms = {term.term_id: term for term in db.query(Term).filter(Term.term_id.in_({row.term_id for row in rows})).all()}
        plan.projected_graduation_term_id = max(rows, key=lambda row: terms[row.term_id].sequence_index).term_id
    else:
        plan.projected_graduation_term_id = None


def _has_academic_warnings(db: Session, degree_plan_id: int) -> bool:
    """Return whether the plan retains any warning-level optimization messages."""
    return db.query(OptimizationMessage).filter(
        OptimizationMessage.degree_plan_id == degree_plan_id,
        OptimizationMessage.severity == "WARNING",
    ).first() is not None


def _validate_overlap_policies(db: Session, degree_plan_id: int) -> None:
    """Reject edited allocations that exceed an explicit cross-program sharing policy."""
    plan = db.get(DegreePlan, degree_plan_id)
    selected_ids = {
        program_id
        for (program_id,) in db.query(ScenarioProgram.academic_program_id).filter(
            ScenarioProgram.planning_scenario_id == plan.planning_scenario_id
        ).all()
    }
    policies = db.query(OverlapPolicy).filter(
        OverlapPolicy.program_a_id.in_(selected_ids),
        OverlapPolicy.program_b_id.in_(selected_ids),
    ).all()
    usage_by_course = _requirement_set_usage_by_course(db, degree_plan_id)
    for policy in policies:
        set_ids_a, set_ids_b = _manual_policy_requirement_sets(db, policy)
        shared_ids = {
            course_id
            for course_id, used_set_ids in usage_by_course.items()
            if used_set_ids & set_ids_a and used_set_ids & set_ids_b
        }
        _enforce_manual_overlap_limit(db, policy, shared_ids)


def _requirement_set_usage_by_course(
    db: Session, degree_plan_id: int
) -> dict[int, set[int]]:
    """Return requirement-set ids to which each planned/completed course is allocated."""
    rows = db.query(RequirementAllocation, RequirementNode.requirement_set_id).join(
        RequirementNode,
        RequirementNode.requirement_node_id == RequirementAllocation.requirement_node_id,
    ).filter(RequirementAllocation.degree_plan_id == degree_plan_id).all()
    usage: dict[int, set[int]] = {}
    for allocation, requirement_set_id in rows:
        course_id = _allocation_course_id(db, allocation)
        if course_id is not None:
            usage.setdefault(course_id, set()).add(requirement_set_id)
    return usage


def _allocation_course_id(db: Session, allocation: RequirementAllocation) -> int | None:
    """Return the catalog course id represented by one allocation row."""
    if allocation.plan_course_id is not None:
        plan_course = db.get(PlanCourse, allocation.plan_course_id)
        return plan_course.course_id if plan_course else None
    if allocation.student_credit_id is not None:
        student_credit = db.get(StudentCredit, allocation.student_credit_id)
        return student_credit.course_id if student_credit else None
    return None


def _manual_policy_requirement_sets(
    db: Session, policy: OverlapPolicy
) -> tuple[set[int], set[int]]:
    """Return each policy side's exclusive requirement-set scope."""
    set_ids_a = _one_policy_side_requirement_sets(
        db, policy.requirement_set_a_id, policy.program_a_id
    )
    set_ids_b = _one_policy_side_requirement_sets(
        db, policy.requirement_set_b_id, policy.program_b_id
    )
    inherited = set_ids_a & set_ids_b
    return set_ids_a - inherited, set_ids_b - inherited


def _one_policy_side_requirement_sets(
    db: Session, requirement_set_id: int | None, program_id: int | None
) -> set[int]:
    """Resolve an explicit requirement set or all sets linked to one program."""
    if requirement_set_id is not None:
        return {requirement_set_id}
    if program_id is None:
        return set()
    rows = db.query(ProgramRequirementSet.requirement_set_id).filter(
        ProgramRequirementSet.academic_program_id == program_id
    ).all()
    return {set_id for (set_id,) in rows}


def _enforce_manual_overlap_limit(
    db: Session, policy: OverlapPolicy, shared_course_ids: set[int]
) -> None:
    """Raise when a disallow or maximum-credit sharing policy is violated."""
    policy_type = policy.policy_type.upper()
    if policy_type in {"DISALLOW", "NO_SHARING", "DISALLOW_SHARING"} and shared_course_ids:
        raise PlanAcademicValidationError(
            "This edit would share a course across programs despite an explicit no-sharing policy."
        )
    if policy_type not in {"MAX_SHARED_CREDITS", "MAX_CREDITS"} or policy.credit_value is None:
        return
    shared_credits = sum(
        float(credits)
        for (credits,) in db.query(Course.credit_hours).filter(
            Course.course_id.in_(shared_course_ids)
        ).all()
    )
    if shared_credits > float(policy.credit_value) + 0.01:
        raise PlanAcademicValidationError(
            f"This edit would share {shared_credits:g} credits, over the explicit "
            f"{float(policy.credit_value):g}-credit policy limit."
        )
