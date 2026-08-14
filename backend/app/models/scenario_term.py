"""Per-term overrides within a scenario, e.g. a term with a lower credit cap."""

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScenarioTerm(Base):
    __tablename__ = "scenario_terms"

    scenario_term_id: Mapped[int] = mapped_column(primary_key=True)
    planning_scenario_id: Mapped[int] = mapped_column(
        ForeignKey("planning_scenarios.planning_scenario_id")
    )
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.term_id"))
    minimum_credits: Mapped[float | None] = mapped_column(Numeric(4, 1))
    maximum_credits: Mapped[float | None] = mapped_column(Numeric(4, 1))
    is_excluded: Mapped[bool] = mapped_column(default=False)
