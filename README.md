# Schedule Optimizer

Schedule Optimizer is a degree-planning prototype that builds prerequisite-aware,
multi-term course schedules from a student's selected major, additional programs,
completed coursework, credit limits, and planning priorities.

> **Catalog scope:** The included data is the Missouri S&T FA26 / 2026 catalog
> snapshot. Plans can extend into later calendar years, but their requirements and
> course rules still come from that snapshot. This is a planning aid, not an official
> degree audit; students should confirm substitutions, approvals, placement results,
> and graduation requirements with an academic advisor.

## What the application supports

- One primary major plus optional second majors, minors, and emphases.
- Completed/in-progress coursework, term exclusions, summer planning, and per-term
  credit limits.
- Prerequisite, co-requisite, term-offering, duplicate-credit, and degree-credit
  validation.
- A recommended plan generated first, without waiting for optional alternatives.
- On-demand alternative plans for selected goals such as earliest graduation,
  balanced workload, fewer extra credits, program overlap, or avoiding summer.
- Simple and detailed schedule views grouped by Fall-start academic year.
- Requirement coverage, plan comparison, course swapping/moving/adding/removing,
  and a searchable Courses view for inspecting recognized prerequisites.
- Direct PDF download of the current schedule view. The exported PDF retains the
  summary, colors, icons, course cards, and academic-year layout while omitting edit
  controls.

## Architecture and catalog flow

```text
schedule_optimizer_db/*.json (canonical catalog source)
        |
        v
db/load_catalog.py
        |
        v
PostgreSQL 16
        |
        v
FastAPI + SQLAlchemy + OR-Tools CP-SAT
        |
        v
React + TypeScript + Vite
```

`catalog_scraper/` is a historical/offline preparation utility. The running loader,
API, optimizer, and frontend do not import or query it.

## Recommended local setup

This option runs PostgreSQL in Docker and runs the backend/frontend directly on the
host for fast reloads. It is the simplest development setup.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine
  with the Compose plugin.
- [Node.js 20+](https://nodejs.org/).
- [uv](https://docs.astral.sh/uv/) for Python 3.12 and backend dependencies.

Install `uv` if needed:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify the tools:

```bash
docker --version
docker compose version
node --version
npm --version
uv --version
```

### 1. Configure local environment files

From the repository root:

```bash
cp .env.example .env
cp .env.example backend/.env
cp frontend/.env.example frontend/.env
```

Windows Command Prompt equivalents:

```bat
copy .env.example .env
copy .env.example backend\.env
copy frontend\.env.example frontend\.env
```

The root `.env` is used by Docker Compose. `backend/.env` is used by backend commands
run from `backend/`. Keep the PostgreSQL database, username, password, host, and port
consistent between them. The defaults expect:

```dotenv
POSTGRES_DB=schedule_optimizer
POSTGRES_USER=postgres
POSTGRES_PASSWORD=changeme
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

`frontend/.env` normally remains:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Do not commit real database credentials. The local `.env` files are intentionally
separate from the checked-in examples.

### 2. Start PostgreSQL

```bash
docker compose up -d db
docker compose ps
```

Wait until the `db` service reports healthy before running migrations.

### 3. Install and initialize the backend

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python ../db/seed_terms.py
uv run python ../db/load_catalog.py
uv run uvicorn app.main:app --reload
```

The migration, term seed, and catalog loader must run before the first plan is
generated. Both data loaders are idempotent and safe to run again after catalog
updates.

The backend is available at:

- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Interactive API documentation: `http://localhost:8000/docs`

### 4. Install and run the frontend

Open a second terminal from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### 5. Verify the installation

1. Confirm `http://localhost:8000/health` returns `{"status":"ok"}`.
2. Open `http://localhost:5173` and select a college and primary major.
3. Complete the wizard and generate the recommended plan.
4. Open **Courses** to inspect a catalog course's recognized prerequisites.
5. On the results page, use **Generate alternatives** only if comparison plans are
   wanted, or use **Download PDF** from the Schedule key toolbar.

## Day-to-day startup

After the first-time initialization, start these in separate terminals:

```bash
# Terminal 1, from the repository root
docker compose up -d db
cd backend
uv run uvicorn app.main:app --reload
```

```bash
# Terminal 2, from the repository root
cd frontend
npm run dev
```

Stop the database without deleting its data:

```bash
docker compose down
```

`docker compose down -v` also deletes the PostgreSQL volume and all locally loaded
data; use it only when a clean database rebuild is intended.

## Alternative ways to run

### Native PostgreSQL

Install a recent PostgreSQL release, create a `schedule_optimizer` database, and put
the matching credentials in both `.env` and `backend/.env`. The database must be
reachable at the configured `POSTGRES_HOST` and `POSTGRES_PORT`.

For example, when the local `postgres` role is already configured:

```bash
psql -U postgres -c "CREATE DATABASE schedule_optimizer;"
```

Then follow the backend and frontend steps above without running
`docker compose up -d db`.

### Full Docker Compose stack

The optional frontend container is served at `http://localhost:4173`. Before starting
the full stack, add that origin to the root `.env` so the containerized backend accepts
browser requests from it:

```dotenv
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:4173
```

The catalog loader scripts are not baked into the backend image, so initialize the
database once from the host:

```bash
docker compose up -d db
cd backend
uv sync
uv run alembic upgrade head
uv run python ../db/seed_terms.py
uv run python ../db/load_catalog.py
cd ..
docker compose --profile full up -d --build
```

Useful Docker commands:

```bash
docker compose ps
docker compose logs -f backend
docker compose --profile full logs -f frontend
docker compose down
```

## Using generated plans

### Recommended and alternative plans

The initial run generates only the recommended plan. This keeps the usable result
available as soon as its ordered optimization stages finish. Alternatives are never
started automatically.

Use **Generate alternatives** in the results header or Compare tab, select only the
strategies you want, and start the additional solve. Course-prerequisite links are
temporarily disabled while alternatives are using the optimizer; the recommended
schedule remains visible. The Compare tab displays its empty-state action until at
least one alternative exists.

### Schedule views and PDF export

The Schedule tab groups Fall, Spring, and optional Summer terms by Fall-start academic
year. Use **Simple** for compact cards or **Details** for selection explanations.

**Download PDF** exports whichever view is currently selected. PDF generation happens
in the browser and may take a few seconds for long schedules. Interactive actions are
removed from the file, and page breaks prefer academic-year boundaries.

### Validated plan edits

The generated plan supports these edits without re-running the full optimizer:

- **Swap:** replace a course with a valid option for the same requirement.
- **Move:** move a course to another eligible term.
- **Add:** add an extra course to a term.
- **Remove:** remove an unlocked course when the plan remains valid.

Each edit revalidates term offerings, prerequisites and downstream dependents,
co-requisites, credit limits, requirement coverage, duplicate credit, and the degree
credit floor. The API returns `422` when an edit would invalidate the plan.

## Optimization behavior summary

- `STANDARD` and `SEMINAR` courses are available by default.
- A structurally required course remains eligible regardless of course type.
- Research, Internship, Special Problems, Special Topics, and other non-standard
  courses enter optimization only when explicitly required or selected.
- Required introductory seminars are placed in their earliest available planning
  term; later seminars follow normal prerequisite sequencing.
- Explicit catalog choices prefer their listed order. For example, when a requirement
  lists MATH 1214 before MATH 1211, the first branch is preferred when feasible.
- Open degree credits prefer eligible higher-level courses from the selected major's
  department before unrelated courses; course count breaks the remaining tie.
- Multiple selected programs are solved together in one shared model so common
  courses can satisfy compatible requirements across programs.
- Primary objectives are solved and locked lexicographically. The optimizer preserves
  whether each stage was proven `OPTIMAL` or only found `FEASIBLE` within the shared
  time limit.

The program's published `total_credit_hours` is enforced by default. Named requirement
nodes do not always add up to that published total, so the optimizer may add courses
classified as **Open degree credits**. Disable `enforce_program_credit_minimum` in the
scenario only when intentionally testing a plan without that floor.

## Catalog updates and database migrations

Make reviewed catalog corrections in `schedule_optimizer_db/*.json`, which is the
canonical source for clean installations. Then reload the catalog:

```bash
cd backend
uv run python ../db/load_catalog.py
```

If an existing database also needs a data correction, include an Alembic data
migration and run:

```bash
cd backend
uv run alembic upgrade head
```

For example, the included FR ENG 1100 correction is stored in `courses.json` and an
Alembic migration so both clean databases and previously loaded databases classify it
as `SEMINAR`. Avoid relying on manual PostgreSQL `UPDATE` statements because other
clones will not receive them and a later catalog reload can overwrite them.

After pulling repository changes, the safe refresh sequence is:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python ../db/seed_terms.py
uv run python ../db/load_catalog.py
cd ../frontend
npm install
```

## Tests and production checks

The backend tests use the configured local PostgreSQL database and roll test changes
back after each test:

```bash
cd backend
uv run pytest
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
npm audit --omit=dev
```

## Troubleshooting

### The frontend cannot reach the backend or reports CORS

- Confirm `http://localhost:8000/health` works first.
- Confirm `frontend/.env` points to the backend with
  `VITE_API_BASE_URL=http://localhost:8000`.
- Restart `npm run dev` after changing `frontend/.env`.
- Add the exact frontend origin to `CORS_ALLOW_ORIGINS` in `backend/.env` for native
  backend runs, or root `.env` for Docker backend runs.
- Private-LAN addresses on port `5173` are accepted by the default regex. For access
  from another device, run Uvicorn with `--host 0.0.0.0` and set
  `VITE_API_BASE_URL` to the host computer's LAN address, not `localhost`.

### PostgreSQL connection fails

- Run `docker compose ps` and confirm the database is healthy.
- Check that only one service owns port `5432`; native PostgreSQL and Docker cannot
  both bind the same host port.
- Confirm the credentials and port in `.env` and `backend/.env` match the database.

### Colleges/programs/courses are empty

Run the migration, term seed, and catalog loader again from `backend/`:

```bash
uv run alembic upgrade head
uv run python ../db/seed_terms.py
uv run python ../db/load_catalog.py
```

### Optimization takes longer for multiple programs

Multiple majors/minors increase the shared candidate and constraint set. Leave the
optimization dialog open; its stage indicator continues updating. Generate alternative
strategies only when needed, and select only the strategies you intend to compare.

### PDF generation appears paused

Long detailed schedules require a larger browser capture. Keep the results tab open
until **Preparing PDF...** finishes. If the browser blocks downloads, allow downloads
for the local site and try again.

## Additional documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - system design and deployment direction.
- [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) - project phases and dependencies.
- [`docs/PHASES.md`](docs/PHASES.md) - detailed implementation checklist.
- [`docs/GOLDEN_SCENARIOS.md`](docs/GOLDEN_SCENARIOS.md) - recorded optimizer regression scenarios.
- [`db/SUMMARY.md`](db/SUMMARY.md) - catalog-loading behavior and examples.
