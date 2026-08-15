"""Small pieces shared by more than one service (currently just course
hydration -- both the prerequisite tree and the requirement tree need to turn
a bag of `course_id`s into full `CourseOut` objects with their subject code)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.subject import Subject
from app.schemas.course import CourseOut


def load_courses_by_id(db: Session, course_ids: set[int]) -> dict[int, CourseOut]:
    """Fetch the given courses (with their subject code) in one query and
    return them as `CourseOut` objects keyed by `course_id`."""
    if not course_ids:
        return {}
    rows = (
        db.query(Course, Subject.subject_code)
        .join(Subject, Subject.subject_id == Course.subject_id)
        .filter(Course.course_id.in_(course_ids))
        .all()
    )
    return {course.course_id: _course_out(course, subject_code) for course, subject_code in rows}


def _course_out(course: Course, subject_code: str) -> CourseOut:
    """Convert a `Course` ORM row plus its already-joined subject code into a `CourseOut`."""
    return CourseOut(
        course_id=course.course_id,
        subject_id=course.subject_id,
        subject_code=subject_code,
        course_number=course.course_number,
        course_title=course.course_title,
        credit_hours=float(course.credit_hours),
        course_level=course.course_level,
        fall_offered=course.fall_offered,
        spring_offered=course.spring_offered,
        summer_offered=course.summer_offered,
        course_type=course.course_type,
    )
