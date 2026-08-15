"""Nested output shape for `requirement_nodes` (see requirement_service.flatten_requirement_tree
and credit_matching_service.match_completed_courses, which fills in `is_satisfied`)."""

from pydantic import BaseModel

from app.models.enums import RequirementNodeType, RuleOperator
from app.schemas.course import CourseGroupOut, CourseOut


class RequirementNodeOut(BaseModel):
    requirement_node_id: int
    node_type: RequirementNodeType
    node_operator: RuleOperator | None = None
    node_name: str | None = None
    required_course: CourseOut | None = None
    course_group: CourseGroupOut | None = None
    required_credit_hours: float | None = None
    required_count: int | None = None
    minimum_grade: str | None = None
    minimum_course_level: int | None = None
    minimum_distinct_subjects: int | None = None
    display_order: int | None = None
    is_active: bool = True
    source_text: str | None = None
    children: list["RequirementNodeOut"] = []

    # Only populated after credit_matching_service.match_completed_courses runs;
    # a bare flatten_requirement_tree() result leaves this None on every node.
    is_satisfied: bool | None = None

    # Only populated by plan_requirement_service.get_plan_requirement_coverage:
    # true if this leaf's satisfying course, per that plan's persisted
    # requirement_allocations, also satisfies a leaf in a *different* program's
    # requirement tree (the same overlap concept as the MAX_REQUIREMENT_OVERLAP
    # objective, but for one already-generated plan instead of the solver).
    is_shared: bool = False


class RequirementSetOut(BaseModel):
    requirement_set_id: int
    requirement_set_code: str
    requirement_set_name: str
    requirement_set_type: str
    description: str | None = None
    nodes: list[RequirementNodeOut]
