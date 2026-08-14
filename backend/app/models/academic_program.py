from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import PROGRAM_TYPE_ENUM, ProgramType


class AcademicProgram(Base):
    """A major, minor, emphasis, or certificate. `program_type` distinguishes which."""

    __tablename__ = "academic_programs"

    academic_program_id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.department_id"))
    program_code: Mapped[str] = mapped_column(String(60), unique=True)
    program_name: Mapped[str] = mapped_column(String(250))
    program_type: Mapped[ProgramType] = mapped_column(PROGRAM_TYPE_ENUM)
    total_credit_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    is_active: Mapped[bool] = mapped_column(default=True)
