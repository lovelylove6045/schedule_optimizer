# Architecture & Tech Stack

Reference doc for how the Academic Degree Optimization Engine (Stellic Pathfinders Challenge submission) is built. Pairs with `docs/PROJECT_PLAN.md`, which breaks the work below into day-by-day phases.

## 1. System Overview

```
┌─────────────────────┐        ┌───────────────────────────┐        ┌────────────────────┐
│   Frontend (React)  │  HTTP  │   Backend (FastAPI)       │  SQL   │   PostgreSQL        │
│  Vite + TS + Tailwind│ <────> │  SQLAlchemy + Alembic     │ <────> │  Docker container   │
│  shadcn/ui, TanStack │        │  + OR-Tools CP-SAT        │        │  (local dev) ->     │
│  Query, React Flow   │        │  optimization engine      │        │  Azure DB for       │
└─────────────────────┘        └───────────────────────────┘        │  PostgreSQL (prod)  │
                                                                     └────────────────────┘
```

- **Database**: PostgreSQL. **Local development** runs Postgres in a Docker container (via `docker-compose`), so the exact same container image/config carries forward to production. Source of truth for catalog data, requirement trees, student scenarios, and generated plans.
- **Migrations**: Alembic manages all schema changes (see §3.1). No hand-run `.sql` files once Alembic is set up — every schema change is a versioned, reversible migration.
- **Backend**: FastAPI (Python). Owns all business logic: loading the academic graph, evaluating requirement trees, running the optimizer, and persisting/returning generated plans.
- **Optimization engine**: Google OR-Tools CP-SAT, embedded in the backend. This is the core differentiator of the project and the highest-risk component, so it gets the most dedicated build time (see `docs/PHASES.md`, Phase 3).
- **Frontend**: React + Vite + TypeScript SPA. Talks to the backend only via REST JSON.
- **Containerization**: Both backend and frontend get their own `Dockerfile` from day one, and a root `docker-compose.yml` orchestrates db + backend (+ optionally frontend) for local dev. This means "deploy to Azure via containers" later is a matter of building/pushing the same images, not a rewrite (see §7).

## 2. Why this stack

- The existing `schedule_optimizer.sql` and `Stellic_Degree_Optimizer_Database_Design.pdf` already assume PostgreSQL with identity columns and enums — using Postgres directly avoids translating the schema.
- The core problem (assign courses to terms subject to prerequisites, credit limits, requirement coverage, then rank/generate multiple valid alternatives) is a textbook constraint-satisfaction problem. OR-Tools CP-SAT provides prerequisite-respecting scheduling, multi-objective optimization, and solution pooling (for "generate multiple distinct plans," UC-44) out of the box, which would otherwise take days to hand-roll correctly.
- FastAPI + Pydantic give fast, typed API development and auto-generated OpenAPI docs, useful when the frontend and backend are built somewhat in parallel.
- React + Tailwind + shadcn/ui is the fastest path to a clean, judge-ready UI without custom design work.
- Everything here has a free hosting tier and deploys in minutes (Vercel for frontend, Render/Railway for backend, Supabase/Neon for DB) — important given the Aug 21, 2026 submission deadline requires a live URL.

## 3. Database Layer

Base schema comes from `schedule_optimizer.sql`, extended per the recommendations in `Stellic_Degree_Optimizer_Database_Design.pdf` (27-table design across 4 domains). Domains:

1. **Course catalog & rules** — `departments`, `subjects`, `courses`, `course_tags`, `course_tag_map`, `course_relations`, `terms`, `course_rule_nodes` (prerequisite/corequisite tree).
2. **Programs & requirements** — `academic_programs`, `program_relationships`, `requirement_sets`, `program_requirement_sets`, `course_groups`, `course_group_members`, `requirement_nodes` (nested requirement tree), `overlap_policies` (double-counting rules).
3. **Students & scenarios** — `students`, `student_credits`, `planning_scenarios`, `scenario_programs`, `scenario_terms`, `scenario_preferences`, `scenario_objectives`.
4. **Generated plans** — `degree_plans`, `plan_courses`, `requirement_allocations`, `optimization_messages`.

Data sources to load in:
- `schedule_optimizer_db/*.json` — pre-extracted departments/subjects/courses/requirement data.
- `catalog_scraper/output/*_courses.json` — raw scraped Missouri S&T course catalog, subject-by-subject.

Per the DB design doc's guidance, **narrow the first data load** to one primary program + one related minor/emphasis + the shared general-education requirement set, plus only the courses reachable through those requirements and their prerequisites. Expand once the end-to-end pipeline works.

### 3.1 Migrations with Alembic

- `alembic init` inside `backend/`, configured to read the SQLAlchemy model metadata so `alembic revision --autogenerate` produces real migrations instead of hand-written SQL.
- One migration per logical schema change (e.g., `0001_initial_schema`, `0002_add_overlap_policies`, ...), committed to the repo so the schema history is reproducible on any machine and in any environment (local Docker, CI, Azure).
- Local workflow: `alembic upgrade head` runs against the local Postgres container on startup (can be automated in `docker-compose` via an init step or a `Makefile`/`justfile` target).
- Same command (`alembic upgrade head`) runs against the production DB during deploy — no separate "prod schema" process to maintain.
- Seed/loader scripts (for `schedule_optimizer_db/*.json` and `catalog_scraper/output/*.json`) are kept separate from Alembic migrations — migrations define structure, a Python loader script populates data.

## 4. Backend Layer

- **ORM**: SQLAlchemy (or SQLModel) models mirroring the schema above.
- **API schemas**: Pydantic models for request/response validation.
- **Core services** (plain Python, independent of the web framework so they're testable):
  - `catalog_service` — load courses, subjects, prerequisite/corequisite trees.
  - `requirement_service` — resolve which requirement sets apply to a scenario's selected programs; flatten nested `requirement_nodes` trees.
  - `credit_matching_service` — match `student_credits` against requirement nodes and course equivalents to mark what's already satisfied.
  - `optimizer_service` — build and solve the CP-SAT model; returns one or more candidate plans with scores.
  - `explanation_service` — generate `optimization_messages` (why a course was recommended, warnings, infeasibility reasons).
- **API endpoints** (grouped):
  - Catalog browsing: programs, courses, requirement sets (for building selection UI).
  - Scenario management: create/update a planning scenario (completed courses, goals, constraints, objectives).
  - Plan generation: trigger the optimizer for a scenario, return ranked plans.
  - Plan detail & comparison: fetch a specific plan's semester breakdown, requirement coverage, and messages; compare N plans side by side.

## 5. Optimization Engine (OR-Tools CP-SAT)

Model sketch:
- **Decision variables**: for each (candidate course, eligible term) pair, a boolean "course is scheduled in this term."
- **Hard constraints**:
  - Prerequisite/corequisite trees from `course_rule_nodes` (a course's term must be after/with its prerequisites' terms).
  - Per-term credit limits (`scenario_terms`, `planning_scenarios.default_maximum_credits`).
  - Term availability (`scenario_terms.is_available`, summer opt-in/out).
  - Requirement coverage — every `requirement_node` must be satisfied by at least the required count/credits of allocated courses, respecting `allow_shared_course` and `overlap_policies`.
  - Locked/preferred courses (`scenario_preferences` hard constraints).
- **Objective(s)**: weighted combination driven by `scenario_objectives` (earliest graduation, min additional credits, max overlap, balanced workload, min summer enrollment), following the rule hierarchy in the product spec (Section 7.10 / 8.4): academic validity → mandatory constraints → overlap maximization → objective optimization → ranking.
- **Multiple plans**: re-solve with diversity constraints (e.g., forbid reusing the exact same course-set) or use OR-Tools' solution pool to collect several distinct feasible solutions, then keep the top N meaningfully-different ones per UC-44.
- **Output**: for each solution, persist `degree_plans` + `plan_courses` + `requirement_allocations`, and derive `optimization_messages` for warnings/explanations.v

Keep the CP-SAT model isolated behind `optimizer_service` so it can be unit-tested against small, hand-verified scenarios independent of the API/DB.

## 6. Frontend Layer

- **Stack**: Vite + React + TypeScript, Tailwind CSS, shadcn/ui components, TanStack Query for data fetching/caching.
- **Screens** (mapped to the product spec's user journey, Section 10):
  1. Program selection (primary degree, catalog year, starting semester).
  2. Academic progress input (completed courses, transfer/AP credits).
  3. Academic goals (second major/minor/emphasis, interests).
  4. Planning constraints (credit limits, semester availability, graduation target).
  5. Optimization objectives selection.
  6. Recommended plan view — semester-by-semester board with credit totals.
  7. Alternative plans comparison view (side-by-side metrics table + explanations).
  8. Requirement coverage view (what's satisfied, what's remaining, shared/double-counted courses).
- **Optional visual differentiator**: React Flow view of the prerequisite chain / requirement tree for a program, to make the "why this course, why this order" logic tangible to judges.

## 7. Deployment

**Local development**: `docker-compose.yml` at the repo root runs a `postgres` service (named volume for data persistence) plus the `backend` service (FastAPI, hot-reload via a bind mount). The frontend is typically run with `npm run dev` directly on the host for the fastest hot-reload loop, but also has its own `Dockerfile` so it can be built/run identically to production.

**Production (Azure, containerized)**:

- **Container images**: `backend/Dockerfile` and `frontend/Dockerfile` (multi-stage build → static assets served by nginx, or served via a small Node server) are pushed to **Azure Container Registry (ACR)**.
- **Compute**: **Azure Container Apps** (recommended) runs the backend and frontend images. Container Apps is the fastest way to go from "Docker image" to "public HTTPS URL" on Azure, with autoscaling and no cluster to manage — a good fit for a hackathon timeline. Azure App Service for Containers is an equally valid, slightly simpler alternative if preferred.
- **Database**: **Azure Database for PostgreSQL – Flexible Server** is recommended for the production database rather than self-hosting Postgres in a container — it's managed (backups, patching, persistence) so the team isn't responsible for data durability during judging. If full containerization of the DB itself is a hard requirement, Postgres can instead run as a Container Apps job/service backed by an Azure Files-mounted volume, but this needs care around backups and restarts.
- **CI/CD**: a GitHub Actions workflow builds both images on push to `main`, pushes to ACR, then triggers a revision update on the two Container Apps. Same `docker-compose.yml` structure used locally maps directly onto these two container definitions, so there's no separate "production-only" config to invent late.
- **Config**: DB connection string, CORS-allowed origin, and any other secrets are injected as environment variables / Container Apps secrets — never committed to the repo. `alembic upgrade head` runs as a release step (e.g., a one-off Container Apps job) before traffic shifts to a new revision.

## 8. Out of scope for the prototype

Per the product spec (Section 11.3) and DB design doc (Section 9.3): no multi-institution/multi-catalog support, no live registration/seats/sections, no GPA/financial-aid logic, no authentication, no admin/curriculum-authoring UI, no predictive analytics, no LLM-based planning decisions (the optimizer itself must stay transparent and rule-based).
