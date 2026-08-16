from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.course import CourseOut
from app.schemas.plan import (
    DegreePlanOut,
    PlanComparisonOut,
    PlanCourseAddIn,
    PlanCourseMoveIn,
    PlanCourseSwapIn,
    PlanMetricsOut,
)
from app.schemas.requirement import RequirementSetOut
from app.services import (
    optimizer_persistence,
    plan_comparison_service,
    plan_requirement_service,
    plan_swap_service,
    plan_swap_validation,
    plan_validation_service,
    requirement_choice_service,
)

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


@router.get("/plans/{degree_plan_id}/swap-options", response_model=dict[int, list[CourseOut]])
def get_plan_swap_options(degree_plan_id: int, db: Session = Depends(get_db)) -> dict[int, list[CourseOut]]:
    """Return, per plan_course_id, the alternative courses the plan board can offer
    for that slot -- empty for a plan_course whose requirement names no alternative."""
    if optimizer_persistence.load_degree_plan(db, degree_plan_id) is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return requirement_choice_service.list_swap_options_for_plan(db, degree_plan_id)


@router.post("/plans/{degree_plan_id}/courses/{plan_course_id}/swap", response_model=DegreePlanOut)
def swap_plan_course(
    degree_plan_id: int, plan_course_id: int, payload: PlanCourseSwapIn, db: Session = Depends(get_db)
) -> DegreePlanOut:
    """Replace one plan_courses row's assigned course with an alternative, keeping
    its term. Rejects (422) a course that isn't offered that term, would push
    the term over its credit cap, or has a prerequisite this plan hasn't
    placed early enough -- see `plan_swap_validation`."""
    try:
        plan_swap_service.swap_plan_course(db, degree_plan_id, plan_course_id, payload.new_course_id)
    except plan_swap_service.PlanCourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        plan_swap_service.CourseNotFoundError,
        plan_swap_service.DuplicateCourseError,
        plan_swap_validation.PlanEditConstraintError,
        plan_validation_service.PlanAcademicValidationError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _reload_plan_or_404(db, degree_plan_id)


@router.post("/plans/{degree_plan_id}/courses", response_model=DegreePlanOut)
def add_plan_course(degree_plan_id: int, payload: PlanCourseAddIn, db: Session = Depends(get_db)) -> DegreePlanOut:
    """Add a brand-new course to a plan in a specific term (e.g. an extra
    elective beyond what the solver assigned), subject to the same term-
    offering/credit-cap/prerequisite checks as a swap -- see `plan_swap_validation`."""
    try:
        plan_swap_service.add_plan_course(db, degree_plan_id, payload.course_id, payload.term_id)
    except (plan_swap_service.DegreePlanNotFoundError, plan_swap_service.TermNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        plan_swap_service.CourseNotFoundError,
        plan_swap_service.DuplicateCourseError,
        plan_swap_validation.PlanEditConstraintError,
        plan_validation_service.PlanAcademicValidationError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _reload_plan_or_404(db, degree_plan_id)


@router.delete("/plans/{degree_plan_id}/courses/{plan_course_id}", response_model=DegreePlanOut)
def remove_plan_course(degree_plan_id: int, plan_course_id: int, db: Session = Depends(get_db)) -> DegreePlanOut:
    """Remove one course entirely from a plan, wherever it came from (solver-
    assigned or student-added)."""
    try:
        plan_swap_service.remove_plan_course(db, degree_plan_id, plan_course_id)
    except plan_swap_service.PlanCourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        plan_validation_service.PlanAcademicValidationError,
        plan_swap_validation.PlanEditConstraintError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _reload_plan_or_404(db, degree_plan_id)


@router.post("/plans/{degree_plan_id}/courses/{plan_course_id}/move", response_model=DegreePlanOut)
def move_plan_course(
    degree_plan_id: int,
    plan_course_id: int,
    payload: PlanCourseMoveIn,
    db: Session = Depends(get_db),
) -> DegreePlanOut:
    """Move a course to another term after validating the entire resulting plan."""
    try:
        plan_swap_service.move_plan_course(db, degree_plan_id, plan_course_id, payload.term_id)
    except (plan_swap_service.PlanCourseNotFoundError, plan_swap_service.TermNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        plan_swap_validation.PlanEditConstraintError,
        plan_validation_service.PlanAcademicValidationError,
    ) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _reload_plan_or_404(db, degree_plan_id)


def _reload_plan_or_404(db: Session, degree_plan_id: int) -> DegreePlanOut:
    """Reload a plan's full breakdown after an edit, for the response body."""
    plan = optimizer_persistence.load_degree_plan(db, degree_plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


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
