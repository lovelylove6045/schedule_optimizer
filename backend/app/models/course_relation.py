from sqlalchemy import ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import COURSE_RELATION_TYPE_ENUM, CourseRelationType


class CourseRelation(Base):
    __tablename__ = "course_relations"

    course_relation_id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id"))
    related_course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id"))
    relation_type: Mapped[CourseRelationType] = mapped_column(COURSE_RELATION_TYPE_ENUM)
    is_bidirectional: Mapped[bool] = mapped_column(default=True)
    maximum_combined_credits: Mapped[float | None] = mapped_column(Numeric(5, 2))
    notes: Mapped[str | None] = mapped_column(Text)
