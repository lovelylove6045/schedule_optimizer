"""Human-readable diagnostics attached to a plan, e.g. "prerequisite waived", "infeasible term"."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OptimizationMessage(Base):
    __tablename__ = "optimization_messages"

    optimization_message_id: Mapped[int] = mapped_column(primary_key=True)
    degree_plan_id: Mapped[int] = mapped_column(ForeignKey("degree_plans.degree_plan_id"))
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    message_code: Mapped[str | None] = mapped_column(String(60))
    message_text: Mapped[str] = mapped_column(Text)
    requirement_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_nodes.requirement_node_id")
    )
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.course_id"))
