"""Named, weighted objective terms for the CP-SAT model, e.g. minimize terms vs. balance load."""

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import OPTIMIZATION_OBJECTIVE_TYPE_ENUM, OptimizationObjectiveType


class ScenarioObjective(Base):
    __tablename__ = "scenario_objectives"

    scenario_objective_id: Mapped[int] = mapped_column(primary_key=True)
    planning_scenario_id: Mapped[int] = mapped_column(
        ForeignKey("planning_scenarios.planning_scenario_id")
    )
    objective_type: Mapped[OptimizationObjectiveType] = mapped_column(
        OPTIMIZATION_OBJECTIVE_TYPE_ENUM
    )
    weight: Mapped[float] = mapped_column(Numeric(5, 2), default=1)
    display_order: Mapped[int | None]
