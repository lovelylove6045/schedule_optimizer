from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.term import TermOut
from app.services import catalog_service

router = APIRouter(tags=["terms"])


@router.get("/terms", response_model=list[TermOut])
def list_terms(db: Session = Depends(get_db)) -> list[TermOut]:
    """Return every term, chronologically, for scenario-creation clients to pick from."""
    return [TermOut.model_validate(term) for term in catalog_service.list_terms(db)]
