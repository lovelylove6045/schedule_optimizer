"""One what-if planning request: horizon, default workload constraints (no data yet)."""

from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class PlanningScenario(Base):
    __tablename__ = "planning_scenarios"

    planning_scenario_id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.student_id"))
    scenario_name: Mapped[str | None] = mapped_column(String(200))
    start_term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.term_id"))
    target_graduation_term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.term_id"))
    default_minimum_credits: Mapped[float | None] = mapped_column(Numeric(4, 1))
    default_maximum_credits: Mapped[float | None] = mapped_column(Numeric(4, 1))
    full_time_minimum_credits: Mapped[float | None] = mapped_column(Numeric(4, 1))
    allow_summer: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
