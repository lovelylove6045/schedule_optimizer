# Schedule-Optimizer
Stellic Pathfinder Challenge - Schedule Optimizer Project for Degree Audits

This is the platform used for the degree optimization for normal degree audits.

> **Prototype catalog scope:** Missouri S&T FA26 / 2026 only. Planning terms may
> extend into later calendar years, but every academic rule is interpreted from
> this single snapshot. This is a planning aid, not an official degree audit.

## Catalog data pipeline

```text
schedule_optimizer_db/*.json
        |
        v
db/load_catalog.py
        |
        v
PostgreSQL
        |
        v
FastAPI services / OR-Tools optimizer
        |
        v
React frontend
```

`schedule_optimizer_db/` is read-only source data. `catalog_scraper/` is a
historical/offline preparation utility and is not imported, executed, or queried
by the loader, API, optimizer, or frontend runtime.

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — tech stack and system design (local PostgreSQL in Docker + Alembic, FastAPI + OR-Tools backend, React frontend, future Azure container deployment).
- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) — phase overview and dependency graph against the competition submission deadline.
- [`docs/PHASES.md`](docs/PHASES.md) — detailed, checkbox-level task breakdown per phase (the day-to-day working checklist).
- [`db/SUMMARY.md`](db/SUMMARY.md) — what the data-loading pipeline does, in plain language, with examples.

## Setup, from a clean machine

Two supported ways to run this locally — pick whichever fits you (see [Option A](#option-a--natively-on-the-host) vs. [Option B](#option-b--docker-compose) below). Both hit the same code either way; each just reads its own `.env` file (see step 4).

This walkthrough is **Option A** (native), in the order you'd actually do it on a brand-new machine: Node.js → Python (via `uv`) → PostgreSQL → migrate → load data → run.

### 1. Install Node.js

Install **Node.js 20+** from [nodejs.org](https://nodejs.org/) (or a version manager like `nvm`/`fnm`). Verify:

```bash
node --version   # v20.x or newer
npm --version
```

### 2. Install Python (via uv)

The backend uses [**uv**](https://docs.astral.sh/uv/) to manage both the Python interpreter and dependencies — you don't need to separately install Python 3.12 first; `uv sync` (step 5) will download it automatically if it's missing.

- **Windows (PowerShell)**: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **macOS / Linux**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Already have Python + pip?** `pip install uv` (or `pipx install uv`) works too — the standalone installers above are only preferred because they don't require Python to already be installed.

Verify:

```bash
uv --version
```

### 3. Install PostgreSQL — natively, or via Docker

Pick **one** of these two; both end with a Postgres server reachable at `localhost:5432`.

**3a. Native install** (simplest, no other tooling required):

- **Windows**: [postgresql.org/download/windows](https://www.postgresql.org/download/windows/) (installer includes a service that starts automatically).
- **macOS**: `brew install postgresql@16 && brew services start postgresql@16`.
- **Linux**: `sudo apt install postgresql` (or your distro's equivalent), then `sudo systemctl enable --now postgresql`.

Create the database the app expects (matches `POSTGRES_DB` below):

```bash
psql -U postgres -c "CREATE DATABASE schedule_optimizer;"
```

**3b. Or install Docker instead** (no native Postgres install at all — a container serves the same role):

1. Install [**Docker Desktop**](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Compose plugin (Linux), and make sure it's running.
2. Verify: `docker --version` and `docker compose version`.
3. Start just the database container (do this instead of step 3a's `psql` command; the database itself — `schedule_optimizer` — is created automatically from `.env`'s `POSTGRES_DB`):

   ```bash
   docker compose up -d db
   ```

Either way, the rest of this walkthrough (steps 4-6) is identical — the backend and its loader scripts don't know or care whether Postgres is native or containerized, only that it's reachable at `localhost:5432`. See [Option B](#option-b--docker-compose) below if you'd rather run the backend itself in a container too, not just the database.

### 4. Configure environment variables

From the repo root:

```bash
cp .env.example .env                  # Windows: copy .env.example .env
cp .env.example backend/.env          # Windows: copy .env.example backend\.env
cp frontend/.env.example frontend/.env
```

Two separate `.env` files are needed even though their contents start out identical: the repo-root `.env` is what `docker-compose.yml` reads (for the containerized Postgres/backend), while `backend/app/config.py` only reads `backend/.env` (used whenever `uv run ...` is invoked from `backend/`, whether that's the app itself or a one-off script like `db/load_catalog.py`). Keep both in sync if you change a value. Open both and adjust `POSTGRES_USER`/`POSTGRES_PASSWORD` to match your local Postgres install if they differ from the defaults. Leave `frontend/.env` as-is unless the backend runs on a non-default port.

### 5. Backend: install deps, migrate, load the catalog, run

```bash
cd backend
uv venv                              # creates the .venv (uv sync below also does this automatically if skipped)
uv sync                              # installs Python 3.12 (if needed) + all dependencies
uv run alembic upgrade head          # creates all 28 tables + enum types
uv run python ../db/seed_terms.py    # generates 36 Fall/Spring/Summer terms through 2038
uv run python ../db/load_catalog.py  # loads the full real catalog: 2,120 courses, 147 programs, every requirement/prerequisite tree
uv run uvicorn app.main:app --reload
```

Both loader scripts are **idempotent** — safe to re-run any time (e.g. after pulling an updated `schedule_optimizer_db/*.json`). The API is now served at `http://localhost:8000` (interactive docs at `http://localhost:8000/docs`, health check at `http://localhost:8000/health`).

Run the backend test suite any time with `uv run pytest` (runs against the same local database, inside rolled-back transactions — see `backend/tests/conftest.py`).

### 6. Frontend: install deps, run

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:5173` and calls the backend via `VITE_API_BASE_URL` (see `frontend/.env`).

### 7. Verify

- `http://localhost:8000/health` → `{"status": "ok"}`
- `http://localhost:8000/docs` → full interactive API reference
- `http://localhost:5173` → the wizard; pick a college, a primary major (e.g. Aerospace Engineering BS), step through to a generated plan.

---

## Running locally — reference

### Option A — Natively on the host

Prerequisites: a local PostgreSQL server (any recent version) reachable on `localhost:5432`, [uv](https://docs.astral.sh/uv/), Node.js 20+. See the [step-by-step walkthrough above](#setup-from-a-clean-machine) the first time; day-to-day, it's just:

```bash
cd backend && uv run uvicorn app.main:app --reload
cd frontend && npm run dev
```

### Option B — Docker Compose

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/), plus `uv` on the host for the one-time migration/data-load step (the `db/` loader scripts aren't baked into the backend image, so they run from the host against the containerized Postgres, which is reachable at `localhost:5432` either way). Since these host-run commands execute from `backend/`, they still read `backend/.env` (see step 4) — `docker compose up -d db` itself reads the repo-root `.env`.

```bash
docker compose up -d db               # Postgres 16 in a container
cd backend
uv run alembic upgrade head           # against the containerized Postgres, via localhost:5432
uv run python ../db/seed_terms.py
uv run python ../db/load_catalog.py
cd ..
docker compose up -d backend          # backend API in a container, tables already migrated/loaded
docker compose --profile full up -d   # also builds/serves the frontend container
docker compose logs -f backend        # tail backend logs
docker compose down                   # stop containers (keeps the pgdata volume)
docker compose down -v                # stop containers and wipe the database volume
```

If you have a native Postgres service running too, stop one before starting the other — both bind to `localhost:5432` and only one can own the port at a time.

See [`docs/PHASES.md`](docs/PHASES.md) for the full build checklist (database schema/Alembic setup is Phase 1).

## Plan-board edit limits

The plan board supports four validated edits on an already-generated plan, none of which re-run the full optimizer:

- **Swap** — replace one term's assigned course with an alternative (`POST /plans/{id}/courses/{plan_course_id}/swap`).
- **Add** — place a brand-new course into a specific term as an extra elective, via the "Add course" search at the bottom of each term column (`POST /plans/{id}/courses`).
- **Remove** — delete a course from the plan entirely, via the trash icon on its tile (`DELETE /plans/{id}/courses/{plan_course_id}`).
- **Move** — place an existing course in another term (`POST /plans/{id}/courses/{plan_course_id}/move`).

Every edit triggers whole-plan revalidation and requirement-allocation rebuilding. The backend checks offerings, regular/summer caps, prerequisites and downstream dependents, requirement coverage, node-specific course levels, distinct-subject rules, duplicate credit, and the published degree-credit floor.

- **Prerequisites** — placing a course whose prerequisite hasn't been completed or already placed in an earlier term of *this same plan* is rejected (e.g. placing MATH 212 requires MATH 191 already sitting in an earlier semester, or on the student's completed-coursework list).
- **Term credit cap** — every semester has a maximum credit-hour load (a per-term `scenario_terms` override if the scenario set one, otherwise the scenario's own default maximum). An edit that would push that semester over its cap is rejected.
- **Term offering** — a course only offered in the fall can't be placed into a spring/summer slot.

These checks live in `backend/app/services/plan_swap_validation.py` and `plan_validation_service.py`. A mandatory course is locked in the UI and direct API attempts that would break validity return `422`.

## Optimization behavior

The recommended plan is solved first with ordered lexicographic stages. Each
achieved higher-priority value is locked before the next selected priority is
optimized; no weighted approximation is used. A minimum-coursework safeguard
prevents overlap or department preferences from padding a plan. The API then
generates semantically distinct alternatives separately.

The optimizer considers `STANDARD` and `SEMINAR` courses by default. Structurally
mandatory course leaves always enter the candidate set regardless of course type, so
catalog requirements cannot be blocked by the preference filter. Other Research,
Internship, Special Problems, Special Topics, and future non-standard alternatives
enter only when the student explicitly requires, prefers, or fixes one to a term.
Filtering happens before model construction to keep recommendations consent-safe and
reduce solve time.

The shared solver deadline is hard: no new stage or alternative solve starts after
the budget expires. `OPTIMAL` and `FEASIBLE` are preserved and shown differently.
Recorded real-catalog regression metrics are in
[`docs/GOLDEN_SCENARIOS.md`](docs/GOLDEN_SCENARIOS.md).

## Reaching your major's full credit total

A degree's requirement tree only lists *named* requirements (core courses, gen-ed groups, specific elective slots) — on their own, those can add up to a bit less than the program's officially published `total_credit_hours` (e.g. a real Aerospace BS catalog entry: 128 total, but its named requirements alone only guaranteed 126). Since Screen 6's credit-load step, every generated plan enforces a hard floor: total assigned credit hours (net of whatever the student already completed) must reach at least the highest published total among the scenario's major-level programs (`PRIMARY_MAJOR`/`SECOND_MAJOR` — a minor doesn't have its own separate graduation total). The solver satisfies this by picking a few extra electives from the same groups it was already choosing from, not by inventing new requirements.

This is on by default (`enforce_program_credit_minimum`) and is a per-scenario toggle right alongside the min/max credits and "allow summer" switches, in case a scenario's candidate pool genuinely has no slack to pad the gap with — turning it off is also the first thing an infeasible-plan message suggests trying. See `backend/app/services/optimizer_model.py::_add_program_credit_floor_constraint` and `backend/app/services/optimizer_candidates.py::_resolve_credit_floor_remaining`.

## Overlap suggestions after generating (and after swapping/adding/removing)

Once a scenario has a generated plan, the results page shows a "More overlap with your major?" panel (same idea as the wizard's Screen 4 suggestions) listing minors/second majors that reuse most of the primary major's own courses, ranked by `program_overlap_service`'s `overlap_ratio`. It stays visible across every plan-board edit and tab, so it's just as available right after generating as it is after a swap, add, or remove. Accepting a suggestion calls `POST /scenarios/{id}/programs` to add it to the scenario, then re-runs the optimizer so the new program's requirements are actually reflected in the plan.

Link for Claude AI Usage Check: https://platform.claude.com/dashboard
