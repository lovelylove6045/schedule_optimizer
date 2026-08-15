from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import ProgramType
from app.schemas.program import ProgramOut, ProgramOverlapOut
from app.schemas.requirement import RequirementSetOut
from app.services import catalog_service, program_overlap_service, requirement_service

router = APIRouter(tags=["programs"])


@router.get("/programs", response_model=list[ProgramOut])
def list_programs(db: Session = Depends(get_db)) -> list[ProgramOut]:
    """Return every academic program in the catalog, each with its department and
    college resolved so a client can narrow the picker to one school."""
    return catalog_service.list_programs(db)


@router.get("/programs/{program_id}/requirements", response_model=list[RequirementSetOut])
def get_program_requirements(program_id: int, db: Session = Depends(get_db)) -> list[RequirementSetOut]:
    """Return a program's requirement sets, each flattened into its full nested node tree."""
    if catalog_service.get_program(db, program_id) is None:
        raise HTTPException(status_code=404, detail="Program not found")
    requirement_sets = requirement_service.resolve_requirement_sets(db, [program_id])
    flattened = [
        requirement_service.flatten_requirement_tree(db, req_set.requirement_set_id)
        for req_set in requirement_sets
    ]
    return [req_set for req_set in flattened if req_set is not None]


@router.get("/programs/{program_id}/overlap-suggestions", response_model=list[ProgramOverlapOut])
def get_program_overlap_suggestions(
    program_id: int,
    program_type: ProgramType | None = None,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[ProgramOverlapOut]:
    """Return other programs ranked by how much they'd reuse this program's own
    required courses -- e.g. which minors are most "free" alongside this major."""
    if catalog_service.get_program(db, program_id) is None:
        raise HTTPException(status_code=404, detail="Program not found")
    return program_overlap_service.suggest_overlapping_programs(db, program_id, program_type, limit)
