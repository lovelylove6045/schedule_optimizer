"""Generates the `terms` table (sequential Fall/Spring/Summer academic terms).

Every other loader table in this project comes from a real JSON export in
`schedule_optimizer_db/` -- this one doesn't, because no source anywhere
(schedule_optimizer_db/, catalog_scraper/, or the design doc) lists real
academic terms. Phase 3's optimizer and every later phase need real `terms`
rows to attach `planning_scenarios.start_term_id` etc. to, so this generates
a reasonable calendar (Fall 2026 through Summer 2038, 36 terms) instead.

Safe to re-run: only inserts term_codes that don't already exist.

Run from backend/:

    cd backend
    uv run python ../db/seed_terms.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal  # noqa: E402
from app.models.term import Term  # noqa: E402

START_YEAR = 2026
TERM_COUNT = 36
TERM_CYCLE = (("FALL", 0), ("SPRING", 1), ("SUMMER", 1))
TERM_DATE_RANGES = {
    "FALL": ((8, 25), (12, 15)),
    "SPRING": ((1, 10), (5, 5)),
    "SUMMER": ((5, 20), (8, 10)),
}


def build_term_rows() -> list[dict]:
    """Build TERM_COUNT sequential Fall/Spring/Summer term rows starting at START_YEAR."""
    rows = []
    for i in range(TERM_COUNT):
        term_type, year_offset = TERM_CYCLE[i % len(TERM_CYCLE)]
        cycle_index = i // len(TERM_CYCLE)
        year = START_YEAR + cycle_index + year_offset
        rows.append(_build_term_row(term_type, year, sequence_index=i + 1))
    return rows


def _build_term_row(term_type: str, year: int, sequence_index: int) -> dict:
    """Build one term row dict for the given term type, calendar year, and sequence index."""
    start_month_day, end_month_day = TERM_DATE_RANGES[term_type]
    return {
        "term_code": f"{term_type}{year}",
        "academic_year": year,
        "term_type": term_type,
        "sequence_index": sequence_index,
        "start_date": date(year, *start_month_day),
        "end_date": date(year, *end_month_day),
    }


def main() -> None:
    """Insert every generated term row whose term_code doesn't already exist in `terms`."""
    rows = build_term_rows()
    session = SessionLocal()
    try:
        existing_codes = {code for (code,) in session.query(Term.term_code).all()}
        new_rows = [row for row in rows if row["term_code"] not in existing_codes]
        for row in new_rows:
            session.add(Term(**row))
        session.commit()
        print(f"Inserted {len(new_rows)} new term(s); {len(rows) - len(new_rows)} already existed.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
