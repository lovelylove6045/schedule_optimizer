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

**Goal**: A locally running Postgres container with the full schema (via Alembic) and the full real catalog loaded.

### 1.1 Schema

- [x] Define SQLAlchemy models for all 28 tables described in `Stellic_Degree_Optimizer_Database_Design.pdf`, one table per file under `backend/app/models/`, grouped by domain to match the doc:
  - Catalog: `departments`, `subjects`, `courses`, `course_tags`, `course_tag_map`, `course_relations`, `terms`, `course_rule_nodes`, `colleges`.
  - Programs/requirements: `academic_programs`, `program_relationships`, `requirement_sets`, `program_requirement_sets`, `course_groups`, `course_group_members`, `requirement_nodes`, `overlap_policies`.
  - Students/scenarios: `students`, `student_credits`, `planning_scenarios`, `scenario_programs`, `scenario_terms`, `scenario_preferences`, `scenario_objectives`.
  - Generated plans: `degree_plans`, `plan_courses`, `requirement_allocations`, `optimization_messages`.
  - Verified with `configure_mappers()` — all cross-file foreign keys resolve, 28 tables registered on `Base.metadata`.
- [x] Reconcile column-level differences between `schedule_optimizer.sql` (the "context only" export) and the DB design doc's fuller table dictionary — table/column names match `schedule_optimizer.sql` where it overlaps; the design doc's additional tables/columns (tags, terms, colleges, students/scenarios/plans domains) were added on top, per the doc as source of truth.
- [x] Added DB-level enums for the values listed in Appendix A of the design doc that the optimizer actually needs, as native Postgres `CREATE TYPE ... AS ENUM` types (not constrained varchars) — defined once as reusable Python `(str, Enum)` classes in `backend/app/models/enums.py`, wired into the relevant `mapped_column`s: `program_type` (`academic_programs.program_type`), `requirement_node_type` (`requirement_nodes.node_type`), `rule_operator` (shared by `requirement_nodes.node_operator` and `course_rule_nodes.rule_operator`, exactly as Appendix A defines it once for both rule trees), `requisite_type` (`course_rule_nodes.requisite_type`), `course_relation_type` (`course_relations.relation_type`), `scenario_program_role` (replaces `scenario_programs.is_primary`, which couldn't express PRIMARY_MAJOR vs. SECOND_MAJOR/MINOR/EMPHASIS — safe change, table has no data yet), `scenario_preference_type` (`scenario_preferences.preference_type`), and the optimization objective codes (`scenario_objectives.objective_type`). One extra enum not in Appendix A, `course_rule_node_type`, was added for `course_rule_nodes.node_type` since the PDF only describes that column in prose and it's a different value space than `requirement_node_type` (documented in `enums.py`). Migration `1b0db359d548` hand-writes explicit `CREATE TYPE` + `ALTER COLUMN ... USING col::text::enum` (Alembic's autogenerate detects the type changes correctly but doesn't emit valid Postgres DDL for varchar→enum on populated tables) — applied cleanly against the live 1,012-course dataset with zero data loss, verified by re-diffing all row/value counts before and after, re-running `load_catalog.py` (idempotent, same counts), and confirming a bad enum value is now rejected by the database itself (`DataError`), not just app code. Appendix A's `degree_type` (BS/BA/NONE) was briefly added (`academic_programs.degree_type`) then deliberately dropped again in migration `564dcc9e0b41` — the optimizer only needs a program's requirement tree, not its BS/BA/none distinction, and `program_type` (MAJOR/MINOR/etc.) already tells it whether something is a degree at all. Loading the full catalog (§1.3) surfaced real controlled values these enums didn't have yet — migration `745ad80a45f7` adds `requirement_node_type.CREDIT_REQUIREMENT` and `course_rule_node_type.OTHER/PROGRAM_MEMBERSHIP/SUBJECT_LEVEL/CREDIT_HOURS` via `ALTER TYPE ... ADD VALUE`; see `db/SUMMARY.md` §4.

### 1.2 Alembic

- [x] `alembic init alembic` inside `backend/`; `env.py` points at `app.models.Base.metadata`.
- [x] `sqlalchemy.url` set at runtime from `app.config.get_settings().database_url` (repo-root `.env`-driven), not hardcoded in `alembic.ini`.
- [x] Generated the first migration: `alembic revision --autogenerate -m "initial schema"` (`a1d053466018_initial_schema.py`); reviewed by hand — all 28 `create_table`s, FKs, and constraints match the models.
- [x] `alembic upgrade head` applied successfully; confirmed all 28 tables + `alembic_version` exist (verified via `information_schema.tables`, then `psql \dt` inside the target Postgres).
- [x] Documented the two commands every teammate needs in `backend/README.md` (`alembic revision --autogenerate -m "..."`, `alembic upgrade head`), for both the native-host and Docker workflows.

### 1.3 Data loading

- [x] **Corrected course**: an earlier version of this loader scoped itself narrowly to one program (Aerospace BS/Minor) and derived `course_rule_nodes` by regex-parsing free-text descriptions in `catalog_scraper/output/*.json`, on the mistaken belief that `schedule_optimizer_db` had no prerequisite data at all. It does: `schedule_optimizer_db/course_rule_nodes.json` (4,777 rows) is already structured exactly like the `course_rule_nodes` table and is higher-quality than the regex-derived version (it already correctly handles the two edge cases — MOTR crosswalk notes, "accompanied by" corequisites — that the regex parser needed hand-written fixes for). `catalog_scraper/` and `db/prereq_parser.py` are no longer used anywhere.
- [x] Rewrote `db/load_catalog.py`: reads all 13 `schedule_optimizer_db/*.json` files (colleges, departments, subjects, courses, course_groups, course_group_courses, course_relations, academic_programs, academic_program_relationships, requirement_sets, program_requirement_sets, requirement_nodes, course_rule_nodes) and upserts every row into Postgres via the SQLAlchemy models, in FK-safe order (self-referencing trees — `requirement_nodes`, `course_rule_nodes` — inserted parent-before-child since a few rows in the source JSON list a child before its parent). `session.merge()` on every table's real primary key — safe to re-run, verified idempotent by running twice and diffing the "Done. Loaded ..." summary counts.
- [x] **Loads the entire catalog now, no scoping** — 146 of 147 academic programs have at least one requirement set attached as of this data drop (only Semiconductor Engineering BS currently has none), so there's no reason left to hold back to one program. One run loads:
  - 3 colleges, 24 departments, 54 subjects, **2,120 courses**.
  - 242 course groups, 21,381 course-group memberships, 315 course relations.
  - **147 academic programs**, 61 program-to-program relationships.
  - 165 requirement sets, 279 program↔requirement-set links, **2,890 requirement-tree nodes**.
  - **4,777 course_rule_nodes**, loaded verbatim — no parsing, no closure/scope computation needed since every row already ships with valid foreign keys into the full course set.
- [x] Two enum values needed adding to load the full catalog cleanly (values that never appeared in the narrow Aerospace scope): `requirement_node_type.CREDIT_REQUIREMENT` and `course_rule_node_type.{OTHER, PROGRAM_MEMBERSHIP, SUBJECT_LEVEL, CREDIT_HOURS}` — see `docs/PHASES.md` §1.1 and `db/SUMMARY.md` §4.
- [x] Rewrote `db/sanity_checks.sql` (5 queries, runnable via `psql -f` or `uv run python db/run_sanity_checks.py` if `psql` isn't on PATH) for the full-catalog load and ran all of them:
  - Row counts per table — match the source JSON array lengths exactly (see counts above).
  - Zero rows where a course directly requires itself.
  - Strict-`PREREQUISITE`-only cycle check — finds exactly 4 courses (2 Russian, 2 Biology "level-or-above" course clusters), a real, understood, benign property of the source data, not a bug — documented in `db/SUMMARY.md` §3a.
  - Aerospace BS's full requirement tree, hand-verified to be identical to the tree previously verified under the narrow-scope load (this program's own data didn't change, only its surrounding context did).
  - Exactly one program (`SEMIENG_BS_2026`) has zero requirement sets attached — expected, not a loader bug.
- [x] **Known data gap resolved**: `courses.fall_offered/spring_offered/summer_offered` previously had an identical placeholder value for every course (flagged in an earlier revision of this doc and `db/SUMMARY.md` §3b). `schedule_optimizer_db/courses.json` now has real, varied per-course values (7 distinct fall/spring/summer combinations across the catalog) — loaded the same as every other course field. See §3.1 below, which previously flagged this as a blocker for the CP-SAT term-eligibility constraints.

**Exit criteria**: `alembic upgrade head` succeeds (native or Docker Postgres); `load_catalog.py` runs without errors and is idempotent; all 5 sanity-check queries return correct, human-verified results. All met for the full catalog.

---

## Phase 2 — Backend Core & Domain Services ✅

**Goal**: Backend can answer "what does this program require" and "what has this student already completed," with no optimizer involved yet.

- [x] Pydantic schemas under `backend/app/schemas/` (`course.py`, `program.py`, `prerequisite.py`, `requirement.py`) mirroring the models needed for API I/O — kept separate from the SQLAlchemy models on purpose (see module docstring); reuse the same `(str, Enum)` classes from `app/models/enums.py` for type-safe serialization instead of redefining them.
- [x] `app/services/catalog_service.py`:
  - [x] `get_program(db, program_id)`, `list_programs(db)`, `get_course(db, course_id)`.
  - [x] `get_prerequisite_tree(db, course_id)` — resolves all `course_rule_nodes` targeting a course into a nested tree (root = `parent_rule_node_id IS NULL`), hydrating `required_course_id` into a full `CourseOut` (with subject code) via a shared `services/common.py` helper.
  - [x] `get_course_group_members(db, course_group_id)`.
- [x] `app/services/requirement_service.py`:
  - [x] `resolve_requirement_sets(db, program_ids: list[int])` — union of `program_requirement_sets` across selected programs, deduplicated by `requirement_set_id` (verified against two real programs that share `MST_GEN_ED_2026`).
  - [x] `flatten_requirement_tree(db, requirement_set_id)` — resolves one `requirement_nodes` table into a nested, evaluable tree (operator + children + hydrated course/course_group leaves) in one pass, no further DB round-trips needed to evaluate it.
- [x] `app/services/credit_matching_service.py`:
  - [x] `match_completed_courses(db, student_id, requirement_set)` — walks an already-flattened tree and fills in `is_satisfied` on every node: `COURSE`/`COURSE_GROUP` leaves check `student_credits` (status `COMPLETED`, best grade across retakes, `minimum_grade` compared via a letter-grade point scale, non-letter grades like P/CR always satisfying), `CREDIT_REQUIREMENT` leaves (no attached course/group — e.g. "12 credits of an approved minor") are never auto-satisfied, and container nodes aggregate their children per `node_operator` (`ALL`/`ANY`/`N_OF`/`CREDITS_FROM`/`UNITS_FROM`). Returns a new tree (`model_copy`) rather than mutating the input.
- [x] Read-only endpoints (`app/routers/programs.py`, `app/routers/courses.py`), wired into `main.py`:
  - [x] `GET /programs`
  - [x] `GET /programs/{id}/requirements` (one flattened tree per requirement_set attached to the program; 404 if the program doesn't exist)
  - [x] `GET /courses/{id}/prerequisites` (nested tree; 404 if the course doesn't exist)
- [x] 24 pytest tests (`backend/tests/`) against the real, fully-loaded local Postgres database from Phase 1 — no mocking, no separate test DB. Isolation comes from `tests/conftest.py`'s `db_session` fixture, which wraps each test in one outer transaction that's always rolled back (verified: `students`/`student_credits` tables are empty after a full test run), and a `client` fixture that overrides FastAPI's `get_db` dependency to reuse that same transactional session. Covers `flatten_requirement_tree` (root/group/course counts against the real Aerospace BS core + programming sets, hand-verified), `match_completed_courses` (real `ALL`/`ANY` aggregation across the COMP SCI 1972+1982 vs. 1570+1580 lecture/lab choice, grade-boundary and pass/fail edge cases via synthetic trees, `CREDIT_REQUIREMENT` never auto-satisfying, immutability of the input), `resolve_requirement_sets` (dedup across two real programs sharing `MST_GEN_ED_2026`), `get_prerequisite_tree`/`get_course_group_members`, and all 3 endpoints including their 404 paths.

**Exit criteria**: `GET /programs/1/requirements` (Aerospace BS) returns all 8 correct flattened requirement-set trees; `match_completed_courses` correctly propagates satisfaction through nested `ALL`/`ANY` groups for a hand-picked set of completed courses (verified in `tests/test_credit_matching_service.py`). All 24 tests pass (`uv run pytest`).

---

## Phase 3 — Optimization Engine (OR-Tools CP-SAT) — critical path ✅

**Goal**: Given a scenario, produce one or more valid, ranked, semester-by-semester plans.

Protect this phase's time above all others — it's the project's core value proposition and the biggest technical risk.

### Data gap closed first

- [x] `terms` had no source data anywhere in `schedule_optimizer_db/` (unlike every other table, which loads from structured JSON). [`db/seed_terms.py`](../db/seed_terms.py) generates 36 sequential Fall/Spring/Summer terms (Fall 2026 → Summer 2038), inserting only `term_code`s that don't already exist — idempotent, same pattern as `load_catalog.py`'s `merge()` but with no JSON to merge against.

### 3.1 Model construction

- [x] [`optimizer_terms.build_term_horizon(db, scenario)`](../backend/app/services/optimizer_terms.py) — ordered `Term`s from `start_term_id` forward, dropping `scenario_terms.is_excluded` terms and (unless `allow_summer`) `SUMMER` terms. The original phase used a 16-term cap; Phase 5.2 retained that fast initial horizon and added a no-target retry up to the 12-year safety limit. Explicit target terms remain hard boundaries.
- [x] [`optimizer_candidates.build_candidate_course_set(db, scenario)`](../backend/app/services/optimizer_candidates.py) — resolves the scenario's programs' requirement trees (reusing Phase 2's `requirement_service`/`credit_matching_service`), collects `COURSE`/`COURSE_GROUP` leaves, and walks `course_rule_nodes` PREREQUISITE/COREQUISITE/PRE_OR_COREQUISITE edges backward to pull in prerequisite closure, minus anything already in `student_credits`.
  - **Prerequisite closure growth cap**: bounded at `MAX_CLOSURE_GROWTH = 500` additional courses so a loosely-linked cluster (the same-or-above-level Russian/Biology ladder documented in `db/SUMMARY.md` §3a) cannot grow without limit while ordinary full-degree prerequisite closures remain intact; anything excluded is surfaced as a warning.
- [x] CP-SAT variables: `assign[course_id, term_id] : BoolVar` in [`optimizer_model.build_optimizer_model`](../backend/app/services/optimizer_model.py) for every (candidate course, eligible term) pair — eligible = course offered that term type per `courses.fall_offered/spring_offered/summer_offered` (real per-course data as of Phase 1, not the old uniform placeholder) and the term isn't excluded from the horizon.
- [x] Constraint: each course assigned to at most one term (`AddAtMostOne` per course across its eligible terms).
- [x] Constraint: prerequisite ordering — for each `course_rule_nodes` PREREQUISITE edge, the prerequisite's assigned term index < the dependent's (`AddBoolOr`/linear reification translating the underlying AND/OR/N_OF rule trees).
- [x] Constraint: corequisite — `COREQUISITE` same term index; `PRE_OR_COREQUISITE` prerequisite's term ≤ dependent's.
- [x] Constraint: per-term credit totals within `scenario_terms.minimum_credits/maximum_credits`, falling back to `planning_scenarios.default_minimum_credits/default_maximum_credits` (credits scaled ×10 and tracked as integers for CP-SAT, since OR-Tools has no native float domain).
- [x] Constraint: requirement coverage — for each `requirement_nodes` leaf/group, mirrors `credit_matching_service`'s `ALL`/`ANY`/`N_OF`/`CREDITS_FROM`/`UNITS_FROM` aggregation logic, but emits CP-SAT constraints instead of evaluating fixed booleans against already-completed courses alone.
  - **Double counting / `overlap_policies`**: `overlap_policies` has zero rows and `requirement_nodes` has no `allow_shared_course` column (that `docs/ARCHITECTURE.md` §5 line is aspirational, not implemented). Since nothing in the data restricts sharing, the solver allows one assigned course's same boolean variable to satisfy multiple requirement nodes by construction — directly matching UC-15's "maximize allowable double counting" given no policy says otherwise.
  - **`CREDIT_REQUIREMENT` leaves** (e.g. placeholder ROTC credit slots with no attached course/group): same rule as `credit_matching_service` — never auto-satisfied by the solver. They don't block feasibility; they surface as an advisor-signoff `optimization_messages` row instead.
- [x] Constraint: hard `scenario_preferences` (`REQUIRE_COURSE`, `AVOID_COURSE`, `FIX_COURSE_TO_TERM` where `is_hard_constraint = true`).

### 3.2 Objectives & ranking

- [x] [`optimizer_objectives.py`](../backend/app/services/optimizer_objectives.py) implements scoring expressions for the 5 objectives scoped in this doc (`MAX_INTEREST_ALIGNMENT`/`PRESERVE_FLEXIBILITY` stay unimplemented — no `course_tags` data exists yet to back interest-alignment anyway): `EARLIEST_GRADUATION` (minimize the max used term's `sequence_index`), `MIN_ADDITIONAL_CREDITS` (minimize total assigned credit hours against a "primary major alone" baseline solve), `MAX_REQUIREMENT_OVERLAP` (maximize courses that satisfy 2+ distinct scenario *programs*, not just 2+ requirement sets within one program), `BALANCED_WORKLOAD` (minimize the single heaviest term's credit total — a simpler proxy than full variance, matching UC-43's "based primarily on credit totals"), `MIN_SUMMER_ENROLLMENT` (minimize total credits assigned to `SUMMER` terms).
- [x] Solve recommended-plan objectives lexicographically. The minimum necessary coursework stage is locked first, followed by the student's ordered primary/secondary priorities and academic-quality tie-breakers. Every achieved stage is equality-locked before the next begins.
- [x] `optimizer_service.generate_recommended_plan` returns the recommended plan first; `generate_alternative_plans` independently explores strategy alternatives afterward under a hard wall-clock deadline.

### 3.3 Multiple distinct plans

- [x] [`optimizer_service.generate_alternative_plans`](../backend/app/services/optimizer_service.py) re-solves independent strategy objectives only after the recommended plan is available.
- [x] Alternatives with an exact assignment duplicate or a semantic duplicate (same course set, graduation term, and credits) are dropped, including duplicates of already-persisted plans.
- [x] Each surviving plan's `strategy_code` is the `OptimizationObjectiveType` value it was solved for (e.g. `EARLIEST_GRADUATION`, `MIN_ADDITIONAL_CREDITS`).

### 3.4 Persistence & explanations

- [x] [`optimizer_persistence.persist_plan`](../backend/app/services/optimizer_persistence.py) writes `degree_plans` + `plan_courses` + `requirement_allocations` (one row per (requirement_node, satisfying course) pair, including already-completed `student_credits` allocations) + `optimization_messages`. The schema has no `is_shared` boolean column — double counting is instead represented structurally, by a course/`plan_course` having *multiple* `requirement_allocations` rows pointing at it (one per requirement node it satisfies).
- [x] `optimization_messages` generated:
  - Infeasible scenario → a plain-language `ERROR`/`INFEASIBLE` message distinguishing "no schedule satisfies every hard constraint" from "solver couldn't verify within the time limit" (UC-56/UC-57).
  - `WARNING`/`ADVISOR_SIGNOFF_NEEDED` for each `CREDIT_REQUIREMENT` node the plan assumes is satisfied outside the tool.
  - `WARNING`/`PREREQUISITE_CLOSURE_CAPPED` for any course excluded from the candidate set by the closure growth cap.
  - `INFO`/`UNVERIFIED_PREREQUISITE_TYPE` summarizing prerequisite conditions (standing, exam, consent) the solver can't verify and assumes satisfied.
  - Offering-risk warnings for infrequently-offered courses scheduled late were scoped out for this prototype pass — no `course_offering_history` data exists to detect "infrequently offered" from, only the boolean `fall_offered/spring_offered/summer_offered` flags already enforced as a hard constraint.
- [x] `persist_plan` only `flush()`s, never `commit()`s — the caller (a future Phase 4 API route, or a test's rollback fixture) owns the transaction boundary, verified by `_smoke_persistence.py` during development leaving zero residual rows after rollback.

### 3.5 Testing

- [x] `test_optimizer_model.py` scenario A: primary program only (Aerospace BS), no restrictive preferences → feasible, and every requirement set's root node holds.
- [x] `test_optimizer_model.py` scenario B: tight per-term credit cap (9 credits) vs. a loose one (18 credits) → the tight cap's earliest-graduation solve needs a strictly later `graduation_index` than the loose cap's, confirming the credit-bound constraint actually binds.
- [x] `test_optimizer_model.py` scenario C: primary major (Aerospace BS) + its own department's minor with real shared courses → `collect_leaf_satisfactions` shows the same course satisfying requirement nodes from both programs' trees (the signal `optimizer_persistence` turns into multiple `requirement_allocations` rows for one `plan_course`).
- [x] `test_optimizer_candidates.py`: direct requirement-course inclusion, completed-course exclusion, prerequisite-closure growth capping, and cross-program overlap detection — all against real Aerospace BS/minor data.
- [x] `test_optimizer_service.py`: a real Aerospace BS scenario yields ≥2 plans with distinct assignment signatures, each correctly labeled with its objective's `strategy_code`; a scenario with an unreachably-early `target_graduation_term_id` returns exactly one infeasible plan with a clear reason instead of raising; an unknown `planning_scenario_id` raises `ValueError` instead of failing silently.

**Exit criteria**: ✅ All three named unit-test scenarios (A/B/C) pass with hand-verified expected output; `generate_plans` returns ≥2 meaningfully different, correctly-labeled plans for a real Aerospace BS scenario; an intentionally-infeasible scenario (unreachable target graduation term) returns a clear reason via `optimization_messages` instead of an error. Full suite: `uv run pytest` — all tests pass (Phase 1/2 tests unaffected, confirming no regression).

---

## Phase 4 — API Integration Layer ✅

**Goal**: A complete, documented HTTP surface for the frontend to build against.

- [x] [`POST /scenarios`](../backend/app/routers/scenarios.py) — body: selected programs (with role), completed/in-progress courses, per-term overrides, preferences, and objectives (ordered) — see [`schemas/scenario.py`](../backend/app/schemas/scenario.py). [`scenario_service.create_scenario`](../backend/app/services/scenario_service.py) enforces the design doc's Section 9.2 rule (exactly one `PRIMARY_MAJOR`) and that every referenced program/term/student id actually exists, creating a new `Student` row when no `student_id` is given (`422` for the business-rule violation, `404` for a missing reference). Returns `planning_scenario_id`.
- [x] [`POST /scenarios/{id}/generate/recommended`](../backend/app/routers/scenarios.py) persists and returns the recommended plan immediately; [`POST /scenarios/{id}/generate/alternatives`](../backend/app/routers/scenarios.py) generates alternatives separately. The legacy `/generate` endpoint remains compatible.
- [x] [`GET /plans/{id}`](../backend/app/routers/plans.py) — full semester-by-semester breakdown and `optimization_messages`, reusing Phase 3's `optimizer_persistence.load_degree_plan`.
- [x] [`GET /plans/compare?ids=1,2,3`](../backend/app/routers/plans.py) — side-by-side metrics via [`plan_comparison_service.compute_plan_metrics`](../backend/app/services/plan_comparison_service.py): graduation term, total credits, `additional_credit_hours` (a new nullable `degree_plans` column — Phase 3 always computed this in memory but never persisted it), max/avg per-term credits and summer-term count (derived from `plan_courses` joined to `terms.term_type`), and overlap credit hours (derived from `requirement_allocations` grouped by the underlying course/credit, counted once per course that satisfies 2+ nodes). `remaining_credit_hours` from the original spec wording is intentionally not included: a *generated* plan by definition already covers every requirement node, so there's no well-defined "remaining" figure at the plan level with the current schema. Declared before `GET /plans/{id}` in the router so `/plans/compare` isn't swallowed by that path parameter.
- [x] `GET /programs`, `GET /programs/{id}/requirements` (reused from Phase 2, unchanged).
- [x] Structured error responses: an infeasible `POST /scenarios/{id}/generate` call returns `200` with one `DegreePlanOut` whose `status` is `"INFEASIBLE"` and whose `messages` explain why — reusing Phase 3's existing `optimization_messages` machinery directly, no separate error envelope needed.
- [x] `GET /terms` was added too (not in the original bullet list): `POST /scenarios` requires real `start_term_id`/`target_graduation_term_id` values and there was previously no way for a client to discover valid term ids at all.
- [x] `/docs` confirmed usable: `GET /openapi.json` builds cleanly and lists every route (`/scenarios`, `/scenarios/{id}/generate`, `/plans/{id}`, `/plans/compare`, `/terms`, plus the Phase 2 routes).
- [x] **Transaction boundary**: [`app/database.py`](../backend/app/database.py)'s `get_db()` now commits on a successful request and rolls back on any exception — the first write endpoints needed this, since every service below it only `flush()`es (consistent with Phase 3's `persist_plan`). `tests/conftest.py`'s `client` fixture overrides `get_db` with a plain `yield db_session` (no commit), so the existing rollback-based test isolation from Phases 1-3 is unaffected — verified by the full suite leaving no residual rows.
- [x] 20 new pytest tests (`backend/tests/`): `test_scenario_service.py` (validation rules + persistence), `test_plan_generation_service.py` (objective filtering/ordering against real Aerospace BS data), `test_plan_comparison_service.py` (hand-built fixture, exact numbers verified), `test_scenarios_api.py` (the full HTTP journey below, plus validation-error paths), `test_plans_api.py` (`GET /plans/{id}` and `/compare`, including the route-ordering fix).

**Exit criteria**: ✅ A scripted end-to-end call sequence (`POST /scenarios` → `POST /scenarios/{id}/generate` → `GET /plans/{id}`) reproduces Phase 3's verified Scenario A (feasible, real Aerospace BS) and infeasible-target-graduation-term case over HTTP — both covered by `test_scenarios_api.py`. Full suite: `uv run pytest` — all tests pass (Phases 1-3 unaffected, confirming no regression).

---

## Phase 5 — Frontend ✅

**Goal**: A judge can complete the full user journey (product spec §10) in the browser with no dead ends.

- [x] Design system: `Nunito` (UI text) + `JetBrains Mono` (credit hours, term codes, course numbers) loaded via Google Fonts in [`index.html`](../frontend/index.html); a "collegiate navy + diploma gold" palette (`--primary`, new `--gold`/`--success`/`--warning` tokens) in [`index.css`](../frontend/src/index.css), kept separate from shadcn's own neutral `--accent` so gold stays a sparingly-used signature color. The **Term Ribbon** ([`term-ribbon.tsx`](../frontend/src/components/layout/term-ribbon.tsx)) is the signature element: the same pill-stepper component is the wizard's 5-step progress indicator and, restyled, the semester board's column headers on Screen 6.
- [x] Three small, additive backend endpoints the frontend needed that no earlier phase exposed: [`GET /courses?search=`](../backend/app/routers/courses.py) (`catalog_service.search_courses`, capped at 50 results) for Screen 2's course picker; [`GET /scenarios/{id}/plans`](../backend/app/routers/scenarios.py) so Screens 6-8 can reload a scenario's plans on refresh without re-running `/generate`; [`GET /plans/{id}/requirements`](../backend/app/routers/plans.py) (new [`plan_requirement_service.py`](../backend/app/services/plan_requirement_service.py), plus a `credit_matching_service.match_completed_courses(..., extra_completed_course_ids=...)` extension and a new `is_shared` field on `RequirementNodeOut`) for Screen 8's per-plan satisfied/remaining/shared view — shared detection reads the plan's real persisted `requirement_allocations` rather than re-deriving it, since that's the only place that records exactly which course satisfied which `COURSE_GROUP` leaf.
- [x] API client layer ([`frontend/src/lib/api/`](../frontend/src/lib/api/), one file per resource) typed against [`lib/types.ts`](../frontend/src/lib/types.ts) mirrors of the backend Pydantic schemas, plus TanStack Query hooks in [`frontend/src/hooks/`](../frontend/src/hooks/). Routing (`react-router-dom`): `/` (wizard) and `/plans/:scenarioId` (tabbed results). Wizard draft state lives in one `useReducer`-based [`ScenarioBuilderContext`](../frontend/src/state/scenario-builder-context.tsx).
- [x] Screen 1 — [`step-program-selection.tsx`](../frontend/src/components/wizard/step-program-selection.tsx): searchable primary-major combobox (`GET /programs`, filtered to `program_type=MAJOR`), starting-term and optional target-graduation-term selects (`GET /terms`).
- [x] Screen 2 — [`step-academic-progress.tsx`](../frontend/src/components/wizard/step-academic-progress.tsx): live course search (`GET /courses?search=`) to mark completed coursework, plus a manual transfer-credit form (title/credit hours, no catalog match required).
- [x] Screen 3 — [`step-academic-goals.tsx`](../frontend/src/components/wizard/step-academic-goals.tsx): first asks whether to add a second major, minor, or emphasis; major/minor browsing is organized by department, and emphasis options are restricted by the loaded `HAS_EMPHASIS` relationship to compatible selected majors.
- [x] Screen 4 — [`step-planning-constraints.tsx`](../frontend/src/components/wizard/step-planning-constraints.tsx): min/max credit-hour sliders, an allow-summer switch, and a simple per-upcoming-term exclude toggle list (maps directly to `scenario_terms.is_excluded`) instead of a calendar-grid widget.
- [x] Screen 5 — [`step-objective-selection.tsx`](../frontend/src/components/wizard/step-objective-selection.tsx): one required primary priority plus up to two optional secondary priorities, submitted in lexicographic order.
- [x] Submit flow ([`wizard-page.tsx`](../frontend/src/pages/wizard-page.tsx)): `POST /scenarios` → `POST /scenarios/{id}/generate` → navigate to `/plans/:scenarioId`, with the generated plans passed via router state to avoid an extra round-trip.
- [x] Screen 6 — [`plan-board.tsx`](../frontend/src/components/plans/plan-board.tsx): a horizontally-scrollable semester board headed by the Term Ribbon, each course a card with subject/number/title/credit hours, a running per-term credit total, and a summary card (status, total/extra credits, projected graduation, `optimization_messages`).
- [x] Screen 7 — [`plan-comparison-table.tsx`](../frontend/src/components/plans/plan-comparison-table.tsx): `GET /plans/compare` metrics table across every generated plan, plus a "why this differs" card per plan synthesized client-side from its `plan_name` (which is literally the `OptimizationObjectiveType` value the solver used for that plan, per `optimizer_persistence._create_degree_plan`) mapped through a small human-readable label/description table.
- [x] Screen 8 — [`requirement-coverage-tree.tsx`](../frontend/src/components/plans/requirement-coverage-tree.tsx): `GET /plans/{id}/requirements` rendered as a nested tree with satisfied (green check) / remaining (empty circle) / shared (gold "Shared" badge) states, with a plan picker when a scenario has more than one generated plan.
- [x] Loading/empty/error states ([`components/shared/`](../frontend/src/components/shared/): `loading-state.tsx`, `empty-state.tsx`, `error-state.tsx`) used consistently across every screen; responsive throughout via Tailwind (`overflow-x-auto` term board/table, `sm:`-breakpoint grid/flex layouts).
- [ ] Stretch (skipped, out of scope for this pass): React Flow diagram of a program's requirement tree or a course's prerequisite chain.

**Exit criteria**: ✅ `tsc -b` and `oxlint` both clean; `vite build` succeeds. A scripted cold-run walkthrough exercising every new/changed endpoint in the exact sequence the frontend calls them (`GET /terms` → `GET /programs` → `POST /scenarios` with a primary major + minor → `POST /scenarios/{id}/generate` → `GET /scenarios/{id}/plans` → `GET /plans/compare` → `GET /plans/{id}/requirements`) against the real Aerospace BS/minor catalog data succeeds end to end, including real detected `is_shared` requirement nodes. Full backend suite: `uv run pytest` — all tests pass (Phases 1-4 unaffected, confirming no regression).

---

## Phase 5.1 — Plan Board & Wizard UX Enhancements ✅

**Goal**: Address real usability gaps found while dogfooding Phase 5's wizard/plan-board journey — missing school picker, noisy repeated warnings, an all-at-once elective picker, and a plan comparison screen with no way to see an alternative's actual schedule.

- [x] **School (college) selection restored**: [`step-school-selection.tsx`](../frontend/src/components/wizard/step-school-selection.tsx) — Screen 1 now starts with a `GET /colleges` picker (CEC/Kummer/CASE) before the program combobox, using [`use-colleges.ts`](../frontend/src/hooks/use-colleges.ts); the program combobox then defaults to that college's programs, with a "look at every school" escape hatch (`showAllSchools` switch) since `academic_program_relationships` still has no rows to filter by automatically.
- [x] **Toast notifications** ([`sonner`](../frontend/src/components/ui/sonner.tsx)) replace repeated inline `optimization_messages` banners — one toast per distinct message code instead of one line per affected course, so a plan with 20+ "prerequisite excluded by closure cap" warnings shows one grouped notice instead of 20 identical paragraphs.
- [x] **Stepwise elective choices**: [`step-course-choices.tsx`](../frontend/src/components/wizard/step-course-choices.tsx) + [`requirement-choice-card.tsx`](../frontend/src/components/wizard/requirement-choice-card.tsx) replace "show every elective decision at once" with one choice per screen (progress dots, back/next), backed by a new [`GET /requirement-choices`](../backend/app/routers/choices.py) endpoint ([`requirement_choice_service.list_requirement_choices`](../backend/app/services/requirement_choice_service.py)) that finds the *decision points* in a program's requirement tree (`COURSE_GROUP` leaves and literal "MATH 1214 or MATH 1215" `ANY`/`N_OF` containers) instead of asking the client to walk the whole tree itself. Answers submit as `REQUIRE_COURSE` scenario preferences, already enforced as a hard constraint by `optimizer_model`.
- [x] **Glass morphism theme**: `glass-panel`/`glass-inset` utility classes ([`index.css`](../frontend/src/index.css)) — translucent, blurred surfaces layered over the navy/gold palette — applied across the wizard steps, plan board, and comparison screens.
- [x] **Semester-wise course swapping on the Plan Board (Screen 6)** — chosen over a second wizard elective-picker pass, Stellic/DegreeWorks style: swap a course for another valid option *for that exact term slot*, without re-running the solver.
  - [x] [`GET /plans/{id}/swap-options`](../backend/app/routers/plans.py) ([`requirement_choice_service.list_swap_options_for_plan`](../backend/app/services/requirement_choice_service.py)) — for each `plan_courses` row, traces its `requirement_allocations` back to the requirement node it satisfies and returns that node's other course-group members or ANY/N_OF siblings as swap candidates; absent entirely for a mandatory single-course node.
  - [x] [`POST /plans/{id}/courses/{plan_course_id}/swap`](../backend/app/routers/plans.py) ([`plan_swap_service.swap_plan_course`](../backend/app/services/plan_swap_service.py)) — mutates the existing `plan_courses` row in place (so its `requirement_allocations` keep tracking the same node with no extra bookkeeping), keeps `requirement_allocations.credit_hours_applied` and the plan's cached credit totals in sync.
  - [x] **Swap validation** ([`plan_swap_validation.py`](../backend/app/services/plan_swap_validation.py)) — every swap is checked against the same hard constraints `optimizer_model` enforces when building a plan from scratch, reimplemented as plain Python over one already-solved plan's fixed placements: (1) the new course must be offered that term's type (`fall_offered`/`spring_offered`/`summer_offered`); (2) the new course's credit hours can't push that term over its `scenario_terms` override or the scenario's `default_maximum_credits` cap; (3) the new course's prerequisite/corequisite tree (`course_rule_nodes`) must already be satisfied by the student's completed credits or by another course this plan places early enough (e.g. swapping in MATH 212 requires this plan to already have MATH 191 placed in an earlier term, or completed). `list_swap_options_for_plan` pre-filters candidates through the same checks, so the plan board never *offers* a swap it would then reject. Violations surface as `422` with a plain-language reason.
  - [x] [`swap-course-button.tsx`](../frontend/src/components/plans/swap-course-button.tsx) — a per-course-card popover (searchable, `cmdk`-based) listing only the alternatives that passed validation, with toast success/error feedback.
- [x] **Suggested major/minor overlap** (Screen 3, "any other goals?"): [`GET /programs/{id}/overlap-suggestions`](../backend/app/routers/programs.py) ([`program_overlap_service.py`](../backend/app/services/program_overlap_service.py)) ranks other programs by what share of *their own* requirements are already covered by the primary program's courses (a coverage ratio, not a raw shared-course count, so a small 15-credit minor that's 90% covered outranks a huge major with a bigger absolute overlap) — deliberately excludes course groups over 50 members (broad gen-ed pools nearly every program can draw from) so the signal isn't swamped by noise. Surfaced as an "suggested \{second majors/minors/emphases\} that overlap with your major" panel with one-tap add.
- [x] **View schedule for alternatives** (Screen 7): each plan's summary card in [`plan-comparison-table.tsx`](../frontend/src/components/plans/plan-comparison-table.tsx) got a "View schedule" action that renders that alternative's full term-by-term `PlanBoard` inline, so a judge/student can inspect the actual courses behind a strategy, not just its aggregate metrics.
- [x] **Add/remove courses on the Plan Board (Screen 6)**, alongside swap — the same `plan_swap_validation` checks (offered-in-term, credit cap, prerequisites) were generalized (`validate_swap`/`validate_add` sharing one `_validate_course_for_slot` helper) so an add is held to the same standard as a swap:
  - [x] [`POST /plans/{id}/courses`](../backend/app/routers/plans.py) ([`plan_swap_service.add_plan_course`](../backend/app/services/plan_swap_service.py)) — places a brand-new course into a specific term as an extra elective (`STUDENT_ADDED` placement source), via [`add-course-button.tsx`](../frontend/src/components/plans/add-course-button.tsx)'s per-term-column search popover.
  - [x] [`DELETE /plans/{id}/courses/{plan_course_id}`](../backend/app/routers/plans.py) ([`plan_swap_service.remove_plan_course`](../backend/app/services/plan_swap_service.py)) — removes only courses marked removable, then revalidates and reallocates the entire plan. Any loss of requirement coverage, prerequisite validity, credit-floor compliance, offering validity, or term-load validity rolls the edit back.
  - [x] [`POST /plans/{id}/courses/{plan_course_id}/move`](../backend/app/routers/plans.py) moves a course to a different term and runs the same whole-plan validation, including downstream prerequisite ordering.
- [x] **Overlap suggestions after generating, not just during the wizard** — the same "suggested minors/second majors that overlap with your major" idea from Screen 3/4 now also surfaces on the results page ([`plan-overlap-suggestions.tsx`](../frontend/src/components/plans/plan-overlap-suggestions.tsx)), staying visible across every tab and through swaps/adds/removes (it isn't scoped to any one edit). Accepting a suggestion there needs a scenario that's already been created, so two new endpoints were added: [`GET`/`POST /scenarios/{id}/programs`](../backend/app/routers/scenarios.py) ([`scenario_service.list_scenario_programs`/`add_scenario_program`](../backend/app/services/scenario_service.py), rejecting a second `PRIMARY_MAJOR` or a duplicate program with `422`) — accepting a suggestion adds the program then re-runs `/generate` so its requirements actually show up. The wizard's `OverlapSuggestionCard` was extracted to [`components/shared/overlap-suggestion-card.tsx`](../frontend/src/components/shared/overlap-suggestion-card.tsx) so both screens share one implementation.
- [x] **Credit-total floor**: found by dogfooding a real Aerospace BS scenario — its 5 solved plans all landed on 126 credits even though the catalog's `academic_programs.total_credit_hours` says 128, since `_add_requirement_coverage_constraints` (Phase 3) only forces each *named* requirement node, not the program's published total. [`optimizer_candidates._resolve_credit_floor_remaining`](../backend/app/services/optimizer_candidates.py) now computes the gap (highest `total_credit_hours` among the scenario's `PRIMARY_MAJOR`/`SECOND_MAJOR` programs, minus credits the student already earned per `student_credits`), and [`optimizer_model._add_program_credit_floor_constraint`](../backend/app/services/optimizer_model.py) enforces it as a hard `sum(assigned credit hours) >= remaining` constraint, padded from the same elective/course-group candidates already in scope (no separate "free elective" pool needed). Relaxable per scenario via a new `enforce_program_credit_minimum` toggle (on by default, alongside the credit-load sliders on Screen 6) in case a scenario's candidate pool has no slack to pad the gap with — also added to `_collect_relaxation_suggestions`'s infeasibility hints. This constraint (plus the existing `COURSE_GROUP` credit-hour thresholds) made some real scenarios need noticeably more search time to even find one feasible schedule, not just to prove optimality, so `optimizer_service`'s fixed 10s-per-solve limit was replaced with `DEFAULT_MAX_TOTAL_SOLVE_SECONDS = 270.0` (4.5 min) shared across the whole `generate_plans` call via a single deadline (`_remaining_seconds`) rather than reset per solve — a scenario that's genuinely hard to prove feasible/infeasible gets (most of) the whole budget for that one check instead of bailing at a fixed 10s, while an easy scenario still returns in seconds since CP-SAT stops as soon as it proves `OPTIMAL`.
- [x] 45+ new backend tests (`test_program_overlap_service.py`, `test_plan_swap_service.py`, `test_plan_swap_validation.py`, `test_requirement_choice_service_swap_options.py`, `test_scenario_service.py`, `test_scenarios_api.py`, plus additions to `test_catalog_api.py`/`test_plans_api.py`/`test_optimizer_model.py`/`test_optimizer_candidates.py`); `tsc -b` and `oxlint` clean on the frontend throughout.
- [x] **README**: rewrote the setup walkthrough with an explicit native-Postgres-vs-Docker choice at step 3 (install Docker Desktop as an alternative to a native Postgres install, not just for the whole backend), plus a "Plan-board edit limits" section documenting swap/add/remove's validation rules and a "Reaching your major's full credit total" section for the new floor constraint.

**Exit criteria**: ✅ Full backend suite passes (Phases 1-5 unaffected); a swap or add that violates term-offering, a term's credit cap, or prerequisite ordering is rejected with a clear `422` reason and never appears as an offered option in the first place; a removed course's `requirement_allocations` are cleaned up so the plan's credit totals stay accurate; overlap suggestions surface the real Aerospace BS/minor shared-course relationship correctly ranked, both in the wizard and on the results page; a fresh-student Aerospace BS plan now reaches the full 128 published credits instead of stopping at 126.

---

## Phase 5.2 — Correctness, optimization, and decision UX ✅

**Goal**: Make every generated or manually edited plan academically defensible,
keep the FA26 prototype boundary explicit, and return the best plan before optional
alternatives.

- [x] Treat the 13 structured JSON files as read-only FA26 source data; keep the historical scraper out of the runtime and loader path.
- [x] Validate program roles and restrict emphases through `HAS_EMPHASIS` parent relationships; organize second-major/minor choices by department.
- [x] Enforce requirement-node minimum course level and minimum distinct subjects, course equivalence/cross-listing, duplicate-credit relations, `CREDIT_HOURS`, and `PROGRAM_MEMBERSHIP` prerequisites.
- [x] Count only degree-applicable completed credits toward the program-credit floor while retaining all completed credits for standing checks.
- [x] Materialize actual node/course usage so allocations, overlap metrics, and shared-course explanations reflect the solved plan rather than candidate eligibility.
- [x] Enforce available overlap-policy rows and surface a warning when multi-program plans have no explicit policy data.
- [x] Replace the weighted objective approximation with locked lexicographic stages: minimum necessary coursework, ordered student priorities, then early-5000 and academic-quality tie-breakers.
- [x] Return and persist the recommended plan separately before generating semantically distinct alternatives; never start a solver stage after its hard deadline.
- [x] Give summer a separate 9-credit default cap, seed 36 planning terms, and retry a no-target scenario with the longer horizon when 16 terms are infeasible.
- [x] Revalidate and reallocate the entire plan after add, swap, move, or remove; roll the transaction back when an edit breaks any hard academic rule.
- [x] Label course roles and edit capabilities, distinguish degree-applicable from scheduled workload credits, expose comparison balance/high-level metrics, and display the advisor-verification disclaimer.

**Exit criteria**: ✅ Unit and integration tests cover relationship validation,
level/distinct-subject rules, equivalence and duplicate credit, structured
prerequisites, hard deadlines, long horizons, lexicographic priority order, and
whole-plan edits. Backend and frontend verification commands are documented in the
root README.

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
