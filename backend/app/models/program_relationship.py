"""Links between programs, e.g. an emphasis being tied to a specific major (no data yet)."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProgramRelationship(Base):
    __tablename__ = "academic_program_relationships"

    academic_program_relationship_id: Mapped[int] = mapped_column(primary_key=True)
    parent_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.academic_program_id")
    )
    child_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.academic_program_id")
    )
    relationship_type: Mapped[str] = mapped_column(String(30))
