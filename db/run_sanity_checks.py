"""Convenience runner for sanity_checks.sql on machines without `psql` on PATH
(uses the same SQLAlchemy engine/config as the API and load_catalog.py).

    cd backend
    uv run python ../db/run_sanity_checks.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.database import engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

SQL_PATH = Path(__file__).resolve().parent / "sanity_checks.sql"


def split_statements(sql: str) -> list[tuple[str, str]]:
    """Split sanity_checks.sql into (title, statement) pairs using the
    "-- N. <title>" banner comments (titles may span multiple "--" lines)
    as section markers."""
    banner_re = re.compile(r"-- =+\n((?:--.*\n)+?)-- =+\n")
    sections = banner_re.split(sql)
    # sections[0] is the file header; then alternating (title-block, body) pairs.
    pairs = list(zip(sections[1::2], sections[2::2]))
    statements = []
    for title_block, body in pairs:
        title = " ".join(line.lstrip("-").strip() for line in title_block.splitlines())
        # Strip full-line SQL comments but keep the statement itself intact.
        cleaned = "\n".join(line for line in body.splitlines() if not line.strip().startswith("--"))
        statements.append((title, cleaned.strip().rstrip(";")))
    return statements


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    statements = split_statements(sql)
    with engine.connect() as conn:
        conn.execute(text("SET statement_timeout = 10000"))
        for title, statement in statements:
            print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
            result = conn.execute(text(statement))
            cols = list(result.keys())
            rows = result.fetchall()
            print(" | ".join(cols))
            for row in rows:
                print(" | ".join("" if v is None else str(v) for v in row))
            print(f"\n({len(rows)} rows)")


if __name__ == "__main__":
    main()
