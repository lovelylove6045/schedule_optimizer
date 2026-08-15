# Data Loading — What Happened, In Plain Language

This explains Phase 1.3 ("Data loading"): what's loaded into Postgres, where
it comes from, and a few real quirks in the data worth knowing about before
Phase 3 (the optimizer) builds on top of it.

## 1. Where the data comes from

`schedule_optimizer_db/` contains 13 JSON files. Every single one of them is
already shaped exactly like one of our 28 Postgres tables — same column
names, same ids, same foreign keys. `db/load_catalog.py` reads all 13 files
and upserts every row into Postgres, in an order that respects foreign keys.
No scope filtering, no free-text parsing needed — including for
prerequisites: `schedule_optimizer_db/course_rule_nodes.json` is already a
structured tree (`GROUP`/`COURSE`/`STANDING`/etc. nodes with real
`required_course_id` foreign keys), not free text to interpret. One example
row:

```json
{
  "course_rule_node_id": 11042,
  "target_course_id": 1718,
  "requisite_type": "PREREQUISITE",
  "node_type": "GROUP",
  "rule_operator": "ALL",
  "source_text": "Aero Eng 3251 and Aero Eng 3361 and Aero Eng 3171"
},
{
  "course_rule_node_id": 13443,
  "target_course_id": 1718,
  "parent_rule_node_id": 11042,
  "requisite_type": "PREREQUISITE",
  "node_type": "COURSE",
  "required_course_id": 1709,
  "source_text": "Aero Eng 3251"
}
```

One run of `load_catalog.py` loads the entire university catalog:

- 3 colleges, 24 departments, 54 subjects, **2,120 courses**
- 242 course groups (elective pools), 21,381 course-group memberships
- 315 cross-listing/duplicate-credit course relations
- **147 academic programs** (majors, minors, emphases), 61 program-to-program
  relationships (e.g. "this emphasis belongs to that major")
- 165 requirement sets, 279 program↔requirement-set links, **2,890
  requirement-tree nodes**
- **4,777 prerequisite/corequisite rule nodes**

Safe to re-run any time — every table is keyed by its real primary key from
the JSON and loaded with an upsert (`session.merge()`), so running it twice
in a row produces identical data (verified).

## 2. Why the whole catalog, not just one program

146 of the 147 academic programs have at least one requirement set attached
(only Semiconductor Engineering BS currently has none — see
`sanity_checks.sql` Query 5), so there's no real subset of the catalog the
app can't use. Loading everything is also simpler than maintaining a
scope-resolution step that decides which courses/programs to pull in.

## 3. Known characteristics of the real data worth knowing about

`load_catalog.py` copies `course_rule_nodes.json` and `requirement_nodes.json`
verbatim, so anything unusual here reflects the source data itself, not a
loading mistake.

### 3a. A handful of "level-or-above" course clusters look like cycles

`sanity_checks.sql` Query 3 checks for courses that indirectly require
themselves through a chain of *strict* prerequisites (ignoring corequisites,
which are allowed to be mutual). That finds exactly **4 courses**, in two
small clusters:

- Russian: `RUSSIAN 3790` ("Scientific Russian") and `RUSSIAN 5790`
  ("Advanced Scientific Russian")
- Biology: `BIO SCI 2242` ("Cave Biology") and `BIO SCI 3783` ("Biological
  Design and Innovation I")

The catalog phrases their prerequisite as "Russian 1180 or above" (or
similar). That's stored as one `COURSE` node per matching course inside an
`ANY` group — so *every* course at or above that level lists *every other*
course at that level as an acceptable alternative, including ones numbered
higher than itself. E.g. "Scientific Russian" (3790) lists "Advanced
Scientific Russian" (5790) as one acceptable alternative, and vice versa.

**Why this isn't a real scheduling deadlock:** it's an `ANY` group, not
`ALL` — a student only needs to have completed *one* course from the list,
not all of them, so nothing ever literally requires "take course A before
you can take course A." In practice a student takes these in numbering
order and it's a non-issue. Flagging it here so Phase 3 (the optimizer)
knows a naive "must resolve to a strict global course ordering" check would
flag these 4 courses, and shouldn't hard-fail on it.

### 3b. `courses.fall_offered` / `spring_offered` / `summer_offered` have real per-course values

These three columns have real, varied values — 7 distinct fall/spring/summer
combinations across the 2,120 courses — so Phase 3's CP-SAT term-eligibility
constraints can be built directly against them.

## 4. Two enum values needed adding

Loading the entire catalog surfaced controlled values that didn't exist yet
in `backend/app/models/enums.py`:

- `requirement_nodes.node_type` needed `CREDIT_REQUIREMENT` (used 3 times,
  e.g. a generic "12 credits of an approved minor" placeholder node that
  doesn't point at a specific course or course group).
- `course_rule_nodes.node_type` needed `OTHER`, `PROGRAM_MEMBERSHIP`,
  `SUBJECT_LEVEL`, and `CREDIT_HOURS` (used 182, 47, 20, and 5 times
  respectively).

Both are native Postgres `ENUM` types, so adding a value is a real schema
migration (`ALTER TYPE ... ADD VALUE`) — see
`backend/alembic/versions/745ad80a45f7_*.py`. Postgres has no `DROP VALUE`
for enums, so that migration's `downgrade()` is a documented no-op.

## 5. Why 3 separate files instead of 1

| File | Job |
|---|---|
| `load_catalog.py` | Reads all 13 `schedule_optimizer_db/*.json` files and upserts everything into Postgres, in FK-safe order. |
| `sanity_checks.sql` | Plain SQL queries anyone can run (with `psql` or any Postgres client) to double-check the loaded data looks right. |
| `run_sanity_checks.py` | Convenience wrapper that runs `sanity_checks.sql` for people who don't have `psql` set up (like this machine) — not "real" logic, kept separate and disposable. |
