"""Request/response shapes for `POST /scenarios`: one planning scenario submitted
in a single call (selected programs, completed/in-progress coursework, term and
credit constraints, and ranked objectives), matching Phase 5's planned wizard
flow (Screens 1-5) collapsing into one API call at the end."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OptimizationObjectiveType, ScenarioPreferenceType, ScenarioProgramRole


class ScenarioProgramIn(BaseModel):
    academic_program_id: int
    program_role: ScenarioProgramRole


class ScenarioProgramOut(BaseModel):
    """One already-selected program on a scenario (`GET`/`POST
    /scenarios/{id}/programs`) -- lets the frontend show/add majors, minors,
    and emphases on an already-generated plan, not just at scenario creation.
    Carries the program's own code/name (not just its id) so the results page
    can show the student *what* they picked without a second lookup."""

    model_config = ConfigDict(from_attributes=True)

    scenario_program_id: int
    academic_program_id: int
    program_role: ScenarioProgramRole
    program_code: str
    program_name: str


class StudentCreditIn(BaseModel):
    """One completed/in-progress/transfer course a student reports. `course_id` is
    used for institutional courses already in the catalog; `external_course_code`/
    `external_course_title` are for transfer credit with no catalog match."""

    course_id: int | None = None
    source_type: str = "INSTITUTIONAL"
    status: str = "COMPLETED"
    term_id: int | None = None
    external_course_code: str | None = None
    external_course_title: str | None = None
    credits_earned: float | None = None
    grade: str | None = None
    is_in_residence: bool = False


class ScenarioTermIn(BaseModel):
    """A per-term override, e.g. a lower credit cap for a co-op term or an excluded
    study-abroad term."""

    term_id: int
    minimum_credits: float | None = None
    maximum_credits: float | None = None
    is_excluded: bool = False


class ScenarioPreferenceIn(BaseModel):
    preference_type: ScenarioPreferenceType
    course_id: int | None = None
    term_id: int | None = None
    weight: float | None = None


class ScenarioObjectiveIn(BaseModel):
    objective_type: OptimizationObjectiveType
    weight: float = 1
    display_order: int | None = None


class ScenarioCreate(BaseModel):
    student_id: int | None = None
    student_display_name: str | None = None
    start_term_id: int
    target_graduation_term_id: int | None = None
    default_minimum_credits: float | None = None
    default_maximum_credits: float | None = None
    full_time_minimum_credits: float | None = None
    allow_summer: bool = False
    summer_maximum_credits: float = Field(default=9, ge=0, le=18)
    # Forces the generated plan's total credit hours to reach the officially
    # published total_credit_hours of the scenario's major(s), not just the
    # specific requirement nodes those programs happen to name. Default on;
    # a student can turn it off if it makes their scenario infeasible.
    enforce_program_credit_minimum: bool = True
    programs: list[ScenarioProgramIn] = Field(min_length=1)
    completed_courses: list[StudentCreditIn] = []
    term_overrides: list[ScenarioTermIn] = []
    preferences: list[ScenarioPreferenceIn] = []
    objectives: list[ScenarioObjectiveIn] = []


class ScenarioCreateOut(BaseModel):
    planning_scenario_id: int
