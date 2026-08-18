from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.course import CourseOut
from app.schemas.prerequisite import PrerequisiteNodeOut
from app.services import catalog_service

router = APIRouter(tags=["courses"])


@router.get("/courses", response_model=list[CourseOut])
def search_courses(
    search: str = Query(..., min_length=1, description="Matches subject code, course number, or title"),
    college_id: int | None = Query(None, gt=0),
    department_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> list[CourseOut]:
    """Search courses by code/title with optional college and department filters."""
    return catalog_service.search_courses(db, search, college_id, department_id)


@router.get("/courses/{course_id}/prerequisites", response_model=list[PrerequisiteNodeOut])
def get_course_prerequisites(course_id: int, db: Session = Depends(get_db)) -> list[PrerequisiteNodeOut]:
    """Return a course's prerequisite/corequisite tree(s), or 404 if the course doesn't exist."""
    if catalog_service.get_course(db, course_id) is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return catalog_service.get_prerequisite_tree(db, course_id)
