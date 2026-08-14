from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CourseTagMap(Base):
    __tablename__ = "course_tag_map"

    course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id"), primary_key=True)
    course_tag_id: Mapped[int] = mapped_column(
        ForeignKey("course_tags.course_tag_id"), primary_key=True
    )
