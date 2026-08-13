# Schedule-Optimizer
Stellic Pathfinder Challenge - Schedule Optimizer Project for Degree Audits

This is the platform used for the degree optimization for normal degree audits.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — tech stack and system design (local PostgreSQL in Docker + Alembic, FastAPI + OR-Tools backend, React frontend, future Azure container deployment).
- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — phase overview and dependency graph against the competition submission deadline.
- [`docs/PHASES.md`](docs/PHASES.md) — detailed, checkbox-level task breakdown per phase (the day-to-day working checklist).

## Running locally

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/), [uv](https://docs.astral.sh/uv/), Node.js 20+.

1. Copy `.env.example` to `.env` at the repo root and adjust values if needed (Postgres credentials, CORS origin).
2. Start Postgres + the backend API in Docker:

   ```bash
   docker compose up -d db backend
   ```

   This builds the backend image (FastAPI + SQLAlchemy + Alembic + OR-Tools, managed with `uv`), starts Postgres 16 with a persistent volume, and exposes the API at `http://localhost:8000` (docs at `http://localhost:8000/docs`, health check at `http://localhost:8000/health`).

3. Start the frontend dev server (outside Docker, for fast hot-reload):

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   The app runs at `http://localhost:5173` and calls the backend via `VITE_API_BASE_URL` (see `frontend/.env`).

4. To run the backend without Docker instead (e.g. for debugging):

   ```bash
   cd backend
   uv sync
   uv run uvicorn app.main:app --reload
   ```

   This reads Postgres connection settings from the repo-root `.env` (`POSTGRES_HOST=localhost` works here since Docker Compose publishes Postgres's port to the host).

Useful commands:

```bash
docker compose logs -f backend   # tail backend logs
docker compose down              # stop containers (keeps the pgdata volume)
docker compose down -v           # stop containers and wipe the database volume
```

See [`docs/PHASES.md`](docs/PHASES.md) for the full build checklist (database schema/Alembic setup is Phase 1).

Link for Claude AI Usage Check: https://platform.claude.com/dashboard
