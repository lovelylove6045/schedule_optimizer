# Backend

FastAPI + SQLAlchemy + Alembic + OR-Tools backend for the Academic Degree Optimization Engine.

## Local development (without Docker)

```bash
uv sync
uv run uvicorn app.main:app --reload
```

## Local development (with Docker Compose, from repo root)

```bash
docker compose up -d db backend
```

See the repo root `README.md` and `docs/PHASES.md` for the full setup and phase checklist.
