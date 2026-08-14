"""The central nested requirement tree: fixed courses, alternatives, credit/count
thresholds, and course-group leaves, all scoped to one requirement set."""

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import (
    REQUIREMENT_NODE_TYPE_ENUM,
    RULE_OPERATOR_ENUM,
    RequirementNodeType,
    RuleOperator,
)


class RequirementNode(Base):
    __tablename__ = "requirement_nodes"

    requirement_node_id: Mapped[int] = mapped_column(primary_key=True)
    requirement_set_id: Mapped[int] = mapped_column(
        ForeignKey("requirement_sets.requirement_set_id")
    )
    parent_requirement_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirement_nodes.requirement_node_id")
    )
    node_type: Mapped[RequirementNodeType] = mapped_column(REQUIREMENT_NODE_TYPE_ENUM)
    node_operator: Mapped[RuleOperator | None] = mapped_column(RULE_OPERATOR_ENUM)
    node_name: Mapped[str | None] = mapped_column(String(250))
    required_course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.course_id"))
    course_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_groups.course_group_id")
    )
    required_credit_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    required_count: Mapped[int | None]
    minimum_grade: Mapped[str | None] = mapped_column(String(5))
    minimum_course_level: Mapped[int | None]
    minimum_distinct_subjects: Mapped[int | None]
    display_order: Mapped[int | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    source_text: Mapped[str | None] = mapped_column(Text)
