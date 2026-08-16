"""Derives `GET /plans/compare` metrics for one persisted degree plan: per-term
credit totals (max/avg), how many SUMMER terms it actually uses, and how many
credit hours come from courses that satisfy more than one requirement node
(the double-counting signal `optimizer_persistence` records as multiple
`requirement_allocations` rows pointing at the same course/credit)."""

from __future__ import annotations

from statistics import mean

from sqlalchemy.orm import Session

from app.models.academic_program import AcademicProgram
from app.models.degree_plan import DegreePlan
from app.models.course import Course
from app.models.optimization_message import OptimizationMessage
from app.models.plan_course import PlanCourse
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.scenario_program import ScenarioProgram
from app.models.term import Term
from app.schemas.plan import PlanMetricsOut

SUMMER_TERM_TYPE = "SUMMER"


def compute_plan_metrics(db: Session, degree_plan_id: int) -> PlanMetricsOut | None:
    """Return one plan's `GET /plans/compare` metrics, or `None` if it doesn't exist."""
    plan = db.get(DegreePlan, degree_plan_id)
    if plan is None:
        return None
    term_credit_totals = _term_credit_totals(db, degree_plan_id)
    high_level_counts = _term_high_level_counts(db, degree_plan_id)
    return PlanMetricsOut(
        degree_plan_id=plan.degree_plan_id,
        plan_name=plan.plan_name,
        status=plan.status,
        total_credit_hours=plan.total_credit_hours,
        additional_credit_hours=plan.additional_credit_hours,
        projected_graduation_term_id=plan.projected_graduation_term_id,
        max_term_credit_hours=max(term_credit_totals.values()) if term_credit_totals else None,
        avg_term_credit_hours=mean(term_credit_totals.values()) if term_credit_totals else None,
        summer_term_count=_summer_term_count(db, degree_plan_id),
        overlap_credit_hours=_overlap_credit_hours(db, degree_plan_id),
        workload_credit_spread=(
            max(term_credit_totals.values()) - min(term_credit_totals.values())
            if term_credit_totals else None
        ),
        max_high_level_courses=max(high_level_counts.values(), default=0),
        high_level_course_spread=(
            max(high_level_counts.values()) - min(high_level_counts.values())
            if high_level_counts else 0
        ),
        selected_programs=_selected_program_names(db, plan.planning_scenario_id),
        warning_codes=_warning_codes(db, degree_plan_id),
    )


def _term_credit_totals(db: Session, degree_plan_id: int) -> dict[int, float]:
    """Return each used term_id's summed `plan_courses.credit_hours` for this plan."""
    rows = (
        db.query(PlanCourse.term_id, PlanCourse.credit_hours)
        .filter(PlanCourse.degree_plan_id == degree_plan_id)
        .all()
    )
    totals: dict[int, float] = {}
    for term_id, credit_hours in rows:
        totals[term_id] = totals.get(term_id, 0.0) + float(credit_hours)
    return totals


def _summer_term_count(db: Session, degree_plan_id: int) -> int:
    """Return how many distinct SUMMER terms this plan actually assigns a course to."""
    rows = (
        db.query(PlanCourse.term_id)
        .join(Term, Term.term_id == PlanCourse.term_id)
        .filter(PlanCourse.degree_plan_id == degree_plan_id, Term.term_type == SUMMER_TERM_TYPE)
        .distinct()
        .all()
    )
    return len(rows)


def _term_high_level_counts(db: Session, degree_plan_id: int) -> dict[int, int]:
    """Return each used term's count of transparently labeled 4000/5000-level courses."""
    rows = (
        db.query(PlanCourse.term_id, Course.course_level)
        .join(Course, Course.course_id == PlanCourse.course_id)
        .filter(PlanCourse.degree_plan_id == degree_plan_id)
        .all()
    )
    counts: dict[int, int] = {}
    for term_id, course_level in rows:
        counts.setdefault(term_id, 0)
        counts[term_id] += int(course_level >= 4000)
    return counts


def _overlap_credit_hours(db: Session, degree_plan_id: int) -> float:
    """Return credits allocated to exclusive requirements of multiple programs."""
    plan = db.get(DegreePlan, degree_plan_id)
    selected_ids = {
        program_id
        for (program_id,) in db.query(ScenarioProgram.academic_program_id).filter(
            ScenarioProgram.planning_scenario_id == plan.planning_scenario_id
        ).all()
    }
    rows = db.query(RequirementAllocation).filter(RequirementAllocation.degree_plan_id == degree_plan_id).all()
    allocations_by_source = _group_allocations_by_source(rows)
    node_ids = {row.requirement_node_id for row in rows}
    set_by_node = dict(
        db.query(RequirementNode.requirement_node_id, RequirementNode.requirement_set_id)
        .filter(RequirementNode.requirement_node_id.in_(node_ids))
        .all()
    )
    program_ids_by_set = _program_ids_by_requirement_set(db, selected_ids)
    return sum(
        float(allocations[0].credit_hours_applied or 0)
        for allocations in allocations_by_source.values()
        if len(
            _exclusive_program_ids_for_allocations(
                allocations, set_by_node, program_ids_by_set
            )
        ) > 1
    )


def _program_ids_by_requirement_set(
    db: Session, selected_program_ids: set[int]
) -> dict[int, set[int]]:
    """Return selected program owners for their linked requirement sets."""
    rows = db.query(
        ProgramRequirementSet.requirement_set_id,
        ProgramRequirementSet.academic_program_id,
    ).filter(ProgramRequirementSet.academic_program_id.in_(selected_program_ids)).all()
    result: dict[int, set[int]] = {}
    for requirement_set_id, program_id in rows:
        result.setdefault(requirement_set_id, set()).add(program_id)
    return result


def _exclusive_program_ids_for_allocations(
    allocations: list[RequirementAllocation],
    set_by_node: dict[int, int],
    program_ids_by_set: dict[int, set[int]],
) -> set[int]:
    """Return unique program owners represented by one course's allocations."""
    result: set[int] = set()
    for allocation in allocations:
        requirement_set_id = set_by_node.get(allocation.requirement_node_id)
        program_ids = program_ids_by_set.get(requirement_set_id, set())
        if len(program_ids) == 1:
            result |= program_ids
    return result


def _group_allocations_by_source(
    rows: list[RequirementAllocation],
) -> dict[tuple[int | None, int | None], list[RequirementAllocation]]:
    """Group `requirement_allocations` rows by the (plan_course_id, student_credit_id)
    pair identifying which underlying course/credit they came from."""
    grouped: dict[tuple[int | None, int | None], list[RequirementAllocation]] = {}
    for row in rows:
        key = (row.plan_course_id, row.student_credit_id)
        grouped.setdefault(key, []).append(row)
    return grouped


def _selected_program_names(db: Session, planning_scenario_id: int) -> list[str]:
    """Return selected program names in scenario-role order for comparison context."""
    rows = (
        db.query(AcademicProgram.program_name)
        .join(ScenarioProgram, ScenarioProgram.academic_program_id == AcademicProgram.academic_program_id)
        .filter(ScenarioProgram.planning_scenario_id == planning_scenario_id)
        .order_by(ScenarioProgram.scenario_program_id)
        .all()
    )
    return [name for (name,) in rows]


def _warning_codes(db: Session, degree_plan_id: int) -> list[str]:
    """Return distinct warning/assumption codes attached to one plan."""
    rows = db.query(OptimizationMessage.message_code).filter(
        OptimizationMessage.degree_plan_id == degree_plan_id,
        OptimizationMessage.severity == "WARNING",
    ).distinct().all()
    return sorted(code for (code,) in rows if code is not None)
