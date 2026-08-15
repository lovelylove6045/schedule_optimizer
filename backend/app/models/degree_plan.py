"""One solver output (a candidate multi-term schedule) for a planning scenario."""

from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class DegreePlan(Base):
    __tablename__ = "degree_plans"

    degree_plan_id: Mapped[int] = mapped_column(primary_key=True)
    planning_scenario_id: Mapped[int] = mapped_column(
        ForeignKey("planning_scenarios.planning_scenario_id")
    )
    plan_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    total_credit_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    additional_credit_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    projected_graduation_term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.term_id"))
    solver_objective_value: Mapped[float | None] = mapped_column(Numeric(10, 4))
    solver_status: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
