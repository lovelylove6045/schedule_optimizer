# Backend

FastAPI + SQLAlchemy + Alembic + OR-Tools backend for the Academic Degree Optimization Engine.

The backend models the Missouri S&T FA26 / 2026 catalog snapshot only. Runtime
catalog data flows from `schedule_optimizer_db/*.json` through
`db/load_catalog.py` into PostgreSQL. The historical `catalog_scraper/` directory
is not a runtime dependency.

Recommended plans use true ordered lexicographic optimization through
`POST /scenarios/{id}/generate/recommended`; alternatives are generated separately
through `POST /scenarios/{id}/generate/alternatives`. Manual edits revalidate the
complete schedule and rebuild requirement allocations.

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
