from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.planning_scenario import PlanningScenario
from app.schemas.plan import DegreePlanOut
from app.schemas.scenario import AlternativePlansGenerateIn, ScenarioCreate, ScenarioCreateOut, ScenarioProgramIn, ScenarioProgramOut
from app.services import optimizer_persistence, optimizer_service, plan_generation_service, scenario_service
from app.services.scenario_service import ScenarioReferenceNotFoundError, ScenarioValidationError

router = APIRouter(tags=["scenarios"])


@router.post("/scenarios", response_model=ScenarioCreateOut)
def create_scenario(payload: ScenarioCreate, db: Session = Depends(get_db)) -> ScenarioCreateOut:
    """Create one planning scenario (programs, coursework, constraints, objectives)."""
    try:
        scenario = scenario_service.create_scenario(db, payload)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ScenarioReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScenarioCreateOut(planning_scenario_id=scenario.planning_scenario_id)


@router.post("/scenarios/{planning_scenario_id}/generate", response_model=list[DegreePlanOut])
def generate_plans(planning_scenario_id: int, db: Session = Depends(get_db)) -> list[DegreePlanOut]:
    """Run the optimizer for a scenario and persist its resulting plan(s). Always
    returns 200: an infeasible scenario comes back as a plan with status
    "INFEASIBLE" and an explanatory message, not an HTTP error."""
    try:
        return plan_generation_service.generate_and_persist_plans(db, planning_scenario_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scenarios/{planning_scenario_id}/generate/recommended", response_model=DegreePlanOut)
def generate_recommended_plan(
    planning_scenario_id: int, db: Session = Depends(get_db)
) -> DegreePlanOut:
    """Generate and return the recommended plan before any alternatives are solved."""
    try:
        return plan_generation_service.generate_and_persist_recommended_plan(db, planning_scenario_id)
    except optimizer_service.OptimizationCancelledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/scenarios/{planning_scenario_id}/generate/cancel", response_model=dict[str, bool])
def cancel_plan_generation(planning_scenario_id: int) -> dict[str, bool]:
    """Stop the active in-process solver for one scenario when the user cancels."""
    return {"cancelled": optimizer_service.cancel_generation(planning_scenario_id)}


@router.post("/scenarios/{planning_scenario_id}/generate/alternatives", response_model=list[DegreePlanOut])
def generate_alternative_plans(
    planning_scenario_id: int,
    payload: AlternativePlansGenerateIn,
    db: Session = Depends(get_db),
) -> list[DegreePlanOut]:
    """Generate only the explicitly requested alternatives to the recommended plan."""
    try:
        return plan_generation_service.generate_and_persist_alternative_plans(
            db, planning_scenario_id, payload.objective_types
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/scenarios/{planning_scenario_id}/plans", response_model=list[DegreePlanOut])
def list_scenario_plans(planning_scenario_id: int, db: Session = Depends(get_db)) -> list[DegreePlanOut]:
    """Return every already-generated plan for a scenario, newest first. Lets the
    frontend results page reload a scenario's plans (e.g. on page refresh)
    without re-running the optimizer."""
    if db.get(PlanningScenario, planning_scenario_id) is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return optimizer_persistence.list_degree_plans_for_scenario(db, planning_scenario_id)


@router.get("/scenarios/{planning_scenario_id}/programs", response_model=list[ScenarioProgramOut])
def list_scenario_programs(
    planning_scenario_id: int, db: Session = Depends(get_db)
) -> list[ScenarioProgramOut]:
    """Return every major/minor/emphasis already selected for a scenario -- lets
    the results page know the primary program (for overlap suggestions) and
    which programs are already taken."""
    programs = scenario_service.list_scenario_programs(db, planning_scenario_id)
    if programs is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return programs


@router.post("/scenarios/{planning_scenario_id}/programs", response_model=ScenarioProgramOut, status_code=201)
def add_scenario_program(
    planning_scenario_id: int, payload: ScenarioProgramIn, db: Session = Depends(get_db)
) -> ScenarioProgramOut:
    """Add a second major/minor/emphasis to an already-created scenario -- e.g.
    accepting an overlap suggestion after a plan's already been generated --
    so the next `/generate` call accounts for its requirements too."""
    try:
        return scenario_service.add_scenario_program(db, planning_scenario_id, payload)
    except ScenarioReferenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
