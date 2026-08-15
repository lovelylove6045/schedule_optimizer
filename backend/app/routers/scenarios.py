from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.plan import DegreePlanOut
from app.schemas.scenario import ScenarioCreate, ScenarioCreateOut
from app.services import plan_generation_service, scenario_service
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
