"""Output shapes for the catalog's organizational hierarchy (college -> department).

Phase 5 shipped a program picker over all 147 programs at once, with no way to
narrow by school -- even though `colleges` and `departments.college_id` have
been loaded since Phase 1. These schemas back `GET /colleges` and the
department/college fields now carried on `ProgramOut`, so a client can offer
"pick your school first, then your program"."""

from pydantic import BaseModel, ConfigDict


class CollegeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    college_id: int
    college_code: str
    college_name: str
    is_active: bool


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: int
    department_code: str
    department_name: str
    college_id: int | None = None
    is_active: bool
