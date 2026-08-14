"""Nested prerequisite/corequisite rule tree for one target course."""

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import (
    COURSE_RULE_NODE_TYPE_ENUM,
    REQUISITE_TYPE_ENUM,
    RULE_OPERATOR_ENUM,
    CourseRuleNodeType,
    RequisiteType,
    RuleOperator,
)


class CourseRuleNode(Base):
    __tablename__ = "course_rule_nodes"

    course_rule_node_id: Mapped[int] = mapped_column(primary_key=True)
    target_course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id"))
    parent_rule_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_rule_nodes.course_rule_node_id")
    )
    requisite_type: Mapped[RequisiteType] = mapped_column(REQUISITE_TYPE_ENUM)
    node_type: Mapped[CourseRuleNodeType] = mapped_column(COURSE_RULE_NODE_TYPE_ENUM)
    rule_operator: Mapped[RuleOperator | None] = mapped_column(RULE_OPERATOR_ENUM)
    required_course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.course_id"))
    required_count: Mapped[int | None]
    minimum_grade: Mapped[str | None] = mapped_column(String(5))
    minimum_total_credits: Mapped[float | None] = mapped_column(Numeric(6, 2))
    text_value: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str | None] = mapped_column(Text)
    required_subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.subject_id"))
    minimum_course_level: Mapped[int | None]
    minimum_standing: Mapped[str | None] = mapped_column(String(20))
    required_academic_program_id: Mapped[int | None] = mapped_column(
        ForeignKey("academic_programs.academic_program_id")
    )
