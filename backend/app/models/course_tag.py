"""Reusable labels for gen-ed categories, labs, interests, etc. (populated in a later phase)."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CourseTag(Base):
    __tablename__ = "course_tags"

    course_tag_id: Mapped[int] = mapped_column(primary_key=True)
    parent_course_tag_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_tags.course_tag_id")
    )
    tag_code: Mapped[str] = mapped_column(String(60), unique=True)
    tag_name: Mapped[str] = mapped_column(String(200))
    tag_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
