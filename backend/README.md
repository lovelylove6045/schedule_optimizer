# Backend

FastAPI + SQLAlchemy + Alembic + OR-Tools backend for the Academic Degree Optimization Engine.

## Local development (directly on the host)

Requires a local PostgreSQL server reachable at the host/port in the repo-root `.env`.

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Database migrations (Alembic)

```bash
uv run alembic revision --autogenerate -m "describe the change"   # after editing app/models/*.py
uv run alembic upgrade head                                        # apply pending migrations
```

## Local development (with Docker Compose, from repo root)

```bash
docker compose up -d db backend
```

Either workflow is fine — use whichever you prefer. Note: the Docker `db` service also binds `localhost:5432`, so stop any native Postgres service first if you switch to this route (and vice versa).

See the repo root `README.md` and `docs/PHASES.md` for the full setup and phase checklist.
