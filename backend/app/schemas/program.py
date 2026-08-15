from pydantic import BaseModel, ConfigDict

from app.models.enums import ProgramType


class ProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    academic_program_id: int
    department_id: int
    program_code: str
    program_name: str
    program_type: ProgramType
    total_credit_hours: float | None
    is_active: bool
