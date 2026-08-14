# Detailed Phase Breakdown

This is the detailed, task-level companion to `docs/PROJECT_PLAN.md` (which has the high-level timeline/overview) and `docs/ARCHITECTURE.md` (tech stack rationale). Use this file as the working checklist — check items off as you go.

Stack assumed throughout: **local PostgreSQL running natively on the host** (Docker Compose kept available for on-demand container-parity checks, not day-to-day dev) + **Alembic migrations** + **FastAPI/SQLAlchemy/OR-Tools backend** + **React/Vite/TS frontend** + **future deploy to Azure via Docker containers** (see `docs/ARCHITECTURE.md` §7).

---

## Phase 0 — Project & Local Environment Setup ✅

**Goal**: Anyone on the team can clone the repo and be running in under 10 minutes.

- [x] Create top-level folders: `backend/`, `frontend/`, `db/` (Alembic lives inside `backend/`, but keep loader/seed scripts in `db/` for clarity).
- [x] `backend/`: scaffold FastAPI app (`app/main.py`), managed with **`uv`** (`uv init`, `uv add ...`) instead of `pip`/`requirements.txt` — deps: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `psycopg2-binary`, `pydantic`, `pydantic-settings`, `python-dotenv`, `ortools`. Config (`app/config.py`) reads Postgres settings from env vars via `pydantic-settings`.
- [x] `backend/Dockerfile`: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` base image, `uv sync --frozen`, run `uv run uvicorn app.main:app --host 0.0.0.0 --reload` for dev.
- [x] `frontend/`: scaffold Vite + React + TypeScript app; add Tailwind CSS v4 (`@tailwindcss/vite`); add shadcn/ui (`components.json`, `button`/`card` installed as a smoke test); add TanStack Query (`QueryClientProvider` in `main.tsx`).
- [x] `frontend/Dockerfile`: multi-stage build (`node:22-alpine` build → `nginx:1.27-alpine` static serve + `nginx.conf` SPA fallback), used later for Azure deploy — not required for local dev loop.
- [x] Root `docker-compose.yml`:
  - `db` service: `postgres:16-alpine`, named volume `pgdata`, env vars for user/password/db name, port `5432` exposed to host, with a `pg_isready` healthcheck.
  - `backend` service: builds `./backend`, depends on `db` (`condition: service_healthy`), bind-mounts source for hot reload (with an anonymous `/app/.venv` volume so the Linux container venv isn't clobbered by a host-mounted Windows `.venv`), `POSTGRES_HOST` overridden to `db` for in-network connectivity.
  - `frontend` service (under the `full` Compose profile, for Phase 6's full-container smoke test — day-to-day dev uses `npm run dev` instead).
- [x] `.env.example` (repo root) documenting `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `CORS_ALLOW_ORIGINS`, `VITE_API_BASE_URL`; local `.env` created with real dev credentials (`POSTGRES_DB=schedule_optimizer`), gitignored. `backend/app/config.py` reads `../.env` (repo root) as the single source of truth, falling back to `backend/.env` if present.
- [x] `GET /health` endpoint in FastAPI returning `{"status": "ok"}`.
- [x] Frontend placeholder page (shadcn `Card`/`Button` + TanStack Query) calls `/health` and displays the result, to prove the full loop works.
- [x] Update root `README.md` "Running locally" section: `docker compose up -d db backend` then `cd frontend && npm install && npm run dev`.

**Exit criteria**: ✅ Verified — `docker compose up -d db backend` builds and starts both containers (Postgres reports `healthy`, backend logs `Application startup complete`), `GET http://localhost:8000/health` returns `{"status": "ok"}` with correct CORS headers for `http://localhost:5173`, `psql` inside the `db` container confirms the `schedule_optimizer` database and `postgres` user are live, and `npm run dev` serves the frontend at `http://localhost:5173` successfully rendering the health-check card.

> **Note**: both a native host Postgres and the Docker `db` container are supported and kept working — use whichever you prefer, per teammate (see root `README.md`). They bind the same port, so only run one at a time. Day-to-day dev here runs natively (`uv run uvicorn app.main:app --reload` against the host Postgres).

---

## Phase 1 — Database Schema & Data Pipeline ✅

**Goal**: A locally running Postgres container with the full schema (via Alembic) and a narrow, real slice of catalog data.

### 1.1 Schema

- [x] Define SQLAlchemy models for all 28 tables described in `Stellic_Degree_Optimizer_Database_Design.pdf`, one table per file under `backend/app/models/`, grouped by domain to match the doc:
  - Catalog: `departments`, `subjects`, `courses`, `course_tags`, `course_tag_map`, `course_relations`, `terms`, `course_rule_nodes`, `colleges`.
  - Programs/requirements: `academic_programs`, `program_relationships`, `requirement_sets`, `program_requirement_sets`, `course_groups`, `course_group_members`, `requirement_nodes`, `overlap_policies`.
  - Students/scenarios: `students`, `student_credits`, `planning_scenarios`, `scenario_programs`, `scenario_terms`, `scenario_preferences`, `scenario_objectives`.
  - Generated plans: `degree_plans`, `plan_courses`, `requirement_allocations`, `optimization_messages`.
  - Verified with `configure_mappers()` — all cross-file foreign keys resolve, 28 tables registered on `Base.metadata`.
- [x] Reconcile column-level differences between `schedule_optimizer.sql` (the "context only" export) and the DB design doc's fuller table dictionary — table/column names match `schedule_optimizer.sql` where it overlaps; the design doc's additional tables/columns (tags, terms, colleges, students/scenarios/plans domains) were added on top, per the doc as source of truth.
- [x] Added DB-level enums for the values listed in Appendix A of the design doc that the optimizer actually needs, as native Postgres `CREATE TYPE ... AS ENUM` types (not constrained varchars) — defined once as reusable Python `(str, Enum)` classes in `backend/app/models/enums.py`, wired into the relevant `mapped_column`s: `program_type` (`academic_programs.program_type`), `requirement_node_type` (`requirement_nodes.node_type`), `rule_operator` (shared by `requirement_nodes.node_operator` and `course_rule_nodes.rule_operator`, exactly as Appendix A defines it once for both rule trees), `requisite_type` (`course_rule_nodes.requisite_type`), `course_relation_type` (`course_relations.relation_type`), `scenario_program_role` (replaces `scenario_programs.is_primary`, which couldn't express PRIMARY_MAJOR vs. SECOND_MAJOR/MINOR/EMPHASIS — safe change, table has no data yet), `scenario_preference_type` (`scenario_preferences.preference_type`), and the optimization objective codes (`scenario_objectives.objective_type`). One extra enum not in Appendix A, `course_rule_node_type`, was added for `course_rule_nodes.node_type` since the PDF only describes that column in prose and it's a different value space than `requirement_node_type` (documented in `enums.py`). Migration `1b0db359d548` hand-writes explicit `CREATE TYPE` + `ALTER COLUMN ... USING col::text::enum` (Alembic's autogenerate detects the type changes correctly but doesn't emit valid Postgres DDL for varchar→enum on populated tables) — applied cleanly against the live 1,012-course dataset with zero data loss, verified by re-diffing all row/value counts before and after, re-running `load_catalog.py` (idempotent, same counts), and confirming a bad enum value is now rejected by the database itself (`DataError`), not just app code. Appendix A's `degree_type` (BS/BA/NONE) was briefly added (`academic_programs.degree_type`) then deliberately dropped again in migration `564dcc9e0b41` — the optimizer only needs a program's requirement tree, not its BS/BA/none distinction, and `program_type` (MAJOR/MINOR/etc.) already tells it whether something is a degree at all; see `db/SUMMARY.md` §7.

### 1.2 Alembic

- [x] `alembic init alembic` inside `backend/`; `env.py` points at `app.models.Base.metadata`.
- [x] `sqlalchemy.url` set at runtime from `app.config.get_settings().database_url` (repo-root `.env`-driven), not hardcoded in `alembic.ini`.
- [x] Generated the first migration: `alembic revision --autogenerate -m "initial schema"` (`a1d053466018_initial_schema.py`); reviewed by hand — all 28 `create_table`s, FKs, and constraints match the models.
- [x] `alembic upgrade head` applied successfully; confirmed all 28 tables + `alembic_version` exist (verified via `information_schema.tables`, then `psql \dt` inside the target Postgres).
- [x] Documented the two commands every teammate needs in `backend/README.md` (`alembic revision --autogenerate -m "..."`, `alembic upgrade head`), for both the native-host and Docker workflows.

### 1.3 Data loading

- [x] Wrote `db/load_catalog.py`: reads `schedule_optimizer_db/*.json` (departments, subjects, courses, course_groups, course_group_courses, course_relations, requirement_sets, requirement_nodes, program_requirement_sets, academic_programs, colleges) and upserts into Postgres via the SQLAlchemy models (`session.merge()` on every table's real primary key — safe to re-run, verified idempotent by running twice and diffing the "Done. Loaded ..." summary counts).
- [x] Cross-referenced `catalog_scraper/output/*_courses.json`: `schedule_optimizer_db` has **no** prerequisite/corequisite data at all (`course_relations.json` is only `CROSS_LISTED`/`DUPLICATE_CREDIT`), so `course_rule_nodes` are derived entirely from free-text `Prerequisite:`/`Corequisite:` sentences in the scraper output via a new best-effort regex parser (`db/prereq_parser.py`) — see below.
- [x] **Scoped the first load narrowly** to Aerospace Engineering BS (`AERO_BS_2026`) + Aerospace Engineering Minor (`AERO_MINOR_2026`) — the only program pair with full requirement data in `schedule_optimizer_db` (confirmed with the user before building the loader). Loaded:
  - Both programs' 9 `requirement_sets` (8 for the major incl. the reusable `MST_GEN_ED_2026` set, 1 for the minor) + all 84 `requirement_nodes`.
  - All 956 directly-required courses (via `required_course_id` and the 10 referenced `course_groups`/`course_group_members` — the gen-ed pools are inherently broad, e.g. HASS/BSS/Natural Sciences).
  - The full prerequisite/corequisite closure via `course_rule_nodes`: 56 additional courses pulled in transitively (e.g. `AERO ENG 4780` → `AERO ENG 3251`/`3361`/`3171` → ... → `MATH 1103`), for **1,012 courses total**. `course_rule_nodes` is derived data with no natural key, so it's deleted and regenerated for the affected courses on every run.
  - Parser notes (best-effort, not a full grammar, as agreed with the user): 1,897 rule nodes parsed from 764 courses' descriptions (1,373 `COURSE`, 375 `GROUP`, 86 `STANDING`, 95 `TEXT` fallback for genuinely unparseable text like "Consent of instructor required"). Found and fixed two real data-quality traps along the way: (1) ~2.5% of descriptions have a trailing Missouri reverse-transfer ("MOTR") equivalency note restating the course's own code, which was being misread as a self-referential prerequisite — now stripped before parsing; (2) some catalog entries phrase a true corequisite as "Prerequisite: Accompanied by X", which — when mutual (e.g. `COMP SCI 1972`/`1982`, `COMP ENG 2210`/`2211`) — is an unsatisfiable cycle if left tagged `PREREQUISITE`; now detected and reclassified to `COREQUISITE`. Verified via a DFS cycle check that the `PREREQUISITE`-only graph is acyclic. A known remaining limitation: nested boolean prerequisite text (e.g. "C in Math 1214; or C in both Math 1210 and Math 1211") is flattened to one `ANY`/`ALL` group rather than fully nested — documented in `db/prereq_parser.py`.
- [x] Wrote 3 sanity-check SQL queries in `db/sanity_checks.sql` (runnable via `psql -f` or `python db/run_sanity_checks.py` if `psql` isn't on PATH) and hand-verified all three against the source JSON/catalog text:
  - Full requirement tree for the primary program (recursive CTE over `requirement_nodes`; 78 rows, matches `requirement_nodes.json` exactly).
  - Distinct prerequisite closure for `AERO ENG 4780` (Senior Design I) (recursive CTE over `course_rule_nodes`, deduplicated to shortest depth per course since the raw "all paths" version floods on shared Math/Physics prereqs; 23 courses, depths 1–4, matches the catalog by hand).
  - All courses satisfying the `AERO_MAE_TECH_2026` course_group (plain join, no recursion needed for a flat membership table; 87 rows).

**Exit criteria**: `alembic upgrade head` succeeds (native or Docker Postgres); `load_catalog.py` runs without errors and is idempotent; the three sanity-check queries return correct, human-verified results. All met for the Aerospace BS/Minor scope.

---

## Phase 2 — Backend Core & Domain Services

**Goal**: Backend can answer "what does this program require" and "what has this student already completed," with no optimizer involved yet.

- [ ] Pydantic schemas mirroring the models needed for API I/O (keep separate from SQLAlchemy models — don't leak ORM objects directly into responses).
- [ ] `catalog_service`:
  - [ ] `get_program(program_id)`, `list_programs()`.
  - [ ] `get_prerequisite_tree(course_id)` — recursively resolve `course_rule_nodes` into a nested dict/dataclass.
  - [ ] `get_course_group_members(course_group_id)`.
- [ ] `requirement_service`:
  - [ ] `resolve_requirement_sets(program_ids: list[int])` — union of `program_requirement_sets` across selected programs.
  - [ ] `flatten_requirement_tree(requirement_set_id)` — recursive walk of `requirement_nodes` into an evaluable structure (operator + children + leaf details).
- [ ] `credit_matching_service`:
  - [ ] `match_completed_courses(student_id, requirement_tree)` — mark which leaf nodes are satisfied by `student_credits`, respecting `minimum_grade` where present.
- [ ] Read-only endpoints:
  - [ ] `GET /programs`
  - [ ] `GET /programs/{id}/requirements` (flattened tree)
  - [ ] `GET /courses/{id}/prerequisites` (nested tree)
- [ ] Basic pytest coverage for `flatten_requirement_tree` and `match_completed_courses` against the narrow dataset loaded in Phase 1.

**Exit criteria**: Calling `GET /programs/{id}/requirements` for the chosen primary program returns the correct nested structure; feeding a hand-picked list of completed courses into `match_completed_courses` correctly flags the expected nodes as satisfied.

---

## Phase 3 — Optimization Engine (OR-Tools CP-SAT) — critical path

**Goal**: Given a scenario, produce one or more valid, ranked, semester-by-semester plans.

Protect this phase's time above all others — it's the project's core value proposition and the biggest technical risk.

### 3.1 Model construction

- [ ] Define the term horizon for a scenario (start term → some max lookahead, e.g. 12 terms) from `planning_scenarios` + `scenario_terms`.
- [ ] Build candidate course universe: courses reachable from the resolved requirement trees (via `requirement_nodes` course/course_group leaves), minus anything already satisfied by `student_credits`.
- [ ] CP-SAT variables: `assign[course_id, term_id] : BoolVar` for every (candidate course, eligible term) pair (eligible = course offered that term type per `courses.fall_offered/spring_offered/summer_offered`, and term is `is_available` per `scenario_terms`). **Known data gap, check before relying on this**: every one of the 2,120 courses in `schedule_optimizer_db/courses.json` currently has the identical placeholder `fall_offered=true, spring_offered=true, summer_offered=false` — there's no real per-course term-offering data anywhere in the repo yet (see `db/SUMMARY.md` §8). Decide here whether the uniform placeholder is acceptable for the demo or needs real data first, since it directly affects prerequisite-ordering feasibility and makes `MIN_SUMMER_ENROLLMENT` a no-op.
- [ ] Constraint: each course assigned to at most one term (or zero, if elective not needed).
- [ ] Constraint: prerequisite ordering — for each `course_rule_nodes` PREREQUISITE edge, the prerequisite's term index < the dependent course's term index (translate AND/OR/N_OF trees into CP-SAT `BoolAnd`/`BoolOr`/linear count constraints).
- [ ] Constraint: corequisite — same term index (or prerequisite's term ≤ dependent's, for PRE_OR_COREQUISITE).
- [ ] Constraint: per-term credit totals within `scenario_terms.minimum_credits/maximum_credits` (falling back to `planning_scenarios.default_minimum_credits/default_maximum_credits`).
- [ ] Constraint: requirement coverage — for each `requirement_nodes` leaf/group, enough assigned (or already-completed) courses/credits satisfy the operator (`ALL`/`ANY`/`N_OF`/`CREDITS_FROM`/`UNITS_FROM`), respecting `allow_shared_course` and any applicable `overlap_policies`.
- [ ] Constraint: hard `scenario_preferences` (`REQUIRE_COURSE`, `AVOID_COURSE`, `FIX_COURSE_TO_TERM` where `is_hard_constraint = true`).

### 3.2 Objectives & ranking

- [ ] Implement scoring terms for each `scenario_objectives` code: `EARLIEST_GRADUATION` (minimize max assigned term index), `MIN_ADDITIONAL_CREDITS` (minimize total credits beyond primary-degree baseline), `MAX_REQUIREMENT_OVERLAP` (maximize shared allocations), `BALANCED_WORKLOAD` (minimize variance across term credit totals), `MIN_SUMMER_ENROLLMENT` (penalize summer-term assignments).
- [ ] Combine objectives respecting priority order (`scenario_objectives.priority`/`weight`) — lexicographic or weighted-sum, whichever is simpler to implement correctly first.
- [ ] Solve once for the primary objective ordering → this becomes the "recommended" plan.

### 3.3 Multiple distinct plans

- [ ] After the first solution, add a diversity/no-good constraint (e.g., "at least K assignments must differ from the previous solution") and re-solve.
- [ ] Repeat until N distinct plans are found or a solve-attempt budget is hit; discard solutions that are trivial rearrangements with no material difference (per UC-44).
- [ ] Label each retained plan with a `strategy_code` (e.g., `EARLIEST_GRAD`, `MIN_CREDITS`, `MAX_OVERLAP`, `BALANCED`) based on which objective it best satisfies.

### 3.4 Persistence & explanations

- [ ] Persist each solution as `degree_plans` + `plan_courses` (+ link to `student_credits` for completed/in-progress rows) + `requirement_allocations` (one row per course/requirement-node pairing, `is_shared = true` when a course covers >1 node).
- [ ] Generate `optimization_messages`:
  - Infeasible scenario → identify and report the binding constraint(s) (per UC-56/UC-57).
  - Offering-risk warnings for infrequently-offered courses scheduled late.
  - Double-counting explanations where `is_shared = true`.

### 3.5 Testing

- [ ] Unit test scenario A: no constraints, primary program only → expect the shortest valid path.
- [ ] Unit test scenario B: tight per-term credit cap → expect an extra term appears, and the reason is captured in `optimization_messages`.
- [ ] Unit test scenario C: primary program + minor with known shared courses → expect `requirement_allocations` shows the expected shared courses with `is_shared = true`.

**Exit criteria**: All three unit-test scenarios pass with hand-verified expected output; the engine returns ≥2 meaningfully different plans for at least one non-trivial scenario; an intentionally-infeasible scenario returns a clear reason instead of an error.

---

## Phase 4 — API Integration Layer

**Goal**: A complete, documented HTTP surface for the frontend to build against.

- [ ] `POST /scenarios` — body: selected programs (with role), completed/in-progress courses, constraints (credit limits, term availability, summer preference), objectives (ordered). Returns `planning_scenario_id`.
- [ ] `POST /scenarios/{id}/generate` — runs Phase 3's optimizer synchronously (fine for a prototype-scale problem); returns the list of generated `degree_plans` with summary metrics.
- [ ] `GET /plans/{id}` — full semester-by-semester breakdown, requirement coverage summary, and related `optimization_messages`.
- [ ] `GET /plans/compare?ids=1,2,3` — side-by-side metrics (graduation term, total/remaining/additional credits, max/avg term credits, summer term count, overlap credits).
- [ ] `GET /programs`, `GET /programs/{id}/requirements` (reuse Phase 2 services).
- [ ] Structured error responses: infeasible generation returns `200` with a `status: "infeasible"` payload and messages, not a `500`.
- [ ] Confirm `/docs` (FastAPI's auto OpenAPI UI) is usable as a live contract for frontend development.

**Exit criteria**: A scripted end-to-end call sequence (`POST /scenarios` → `POST /scenarios/{id}/generate` → `GET /plans/{id}`) reproduces Phase 3's verified unit-test scenarios over HTTP.

---

## Phase 5 — Frontend

**Goal**: A judge can complete the full user journey (product spec §10) in the browser with no dead ends.

- [ ] API client layer (typed fetch wrapper) + TanStack Query hooks per endpoint.
- [ ] Screen 1 — Program selection: primary degree dropdown, starting term picker.
- [ ] Screen 2 — Academic progress: searchable multi-select of courses (hits `GET /programs/{id}/requirements` or a course-search endpoint) marked completed/in-progress, plus simple transfer-credit entry.
- [ ] Screen 3 — Academic goals: add second major/minor/emphasis (dropdown filtered by `program_relationships`), select interest tags.
- [ ] Screen 4 — Planning constraints: max credits/term slider, preferred range, summer on/off, per-term availability grid (for co-op/study-abroad terms).
- [ ] Screen 5 — Objective selection: ordered multi-select (drag-to-reorder if time allows, otherwise a simple ranked list) over the objective codes.
- [ ] Screen 6 — Recommended plan view: semester board/columns, each course as a card with credits, cumulative credit counter per column.
- [ ] Screen 7 — Alternative plans comparison: metrics table across generated plans + short natural-language "why this differs" pulled from `optimization_messages`.
- [ ] Screen 8 — Requirement coverage view: satisfied/remaining/shared requirement nodes, with shared ones visually flagged.
- [ ] Loading/empty/error states for every screen (no blank pages).
- [ ] Stretch (only if ahead of schedule): React Flow diagram of a program's requirement tree or a course's prerequisite chain.

**Exit criteria**: A cold run through Screens 1→8 with no console errors, no dead ends, and results that visibly match what Phase 3/4 produced.

---

## Phase 6 — Local Integration Pass

**Goal**: Backend + frontend + Postgres run together via `docker compose up` with zero manual steps, before touching Azure.

- [ ] Extend `docker-compose.yml` to optionally include the frontend service (production-style build) for a full "everything in containers" smoke test.
- [ ] Confirm `alembic upgrade head` + `load_catalog.py` can run as a one-time init step in the compose flow (e.g., a `db-init` one-shot service or a documented manual step).
- [ ] Run through all 12 "Core Demo Use Cases" (product spec §5.11) against the fully containerized local stack.
- [ ] Fix integration bugs found only when everything runs together (CORS, env var mismatches, timezone/date handling for terms, etc.).

**Exit criteria**: Fresh `git clone` → documented setup commands → full user journey works end to end, entirely inside Docker, with no cloud dependency required yet.

---

## Phase 7 — Azure Deployment

**Goal**: A live, public HTTPS URL backed by the same containers validated in Phase 6.

- [ ] Create Azure resources: **Azure Container Registry**, **Azure Database for PostgreSQL – Flexible Server**, two **Azure Container Apps** (backend, frontend) — or App Service for Containers if preferred.
- [ ] Build and push `backend` and `frontend` images to ACR (`az acr build` or a GitHub Actions workflow).
- [ ] Configure Container Apps with the ACR images, environment variables/secrets (`DATABASE_URL` pointing at the Flexible Server, CORS origin), and ingress (HTTPS, public).
- [ ] Run `alembic upgrade head` and `load_catalog.py` against the Azure Postgres instance (one-off Container Apps job, or run locally against the Azure connection string for the prototype).
- [ ] Point the frontend's `VITE_API_BASE_URL` at the deployed backend URL and rebuild/redeploy.
- [ ] Smoke-test the full user journey against the live URL from a fresh/incognito browser session.
- [ ] (Optional) GitHub Actions workflow: on push to `main`, build both images, push to ACR, update both Container Apps revisions automatically.

**Exit criteria**: The live Azure URL supports the full user journey end to end, matching local behavior.

---

## Phase 8 — Submission Prep

**Goal**: Everything the Competition Official Rules require is ready before the deadline, with buffer time to spare.

- [ ] Confirm category selection (likely **Degree Planning & Discovery**) and project title.
- [ ] Write the 500-word project overview (what was built, problem addressed, intended user).
- [ ] Record the ≤2-minute demo video (YouTube/Vimeo/Loom) showing the core demo use cases.
- [ ] Confirm the working prototype link (the Azure URL, or a GitHub repo link as fallback) is publicly reachable.
- [ ] Compile the **required tools/AI-disclosure list**: every framework, library, and AI coding assistant used (per §6 of `Competition Official Rules.pdf` — failure to disclose is grounds for disqualification).
- [ ] Names, institutions, programs of study, emails for every team member.
- [ ] Final read-through of the live URL from a clean browser profile.
- [ ] Submit with buffer time before **August 21, 2026, 11:59 PM ET**.

**Exit criteria**: Submission is complete on the Competition Site before the deadline, with every required field filled in.
