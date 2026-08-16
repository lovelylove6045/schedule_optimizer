# Project Plan — Overview

Timeline anchor: Submission Deadline is **August 21, 2026, 11:59 PM ET** (`Competition Official Rules.pdf`). This overview assumes work starts ~Aug 12, 2026, giving roughly **9 days**. Adjust to your actual start date; what matters is the phase order and dependencies below.

Companion docs:

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — tech stack and system design (local Postgres in Docker + Alembic, FastAPI + OR-Tools backend, React frontend, future Azure container deployment).
- [`docs/PHASES.md`](PHASES.md) — the detailed, checkbox-level task breakdown for every phase below. **Use that file as the day-to-day working checklist.**

## Phases at a glance

| Phase | Focus | Depends on |
|---|---|---|
| 0 | Local environment setup (Docker Compose: Postgres + backend; frontend scaffold) | — |
| 1 | DB schema via Alembic + narrow real data load | 0 |
| 2 | Backend core services (requirement resolution, credit matching, catalog endpoints) | 1 |
| 3 | **Optimization engine** (OR-Tools CP-SAT) — critical path | 2 |
| 4 | API integration layer (scenario create/generate, plan detail/compare) | 2, 3 |
| 5 | Frontend (full user journey) | 2 (starts), 4 (completes) |
| 6 | Full local integration pass (everything in Docker together) | 3, 4, 5 |
| 7 | Azure deployment (Container Apps + Azure DB for PostgreSQL) | 6 |
| 8 | Submission prep (video, overview, tools disclosure) | 7 |
| 9 | Correctness/UX refactor (FA26 scope, lexicographic solve, safe edits, academic rules) | 5 |

## Dependency summary

```
Phase 0 (local setup)
   └─ Phase 1 (DB schema + data)
         └─ Phase 2 (backend core)
               ├─ Phase 3 (optimizer, critical path)  ──┐
               └─ Phase 5 (frontend, starts once Phase 2 read endpoints exist)
                                                          ├─ Phase 4 (API integration)
                                                          └─ Phase 6 (full local integration)
                                                                └─ Phase 7 (Azure deploy)
                                                                      └─ Phase 8 (submission)
```

If working solo or in a small team, **Phase 3 (optimizer)** is the piece to start earliest and protect most — everything else can flex around it, but a working optimizer is the project's core value proposition per the product spec. Azure deployment (Phase 7) is intentionally sequenced *after* a full local Docker integration pass (Phase 6), so cloud-specific issues don't block feature development early on.
