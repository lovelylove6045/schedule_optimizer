# Data Loading — What Happened, In Plain Language

This explains Phase 1.3 ("Data loading"): what we were trying to do, why the
two source JSON folders are actually very different shapes, why we didn't
just dump everything into the database in one shot, everything that went
wrong along the way, and why the work ended up split across four files in
`db/`.

## 1. What we were trying to do

We have a Postgres database with 28 empty tables (courses, requirements,
degree plans, etc. — set up in Phase 1.1/1.2). We needed to actually put real
data into it: real courses, real degree requirements, real prerequisites —
so the rest of the app (and later, the optimizer) has something real to work
with instead of an empty database.

## 2. Two data sources — and they are NOT the same shape

This is worth being very explicit about, because it's the whole reason the
loading process was harder than "just copy the JSON into the database."

We have **two** source folders, and only **one** of them looks like our
database:

### `schedule_optimizer_db/*.json` — matches our database tables closely

This one really is shaped like our tables. One JSON object = one future
database row. Example, one course:

```json
{
  "course_id": 1699,
  "subject_id": 40,
  "course_number": "2360",
  "course_title": "Dynamics",
  "credit_hours": "3.0",
  "course_description": "The principles of mechanics are used..."
}
```

That maps almost 1-to-1 onto our `courses` table. Easy. This is what we
directly upsert into Postgres.

**But this folder has no prerequisite data at all.** The only "relationship"
file it has (`course_relations.json`) is for things like cross-listings
("Theatre 3245 is secretly the same course as Speech 3245") — not
"you must take X before Y."

### `catalog_scraper/output/*.json` — just scraped web text, NOT shaped like our database

This one is a completely different shape. It's what you'd get if you copy-
pasted the university's public course catalog page for every course. One
JSON object = one paragraph of English text, nothing more:

```json
{
  "subject_code": "AERO ENG",
  "course": "AERO ENG 2360  Dynamics (LEC 3.0)",
  "description": "The principles of mechanics are used to model engineering systems. Kinematics of particle motion... Prerequisite: Grade of \"C\" or better in each of Civ Eng 2200, Math 2222. (Co-listed with Mech Eng 2360)."
}
```

There is no `required_course_id` field here. There's no structure at all —
it's one big free-text sentence, and the prerequisite information is buried
*inside* the English, mixed in with the rest of the course blurb. A computer
can't "read" that sentence the way a human does; it has no idea "Civ Eng
2200" and "Math 2222" are course codes unless we teach it to recognize that
pattern with a program we write ourselves (that's `prereq_parser.py`).

**So the short answer to "why not just upload it":** `schedule_optimizer_db`
*is* basically ready to upload as-is (and we do exactly that). But it's
missing prerequisites entirely. The only place prerequisites exist at all is
buried in messy scraped English text in the *other* folder, which is not
database-shaped and has to be interpreted, not just copied.

## 3. Why we didn't just upload the *entire* catalog

`schedule_optimizer_db` has **2,120 courses total** across the whole school.
Out of those, only **one degree program** (Aerospace Engineering, plus its
minor) actually has a full requirement tree built — i.e., a real answer to
"what courses does a student need to take to graduate with this degree." All
the other ~50 subjects are just a flat list of courses with no requirements
attached to them yet.

So loading "everything" would have meant:

- Importing ~2,000 courses that the app can't do anything useful with yet
  (no degree requires them, so there's nothing to check them against).
- Running the English-sentence prerequisite parser against all 2,120 courses
  at once, which — as you'll see below — turned out to have real bugs.
  Debugging those bugs against 2,000 courses at once would have been much
  harder than debugging them against ~1,000.

Instead, we loaded **only what's needed for one real degree**: Aerospace
Engineering BS + its minor. That's still substantial — 1,012 courses in the
end, because "gen-ed" requirements (English, History, etc.) pull in courses
from many other subjects too — but it's a scope we can actually check by
hand and trust, before ever pointing the loader at the full catalog.

Think of it like building one working room of a house completely (wiring,
plumbing, paint) before framing all the other rooms — you learn what's wrong
with your blueprint on one room, not on the whole house at once.

## 4. Everything that went wrong (and how we found each one)

### Problem 1: There's no prerequisite data anywhere in the clean JSON files

Covered above in section 2 — this is *why* `prereq_parser.py` had to exist
at all. Since English is messy and we'll never parse it 100% perfectly, we
built it as **best effort**: anything it's confident about becomes a real,
structured link in the database; anything it can't confidently parse gets
saved as plain text instead of being silently thrown away. Example of the
"can't confidently parse" fallback:

> Raw text: `"Consent of instructor required"`
> Result: saved as-is, flagged as unparsed, instead of guessing and getting
> it wrong.

### Problem 2: A university crosswalk note tricked the parser into a "self-loop"

Some course descriptions end with an unrelated bonus sentence, e.g.:

> "...Prerequisite: A grade of 'C' or better in Math 1103; or by placement
> examination. **MATH 1120 - MOTR MATH 130: Pre-Calculus Algebra**"

That bolded bit just says "this course transfers as MOTR MATH 130 at other
Missouri schools" — nothing to do with prerequisites. But our first version
of the parser didn't know that, and it saw "MATH 1120" sitting right there
in the same sentence, so it created a nonsense rule: **"MATH 1120 requires
MATH 1120"** — a course requiring itself!

We caught this by writing a small check that looks for cycles (loops) in the
prerequisite data — a course should never (directly or indirectly) require
itself. That check found the MATH 1120 self-loop immediately.
**Fix:** we now cut off that trailing "MOTR" note before parsing the rest of
the sentence.

### Problem 3: Some "prerequisites" are secretly "must take together with"

A few pairs of courses (like a lecture + its lab) are written like this:

> `COMP SCI 1972` description: "Prerequisite: **Accompanied by** Comp Sci 1982..."
> `COMP SCI 1982` description: "Prerequisite: **Accompanied by** Comp Sci 1972..."

Read literally as "prerequisite," this says "1972 needs 1982 first, AND 1982
needs 1972 first" — impossible, you could never take either one first! But
"accompanied by" actually means "take at the same time" — it's really a
**corequisite**, not a strict prerequisite. Our cycle-checker caught this
exact pair as another loop.
**Fix:** whenever we see the phrase "accompanied by," we now file it as a
corequisite instead of a prerequisite, which is allowed to be mutual (you
register for both at once, no ordering problem).

### Problem 4: Course descriptions use abbreviations that don't match the official subject codes

The database's official subject code for Physics is `PHYSICS`, and for
Mechanical Engineering it's `MECH ENG`. But some course descriptions use
shorter, inconsistent abbreviations when mentioning other courses:

> `MECH ENG 5544` description: "Prerequisite: **Phys** 2135; **Mech** 3525 or
> consent of instructor..."

Our parser looks for the *official* subject codes, so it doesn't recognize
"Phys" or "Mech" as course-subject abbreviations — it correctly refuses to
guess, and saves the whole thing as unparsed plain text instead of silently
linking to the wrong course (or crashing). This is a real limitation, not a
bug we "fixed" — teaching the parser every possible abbreviation the
university has ever used isn't worth the effort right now, and it's safer
to under-parse than to guess wrong.

### Problem 5: "A or B or C" written as one sentence loses its exact logic

Some prerequisites have real nested logic, e.g. for `MATH 1215`:

> "Prerequisites: A grade of 'C' or better in Math 1214; **or** a grade of
> 'C' or better in **both** Math 1210 **and** Math 1211."

In plain English that means: *(Math 1214) OR (Math 1210 AND Math 1211)* —
two different valid paths, one of which needs two courses together. Our
parser is only smart enough to build one flat group, so it currently
(incorrectly) records this as *any one of* Math 1214, Math 1210, or Math
1211 — losing the fact that 1210 and 1211 must be taken **together** if
you're going that route. This is a known, documented limitation (see the
comment at the top of `prereq_parser.py`) — writing a parser that fully
understands nested "and/or" English grammar is a much bigger project, and
wasn't worth it for a "best effort" first pass.

### Problem 6: A "show me the full prerequisite chain" query exploded

Once real data was loaded, we tried to write a database query that walks
"what does this course need, and what do *those* courses need," all the way
back. The first version of that query technically never stopped producing
new rows in a reasonable time — not because of a real infinite loop, but
because many advanced courses all eventually depend on the same basic math
courses (Calculus, Algebra, etc.). Every time two different paths reconverge
on the same course ("both paths need Calc II eventually"), a naive query
re-explores that course's own prerequisites all over again, and this
multiplies out of control (1,600+ duplicate-looking rows for one course!).
**Fix:** we rewrote the query to say "show me each required course *once*,
at the shortest distance it takes to reach it" — which is both correct and
fast (23 rows instead of 1,600+).

### Other limitations worth knowing about (not bugs, just "be aware")

- The parser assumes one course only has one grade requirement per
  prerequisite clause; if a sentence mixes different required grades for
  different courses in a genuinely complex way, it may not separate them
  perfectly.
- We only load prerequisite data for courses inside our Aerospace BS/Minor
  scope. If you widen the loader to another program later, courses outside
  the current scope won't have their prerequisites parsed until that
  program is loaded too.
- The parser can only find courses that actually exist in
  `schedule_optimizer_db`. If a description mentions a course that was
  removed from the catalog or renamed, that mention is safely dropped rather
  than linked to the wrong thing.

## 5. Why 4 separate files instead of 1 big script

Everything *could* have been crammed into one file, but each of these does a
genuinely different job, and keeping them separate made all of the problems
above much easier to find and fix in isolation:

| File | Job | Why separate |
|---|---|---|
| `load_catalog.py` | The main script: reads the JSON files, decides "which courses/requirements are in scope," and writes everything into Postgres. | This is the orchestrator — it calls the parser, but doesn't need to know *how* parsing works internally. |
| `prereq_parser.py` | Just the English-sentence-to-structured-data logic (regex parsing of "Prerequisite: ..." text). | Parsing free text is its own tricky problem (see Problems 1–5 above). Keeping it in its own file meant we could test and fix parsing bugs without touching any database code. |
| `sanity_checks.sql` | Three plain SQL queries anyone (even without Python) can run to double-check the loaded data looks right. | This is meant to be handed to a human reviewer, or run with the standard `psql` tool — it shouldn't require reading Python. |
| `run_sanity_checks.py` | A tiny convenience script that runs `sanity_checks.sql` for people who don't have `psql` set up (like on this machine). | Purely a convenience wrapper — not "real" logic, so it's kept separate and disposable. |

## 6. The end result

Running `load_catalog.py` now loads, every time you run it (safe to re-run):

- 3 colleges, 19 departments, 37 subjects, **1,012 courses**
- 10 course groups (elective pools) with 1,091 courses in them
- 80 cross-listing relationships
- 2 academic programs (Aerospace BS + Minor), 9 requirement sets, 84 requirement tree nodes
- **1,897 prerequisite/corequisite rules**, parsed from real course descriptions, with zero self-loops and zero impossible (prerequisite) cycles

All three sanity-check queries were run and checked by hand against the
original catalog text — see `sanity_checks.sql` for the queries and
`docs/PHASES.md` (Phase 1.3) for the full checklist and results.

