"""Which major(s)/minor(s) the student is optimizing for within a scenario.

`program_role` replaces an earlier `is_primary: bool` column: the design doc's
validation rule ("exactly one PRIMARY_MAJOR per planning scenario", §9.2)
needs to distinguish PRIMARY_MAJOR from SECOND_MAJOR/MINOR/EMPHASIS, which a
single boolean can't express. Safe to change outright (no data loaded here
yet - Phase 2/3 territory)."""

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import SCENARIO_PROGRAM_ROLE_ENUM, ScenarioProgramRole


class ScenarioProgram(Base):
    __tablename__ = "scenario_programs"

    scenario_program_id: Mapped[int] = mapped_column(primary_key=True)
    planning_scenario_id: Mapped[int] = mapped_column(
        ForeignKey("planning_scenarios.planning_scenario_id")
    )
    academic_program_id: Mapped[int] = mapped_column(
        ForeignKey("academic_programs.academic_program_id")
    )
    program_role: Mapped[ScenarioProgramRole] = mapped_column(SCENARIO_PROGRAM_ROLE_ENUM)
