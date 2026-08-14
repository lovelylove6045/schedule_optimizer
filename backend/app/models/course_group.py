from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CourseGroup(Base):
    """Named set of courses that can satisfy an elective/alternative requirement."""

    __tablename__ = "course_groups"

    course_group_id: Mapped[int] = mapped_column(primary_key=True)
    course_group_code: Mapped[str] = mapped_column(String(60), unique=True)
    course_group_name: Mapped[str] = mapped_column(String(250))
    course_group_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
