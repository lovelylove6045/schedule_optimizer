from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all ORM models (populated starting in Phase 1)."""


def get_db():
    """FastAPI dependency that yields one request-scoped `Session` and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
