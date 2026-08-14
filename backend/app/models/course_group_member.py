from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CourseGroupMember(Base):
    """Materialized course candidates for a course group (`course_group_courses`)."""

    __tablename__ = "course_group_courses"

    course_group_course_id: Mapped[int] = mapped_column(primary_key=True)
    course_group_id: Mapped[int] = mapped_column(ForeignKey("course_groups.course_group_id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id"))
