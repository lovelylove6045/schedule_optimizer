"""Explicit double-counting rules between selected programs/requirement sets (no data yet)."""

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OverlapPolicy(Base):
    __tablename__ = "overlap_policies"

    overlap_policy_id: Mapped[int] = mapped_column(primary_key=True)
    program_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_programs.academic_program_id")
    )
    program_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_programs.academic_program_id")
    )
    requirement_set_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_sets.requirement_set_id")
    )
    requirement_set_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_sets.requirement_set_id")
    )
    policy_type: Mapped[str] = mapped_column(String(40))
    credit_value: Mapped[float | None] = mapped_column(Numeric(5, 2))
    requires_approval: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
