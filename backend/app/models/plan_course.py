"""Course placements (one row per course-per-term) that make up a degree plan."""

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanCourse(Base):
    __tablename__ = "plan_courses"

    plan_course_id: Mapped[int] = mapped_column(primary_key=True)
    degree_plan_id: Mapped[int] = mapped_column(ForeignKey("degree_plans.degree_plan_id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id"))
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.term_id"))
    credit_hours: Mapped[float] = mapped_column(Numeric(5, 2))
    placement_source: Mapped[str] = mapped_column(String(20), default="SOLVER")
