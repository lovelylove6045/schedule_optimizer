"""Nested output shape for `course_rule_nodes` (see catalog_service.get_prerequisite_tree)."""

from pydantic import BaseModel

from app.models.enums import CourseRuleNodeType, RequisiteType, RuleOperator
from app.schemas.course import CourseOut


class PrerequisiteNodeOut(BaseModel):
    course_rule_node_id: int
    requisite_type: RequisiteType
    node_type: CourseRuleNodeType
    rule_operator: RuleOperator | None = None
    required_course: CourseOut | None = None
    required_subject_id: int | None = None
    required_academic_program_id: int | None = None
    required_count: int | None = None
    minimum_grade: str | None = None
    minimum_total_credits: float | None = None
    minimum_course_level: int | None = None
    minimum_standing: str | None = None
    text_value: str | None = None
    source_text: str | None = None
    children: list["PrerequisiteNodeOut"] = []
