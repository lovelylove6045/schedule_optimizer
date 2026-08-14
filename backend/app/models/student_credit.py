"""Completed/in-progress coursework, transfer credit, AP/IB, etc. (no data yet)."""

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StudentCredit(Base):
    __tablename__ = "student_credits"

    student_credit_id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.student_id"))
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.course_id"))
    source_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.term_id"))
    external_course_code: Mapped[str | None] = mapped_column(String(60))
    external_course_title: Mapped[str | None] = mapped_column(String(250))
    credits_earned: Mapped[float | None] = mapped_column(Numeric(5, 2))
    grade: Mapped[str | None] = mapped_column(String(5))
    is_in_residence: Mapped[bool] = mapped_column(default=False)
    approved_requirement_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_nodes.requirement_node_id")
    )
    notes: Mapped[str | None] = mapped_column(Text)
