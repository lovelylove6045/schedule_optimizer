"""Shared pytest fixtures.

Tests run against the real local Postgres database (the one `db/load_catalog.py`
populates) rather than a mock or a separate test database -- there's no
lighter-weight way to get 2,120 real courses' worth of catalog data to test
against. To keep that safe, every test runs inside one outer transaction that
is always rolled back at the end (`db_session` below), so nothing a test
creates (e.g. a scratch `Student`/`StudentCredit` for credit-matching tests)
is ever actually committed to the database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
