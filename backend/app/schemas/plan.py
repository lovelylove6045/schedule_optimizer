"""Output shapes for reading a persisted `DegreePlan` back out (also reusable
by Phase 4's API layer)."""

from pydantic import BaseModel, ConfigDict

from app.schemas.course import CourseOut


class PlanCourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_course_id: int
    course: CourseOut
    term_id: int
    credit_hours: float
    placement_source: str


class OptimizationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    optimization_message_id: int
    severity: str
    message_code: str | None = None
    message_text: str
    requirement_node_id: int | None = None
    course_id: int | None = None


class DegreePlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    degree_plan_id: int
    planning_scenario_id: int
    plan_name: str | None = None
    status: str
    total_credit_hours: float | None = None
    projected_graduation_term_id: int | None = None
    solver_objective_value: float | None = None
    solver_status: str | None = None
    courses: list[PlanCourseOut] = []
    messages: list[OptimizationMessageOut] = []
