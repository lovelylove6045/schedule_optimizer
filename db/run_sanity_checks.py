"""Runs db/sanity_checks.sql and prints each query's result, for people who
don't have `psql` set up locally (like this machine). Purely a convenience
wrapper around plain SQL -- see sanity_checks.sql for what each query means.

Run from backend/:

    cd backend
    uv run python ../db/run_sanity_checks.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import engine  # noqa: E402
from sqlalchemy import text  # noqa: E402

SQL_PATH = Path(__file__).resolve().parent / "sanity_checks.sql"

# Splits the file into (title, statement) pairs: each statement is preceded
# by one or more `-- ...` comment lines, the last of which starts with
# "Query N:".
_STATEMENT_RE = re.compile(
    r"((?:^--.*\n)+)((?:[^;]|\n)*?;)", re.MULTILINE
)


def parse_statements(sql_text: str) -> list[tuple[str, str]]:
    """Split the sanity-checks SQL file into (title, statement) pairs, one per query."""
    statements = []
    for comment_block, statement in _STATEMENT_RE.findall(sql_text):
        title_lines = [
            line.lstrip("- ").strip()
            for line in comment_block.strip().splitlines()
        ]
        title = " ".join(title_lines)
        statements.append((title, statement.strip()))
    return statements


def main() -> None:
    """Run every query in sanity_checks.sql against the configured database and print its results."""
    sql_text = SQL_PATH.read_text(encoding="utf-8")
    statements = parse_statements(sql_text)
    print(f"Found {len(statements)} queries in {SQL_PATH.name}.\n")
    with engine.connect() as conn:
        for title, statement in statements:
            _run_and_print_statement(conn, title, statement)


def _run_and_print_statement(conn, title: str, statement: str) -> None:
    """Execute one sanity-check query and print its title, column names, and up to 50 rows."""
    print("=" * 80)
    print(title)
    print("=" * 80)
    result = conn.execute(text(statement))
    rows = result.fetchall()
    if not rows:
        print("(0 rows)")
    else:
        print(list(result.keys()))
        for row in rows[:50]:
            print(tuple(row))
        if len(rows) > 50:
            print(f"... and {len(rows) - 50} more row(s)")
    print()


if __name__ == "__main__":
    main()
