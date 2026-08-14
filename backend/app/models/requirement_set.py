from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RequirementSet(Base):
    """Reusable container for general education, program core, electives, minor, etc."""

    __tablename__ = "requirement_sets"

    requirement_set_id: Mapped[int] = mapped_column(primary_key=True)
    requirement_set_code: Mapped[str] = mapped_column(String(60), unique=True)
    requirement_set_name: Mapped[str] = mapped_column(String(250))
    requirement_set_type: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
