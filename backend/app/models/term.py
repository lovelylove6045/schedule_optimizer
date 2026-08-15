"""Ordered planning periods, e.g. Fall 2026. Has no source data anywhere in
this repo (unlike every other catalog table); populated by `db/seed_terms.py`."""

from datetime import date

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Term(Base):
    __tablename__ = "terms"

    term_id: Mapped[int] = mapped_column(primary_key=True)
    term_code: Mapped[str] = mapped_column(String(20), unique=True)
    academic_year: Mapped[int]
    term_type: Mapped[str] = mapped_column(String(10))
    sequence_index: Mapped[int] = mapped_column(unique=True)
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
