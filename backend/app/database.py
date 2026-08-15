from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all ORM models (populated starting in Phase 1)."""


def get_db():
    """FastAPI dependency that yields one request-scoped `Session`, committing on
    success and rolling back on any exception, so nothing partially applies.
    Services below this layer only `flush()`; the request itself owns the
    transaction boundary. Tests override this dependency with a plain
    `yield db_session` (no commit), so their rollback-based isolation is unaffected."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
