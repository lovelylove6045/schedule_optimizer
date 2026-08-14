"""Which requirement_node each plan_course (or student_credit) counts against,
resolving the double-counting/overlap logic for a given plan."""

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RequirementAllocation(Base):
    __tablename__ = "requirement_allocations"

    requirement_allocation_id: Mapped[int] = mapped_column(primary_key=True)
    degree_plan_id: Mapped[int] = mapped_column(ForeignKey("degree_plans.degree_plan_id"))
    requirement_node_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_nodes.requirement_node_id")
    )
    plan_course_id: Mapped[int | None] = mapped_column(ForeignKey("plan_courses.plan_course_id"))
    student_credit_id: Mapped[int | None] = mapped_column(
        ForeignKey("student_credits.student_credit_id")
    )
    credit_hours_applied: Mapped[float | None] = mapped_column(Numeric(5, 2))
