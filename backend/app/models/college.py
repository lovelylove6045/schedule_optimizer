from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class College(Base):
    __tablename__ = "colleges"

    college_id: Mapped[int] = mapped_column(primary_key=True)
    college_code: Mapped[str] = mapped_column(String(30), unique=True)
    college_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=True)
