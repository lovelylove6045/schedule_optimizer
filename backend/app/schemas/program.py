from pydantic import BaseModel, ConfigDict

from app.models.enums import ProgramType
from app.schemas.course import CourseOut


class ProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    academic_program_id: int
    department_id: int
    program_code: str
    program_name: str
    program_type: ProgramType
    total_credit_hours: float | None
    is_active: bool

    # Resolved through departments -> colleges by `catalog_service.list_programs`
    # so a client can group/filter the 147-program catalog by school without a
    # second round-trip. Nullable because `departments.college_id` is nullable
    # in the schema (every currently-loaded department does have one).
    department_code: str | None = None
    department_name: str | None = None
    college_id: int | None = None
    college_code: str | None = None
    college_name: str | None = None
    compatible_parent_program_ids: list[int] = []


class ProgramOverlapOut(BaseModel):
    """Return an estimated catalog-level overlap after inherited sets are removed."""

    academic_program_id: int
    program_code: str
    program_name: str
    program_type: ProgramType
    total_credit_hours: float | None
    overlap_course_count: int
    overlap_credit_hours: float
    # Share of this program's own credit hours already covered by the overlap,
    # e.g. 0.8 means adding this program would need roughly 20% new coursework.
    # Not capped at 1.0: a program can require fewer credits than the sum of
    # its listed courses (e.g. it only needs some of them), so full or
    # over-covered overlap can read above 100%.
    overlap_ratio: float | None
    overlap_courses: list[CourseOut]
