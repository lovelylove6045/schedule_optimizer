"""Derives `GET /plans/compare` metrics for one persisted degree plan: per-term
credit totals (max/avg), how many SUMMER terms it actually uses, and how many
credit hours come from courses that satisfy more than one requirement node
(the double-counting signal `optimizer_persistence` records as multiple
`requirement_allocations` rows pointing at the same course/credit)."""

from __future__ import annotations

from statistics import mean

from sqlalchemy.orm import Session

from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.requirement_allocation import RequirementAllocation
from app.models.term import Term
from app.schemas.plan import PlanMetricsOut

SUMMER_TERM_TYPE = "SUMMER"


def compute_plan_metrics(db: Session, degree_plan_id: int) -> PlanMetricsOut | None:
    """Return one plan's `GET /plans/compare` metrics, or `None` if it doesn't exist."""
    plan = db.get(DegreePlan, degree_plan_id)
    if plan is None:
        return None
    term_credit_totals = _term_credit_totals(db, degree_plan_id)
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


def _overlap_credit_hours(db: Session, degree_plan_id: int) -> float:
    """Return total credit hours from courses/credits that satisfy 2+ requirement
    nodes on this plan (each such course counted once, not once per node)."""
    rows = db.query(RequirementAllocation).filter(RequirementAllocation.degree_plan_id == degree_plan_id).all()
    allocations_by_source = _group_allocations_by_source(rows)
    return sum(
        float(allocations[0].credit_hours_applied or 0)
        for allocations in allocations_by_source.values()
        if len(allocations) > 1
    )


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
