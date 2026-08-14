from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProgramRequirementSet(Base):
    """Many-to-many bridge: which requirement sets apply to which program."""

    __tablename__ = "program_requirement_sets"

    program_requirement_set_id: Mapped[int] = mapped_column(primary_key=True)
    academic_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.academic_program_id")
    )
    requirement_set_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_sets.requirement_set_id")
    )
    display_order: Mapped[int | None]
