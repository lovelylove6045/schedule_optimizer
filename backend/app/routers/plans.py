from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.plan import DegreePlanOut, PlanComparisonOut, PlanMetricsOut
from app.schemas.requirement import RequirementSetOut
from app.services import optimizer_persistence, plan_comparison_service, plan_requirement_service

router = APIRouter(tags=["plans"])


@router.get("/plans/compare", response_model=PlanComparisonOut)
def compare_plans(
    ids: str = Query(..., description="Comma-separated degree_plan_ids, e.g. 1,2,3"),
    db: Session = Depends(get_db),
) -> PlanComparisonOut:
    """Return side-by-side comparison metrics for a comma-separated list of plan ids.
    Declared before `/plans/{degree_plan_id}` so "compare" isn't swallowed by that
    path parameter."""
    plan_ids = _parse_plan_ids(ids)
    metrics = [_load_metrics_or_404(db, plan_id) for plan_id in plan_ids]
    return PlanComparisonOut(plans=metrics)


@router.get("/plans/{degree_plan_id}", response_model=DegreePlanOut)
def get_plan(degree_plan_id: int, db: Session = Depends(get_db)) -> DegreePlanOut:
    """Return one persisted plan's full semester-by-semester breakdown and messages."""
    plan = optimizer_persistence.load_degree_plan(db, degree_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.get("/plans/{degree_plan_id}/requirements", response_model=list[RequirementSetOut])
def get_plan_requirements(degree_plan_id: int, db: Session = Depends(get_db)) -> list[RequirementSetOut]:
    """Return one plan's requirement sets, flattened with is_satisfied/is_shared
    computed against that specific plan's assigned courses."""
    coverage = plan_requirement_service.get_plan_requirement_coverage(db, degree_plan_id)
    if coverage is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return coverage


def _parse_plan_ids(ids: str) -> list[int]:
    """Parse a comma-separated `ids` query string into a non-empty list of ints."""
    try:
        plan_ids = [int(raw_id.strip()) for raw_id in ids.split(",") if raw_id.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ids must be a comma-separated list of integers") from exc
    if not plan_ids:
        raise HTTPException(status_code=400, detail="ids must contain at least one degree_plan_id")
    return plan_ids


def _load_metrics_or_404(db: Session, degree_plan_id: int) -> PlanMetricsOut:
    """Return one plan's comparison metrics, or raise 404 if it doesn't exist."""
    metrics = plan_comparison_service.compute_plan_metrics(db, degree_plan_id)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Plan {degree_plan_id} not found")
    return metrics
