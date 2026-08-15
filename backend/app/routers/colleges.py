from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.college import CollegeOut
from app.services import catalog_service

router = APIRouter(tags=["colleges"])


@router.get("/colleges", response_model=list[CollegeOut])
def list_colleges(db: Session = Depends(get_db)) -> list[CollegeOut]:
    """Return every college/school, so a client can ask "which school?" before
    narrowing the 147-program catalog down to one program."""
    return catalog_service.list_colleges(db)
