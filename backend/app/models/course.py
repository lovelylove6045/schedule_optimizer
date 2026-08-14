from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Course(Base):
    __tablename__ = "courses"

    course_id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.subject_id"))
    course_number: Mapped[str] = mapped_column(String(20))
    course_level: Mapped[int]
    course_title: Mapped[str] = mapped_column(String(250))
    credit_hours: Mapped[float] = mapped_column(Numeric(5, 2))
    course_description: Mapped[str | None] = mapped_column(Text)
    fall_offered: Mapped[bool] = mapped_column(default=False)
    spring_offered: Mapped[bool] = mapped_column(default=False)
    summer_offered: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    course_type: Mapped[str] = mapped_column(String(30), default="STANDARD")
