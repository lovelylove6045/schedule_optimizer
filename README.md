# Schedule-Optimizer
Stellic Pathfinder Challenge - Schedule Optimizer Project for Degree Audits

This is the platform used for the degree optimization for normal degree audits.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — tech stack and system design (local PostgreSQL in Docker + Alembic, FastAPI + OR-Tools backend, React frontend, future Azure container deployment).
- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — phase overview and dependency graph against the competition submission deadline.
- [`docs/PHASES.md`](docs/PHASES.md) — detailed, checkbox-level task breakdown per phase (the day-to-day working checklist).

## Running locally

Two supported ways to run this locally — pick whichever fits you. Both read the same `.env` and hit the same code, so they're interchangeable.

### Option A — Natively on the host

Prerequisites: a local PostgreSQL server (any recent version) reachable on `localhost:5432`, [uv](https://docs.astral.sh/uv/), Node.js 20+.

1. Copy `.env.example` to `.env` at the repo root and adjust values if needed (Postgres credentials, CORS origin). Make sure a database matching `POSTGRES_DB` exists on your local Postgres server.
2. Run database migrations and start the backend API:

   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload
   ```

   The API is served at `http://localhost:8000` (docs at `http://localhost:8000/docs`, health check at `http://localhost:8000/health`).

3. Start the frontend dev server:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   The app runs at `http://localhost:5173` and calls the backend via `VITE_API_BASE_URL` (see `frontend/.env`).

### Option B — Docker Compose

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up -d db backend       # Postgres 16 + backend API in containers
docker compose --profile full up -d   # also builds/serves the frontend container
docker compose logs -f backend        # tail backend logs
docker compose down                   # stop containers (keeps the pgdata volume)
docker compose down -v                # stop containers and wipe the database volume
```

If you have a native Postgres service running too, stop one before starting the other — both bind to `localhost:5432` and only one can own the port at a time.

See [`docs/PHASES.md`](docs/PHASES.md) for the full build checklist (database schema/Alembic setup is Phase 1).

Link for Claude AI Usage Check: https://platform.claude.com/dashboard
