from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    department_id: Mapped[int] = mapped_column(primary_key=True)
    department_code: Mapped[str] = mapped_column(String(30), unique=True)
    department_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=True)
    college_id: Mapped[int | None] = mapped_column(ForeignKey("colleges.college_id"))
    source_url: Mapped[str | None] = mapped_column(Text)
