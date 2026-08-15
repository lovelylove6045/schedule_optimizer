from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.academic_program import AcademicProgram
from app.schemas.choice import RequirementChoiceOut
from app.schemas.course import CourseGroupMembersOut
from app.services import catalog_service, requirement_choice_service

router = APIRouter(tags=["choices"])


@router.get("/requirement-choices", response_model=list[RequirementChoiceOut])
def list_requirement_choices(
    program_ids: str = Query(..., description="Comma-separated academic_program_ids, e.g. 1,2"),
    completed_course_ids: str = Query(
        "", description="Comma-separated course_ids the student already completed"
    ),
    db: Session = Depends(get_db),
) -> list[RequirementChoiceOut]:
    """Return the elective decision points ("MATH 1214 or MATH 1215") across the
    given programs' requirement trees, so a client can collect the student's
    preferred courses before a scenario is created. Answers are submitted back as
    `REQUIRE_COURSE` entries in `POST /scenarios`'s `preferences`."""
    parsed_program_ids = _parse_id_list(program_ids, "program_ids", required=True)
    _validate_programs_exist(db, parsed_program_ids)
    completed = set(_parse_id_list(completed_course_ids, "completed_course_ids", required=False))
    return requirement_choice_service.list_requirement_choices(db, parsed_program_ids, completed)


@router.get("/course-groups/{course_group_id}/courses", response_model=CourseGroupMembersOut)
def get_course_group_courses(course_group_id: int, db: Session = Depends(get_db)) -> CourseGroupMembersOut:
    """Return one course group's full member list. Lets a client load every option
    for a broad elective pool that `GET /requirement-choices` only previewed
    (`options_truncated=true`), without inlining thousands of courses in that
    response."""
    group = catalog_service.get_course_group_members(db, course_group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Course group not found")
    return group


def _parse_id_list(raw: str, field_name: str, required: bool) -> list[int]:
    """Parse a comma-separated id query string into a list of ints, deduplicated
    while preserving order (program order drives the choice ordering)."""
    try:
        ids = [int(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"{field_name} must be a comma-separated list of integers"
        ) from exc
    if required and not ids:
        raise HTTPException(status_code=400, detail=f"{field_name} must contain at least one id")
    return list(dict.fromkeys(ids))


def _validate_programs_exist(db: Session, program_ids: list[int]) -> None:
    """Raise 404 if any requested academic_program_id is unknown."""
    rows = (
        db.query(AcademicProgram.academic_program_id)
        .filter(AcademicProgram.academic_program_id.in_(program_ids))
        .all()
    )
    missing = set(program_ids) - {row[0] for row in rows}
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown academic_program_id(s): {sorted(missing)}")
