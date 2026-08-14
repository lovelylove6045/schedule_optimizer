"""Soft preferences fed to the solver as objective weights, e.g. preferred course/time-of-day."""

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import SCENARIO_PREFERENCE_TYPE_ENUM, ScenarioPreferenceType


class ScenarioPreference(Base):
    __tablename__ = "scenario_preferences"

    scenario_preference_id: Mapped[int] = mapped_column(primary_key=True)
    planning_scenario_id: Mapped[int] = mapped_column(
        ForeignKey("planning_scenarios.planning_scenario_id")
    )
    preference_type: Mapped[ScenarioPreferenceType] = mapped_column(
        SCENARIO_PREFERENCE_TYPE_ENUM
    )
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.course_id"))
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.term_id"))
    weight: Mapped[float | None] = mapped_column(Numeric(5, 2))
