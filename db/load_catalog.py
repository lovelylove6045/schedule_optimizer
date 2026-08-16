"""Full-catalog loader (see docs/PHASES.md Phase 1.3, db/SUMMARY.md).

Loads every file in schedule_optimizer_db/ verbatim into Postgres: the whole
catalog (2,120 courses, 147 academic programs, every requirement tree, and
every prerequisite/corequisite rule), with no scope filtering and no free-
text parsing. Every one of these JSON files is already shaped exactly like
its destination table (same column names, same ids), so this script is a
straight upsert -- see db/SUMMARY.md for why an earlier version of this
loader briefly derived prerequisites from unstructured data. The retained
catalog_scraper/ directory is historical/offline only and is never imported or
invoked here.

Safe to re-run: every table is keyed by its real primary key from the source
JSON and loaded with session.merge() (upsert).

Run from backend/ so it uses the same dependencies as the API:

    cd backend
    uv run python ../db/load_catalog.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
SCHEDULE_DB_DIR = REPO_ROOT / "schedule_optimizer_db"

sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal  # noqa: E402
from app.models.academic_program import AcademicProgram  # noqa: E402
from app.models.college import College  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.course_group import CourseGroup  # noqa: E402
from app.models.course_group_member import CourseGroupMember  # noqa: E402
from app.models.course_relation import CourseRelation  # noqa: E402
from app.models.course_rule_node import CourseRuleNode  # noqa: E402
from app.models.department import Department  # noqa: E402
from app.models.program_relationship import ProgramRelationship  # noqa: E402
from app.models.program_requirement_set import ProgramRequirementSet  # noqa: E402
from app.models.requirement_node import RequirementNode  # noqa: E402
from app.models.requirement_set import RequirementSet  # noqa: E402
from app.models.subject import Subject  # noqa: E402

# Every one of these (table, primary_key_column) pairs is loaded above with an
# explicit id from the source JSON (never through the ORM's own autoincrement),
# which leaves Postgres's identity sequence stuck at its initial value. Left
# unsynced, the *next* ordinary insert into one of these tables (an app feature,
# or even a test, creating a new row without specifying an id) collides with
# real catalog data instead of getting a fresh id.
SEQUENCE_TABLES = [
    ("colleges", "college_id"),
    ("departments", "department_id"),
    ("subjects", "subject_id"),
    ("courses", "course_id"),
    ("course_groups", "course_group_id"),
    ("course_group_courses", "course_group_course_id"),
    ("course_relations", "course_relation_id"),
    ("academic_programs", "academic_program_id"),
    ("academic_program_relationships", "academic_program_relationship_id"),
    ("requirement_sets", "requirement_set_id"),
    ("program_requirement_sets", "program_requirement_set_id"),
    ("requirement_nodes", "requirement_node_id"),
    ("course_rule_nodes", "course_rule_node_id"),
]

CATALOG_FILES = [
    "colleges",
    "departments",
    "subjects",
    "courses",
    "course_groups",
    "course_group_courses",
    "course_relations",
    "requirement_sets",
    "requirement_nodes",
    "program_requirement_sets",
    "academic_programs",
    "academic_program_relationships",
    "course_rule_nodes",
]


def load_json(name: str) -> list[dict]:
    """Read one `schedule_optimizer_db/<name>.json` file into a list of row dicts."""
    with open(SCHEDULE_DB_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def load_all_catalog_json() -> dict[str, list[dict]]:
    """Read every catalog JSON file this loader needs, keyed by table name."""
    return {name: load_json(name) for name in CATALOG_FILES}


def insert_tree(
    session, rows: list[dict], model, parent_key: str, id_key: str, cast: dict[str, type] | None = None
) -> None:
    """Insert rows of a self-referencing tree (requirement_nodes,
    course_rule_nodes) parent-before-child, since a handful of rows in the
    source JSON list a child before its parent (see db/SUMMARY.md)."""
    by_parent: dict[int | None, list[dict]] = {}
    for row in rows:
        by_parent.setdefault(row.get(parent_key), []).append(row)
    _insert_children(session, by_parent, model, id_key, cast or {}, parent_id=None)


def _insert_children(
    session,
    by_parent: dict[int | None, list[dict]],
    model,
    id_key: str,
    cast: dict[str, type],
    parent_id: int | None,
) -> None:
    """Recursively insert every row under `parent_id`, then its descendants, depth-first."""
    for row in by_parent.get(parent_id, []):
        data = dict(row)
        for field, to_type in cast.items():
            if data.get(field) is not None:
                data[field] = to_type(data[field])
        session.merge(model(**data))
        session.flush()
        _insert_children(session, by_parent, model, id_key, cast, parent_id=row[id_key])


def _upsert_reference_data(session, data: dict[str, list[dict]]) -> None:
    """Upsert colleges, departments, subjects, and courses, in FK-safe order."""
    print("Upserting colleges/departments/subjects/courses...")
    for row in data["colleges"]:
        session.merge(College(**row))
    session.flush()
    for row in data["departments"]:
        session.merge(Department(**row))
    session.flush()
    for row in data["subjects"]:
        session.merge(Subject(**row))
    session.flush()
    for row in data["courses"]:
        course_data = dict(row)
        course_data["credit_hours"] = float(course_data["credit_hours"])
        session.merge(Course(**course_data))
    session.flush()


def _upsert_course_groups_and_relations(session, data: dict[str, list[dict]]) -> None:
    """Upsert course groups, their memberships, and course-to-course relations."""
    print("Upserting course groups/members/relations...")
    for row in data["course_groups"]:
        session.merge(CourseGroup(**row))
    session.flush()
    for row in data["course_group_courses"]:
        session.merge(CourseGroupMember(**row))
    session.flush()
    for row in data["course_relations"]:
        relation_data = dict(row)
        if relation_data.get("maximum_combined_credits") is not None:
            relation_data["maximum_combined_credits"] = float(relation_data["maximum_combined_credits"])
        session.merge(CourseRelation(**relation_data))
    session.flush()


def _upsert_programs_and_relationships(session, data: dict[str, list[dict]]) -> None:
    """Upsert academic programs and their parent/child program relationships."""
    print("Upserting academic programs and program relationships...")
    for row in data["academic_programs"]:
        program_data = dict(row)
        if program_data.get("total_credit_hours") is not None:
            program_data["total_credit_hours"] = float(program_data["total_credit_hours"])
        session.merge(AcademicProgram(**program_data))
    session.flush()
    for row in data["academic_program_relationships"]:
        session.merge(ProgramRelationship(**row))
    session.flush()


def _upsert_requirement_sets_and_links(session, data: dict[str, list[dict]]) -> None:
    """Upsert requirement sets and the program-to-requirement-set links."""
    print("Upserting requirement sets and program-requirement links...")
    for row in data["requirement_sets"]:
        session.merge(RequirementSet(**row))
    session.flush()
    for row in data["program_requirement_sets"]:
        session.merge(ProgramRequirementSet(**row))
    session.flush()


def _upsert_requirement_and_rule_trees(session, data: dict[str, list[dict]]) -> None:
    """Upsert the two self-referencing tree tables, parent-before-child."""
    print("Upserting requirement_nodes (parent-before-child)...")
    insert_tree(
        session,
        data["requirement_nodes"],
        RequirementNode,
        parent_key="parent_requirement_node_id",
        id_key="requirement_node_id",
        cast={"required_credit_hours": float},
    )
    session.flush()
    print("Upserting course_rule_nodes (parent-before-child)...")
    insert_tree(
        session,
        data["course_rule_nodes"],
        CourseRuleNode,
        parent_key="parent_rule_node_id",
        id_key="course_rule_node_id",
        cast={"minimum_total_credits": float},
    )
    session.flush()


def _sync_sequences(session) -> None:
    """Advance every explicit-id table's identity sequence past its current max id.

    Run once after the explicit-id upserts commit, so a later ordinary insert
    (autoincrementing, no explicit id) gets a fresh one instead of colliding
    with catalog data (see SEQUENCE_TABLES)."""
    print("Syncing identity sequences for explicit-id tables...")
    for table, column in SEQUENCE_TABLES:
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
                f"COALESCE((SELECT MAX({column}) FROM {table}), 1))"
            )
        )
    session.commit()


def _print_load_summary(data: dict[str, list[dict]]) -> None:
    """Print a one-line row-count summary of everything just loaded."""
    print(
        "Done. Loaded "
        f"{len(data['colleges'])} colleges, {len(data['departments'])} departments, "
        f"{len(data['subjects'])} subjects, {len(data['courses'])} courses, "
        f"{len(data['course_groups'])} course groups, "
        f"{len(data['course_group_courses'])} course-group members, "
        f"{len(data['course_relations'])} course relations, "
        f"{len(data['academic_programs'])} academic programs, "
        f"{len(data['academic_program_relationships'])} program relationships, "
        f"{len(data['requirement_sets'])} requirement sets, "
        f"{len(data['program_requirement_sets'])} program-requirement links, "
        f"{len(data['requirement_nodes'])} requirement nodes, "
        f"{len(data['course_rule_nodes'])} course_rule_nodes."
    )


def main() -> None:
    """Load all `schedule_optimizer_db/*.json` files into Postgres, verbatim, in dependency order."""
    print("Loading schedule_optimizer_db/*.json (full catalog)...")
    data = load_all_catalog_json()
    session = SessionLocal()
    try:
        _upsert_reference_data(session, data)
        _upsert_course_groups_and_relations(session, data)
        _upsert_programs_and_relationships(session, data)
        _upsert_requirement_sets_and_links(session, data)
        _upsert_requirement_and_rule_trees(session, data)
        session.commit()
        _sync_sequences(session)
        _print_load_summary(data)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
