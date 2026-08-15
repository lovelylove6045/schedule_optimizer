"""Full-catalog loader (see docs/PHASES.md Phase 1.3, db/SUMMARY.md).

Loads every file in schedule_optimizer_db/ verbatim into Postgres: the whole
catalog (2,120 courses, 147 academic programs, every requirement tree, and
every prerequisite/corequisite rule), with no scope filtering and no free-
text parsing. Every one of these JSON files is already shaped exactly like
its destination table (same column names, same ids), so this script is a
straight upsert -- see db/SUMMARY.md for why an earlier version of this
script instead derived prerequisites by regex-parsing catalog_scraper/
output/*.json, and why that turned out to be unnecessary.

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


def load_json(name: str) -> list[dict]:
    with open(SCHEDULE_DB_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def insert_tree(session, rows: list[dict], model, parent_key: str, id_key: str, cast: dict[str, type] | None = None) -> None:
    """Insert rows of a self-referencing tree (requirement_nodes,
    course_rule_nodes) parent-before-child, since a handful of rows in the
    source JSON list a child before its parent (see db/SUMMARY.md)."""
    by_parent: dict[int | None, list[dict]] = {}
    for row in rows:
        by_parent.setdefault(row.get(parent_key), []).append(row)

    def insert_children(parent_id: int | None) -> None:
        for row in by_parent.get(parent_id, []):
            data = dict(row)
            for field, to_type in (cast or {}).items():
                if data.get(field) is not None:
                    data[field] = to_type(data[field])
            session.merge(model(**data))
            session.flush()
            insert_children(row[id_key])

    insert_children(None)


def main() -> None:
    print("Loading schedule_optimizer_db/*.json (full catalog)...")
    colleges = load_json("colleges")
    departments = load_json("departments")
    subjects = load_json("subjects")
    courses = load_json("courses")
    course_groups = load_json("course_groups")
    course_group_courses = load_json("course_group_courses")
    course_relations = load_json("course_relations")
    requirement_sets = load_json("requirement_sets")
    requirement_nodes = load_json("requirement_nodes")
    program_requirement_sets = load_json("program_requirement_sets")
    academic_programs = load_json("academic_programs")
    academic_program_relationships = load_json("academic_program_relationships")
    course_rule_nodes = load_json("course_rule_nodes")

    session = SessionLocal()
    try:
        print("Upserting colleges/departments/subjects/courses...")
        for row in colleges:
            session.merge(College(**row))
        session.flush()
        for row in departments:
            session.merge(Department(**row))
        session.flush()
        for row in subjects:
            session.merge(Subject(**row))
        session.flush()
        for row in courses:
            data = dict(row)
            data["credit_hours"] = float(data["credit_hours"])
            session.merge(Course(**data))
        session.flush()

        print("Upserting course groups/members/relations...")
        for row in course_groups:
            session.merge(CourseGroup(**row))
        session.flush()
        for row in course_group_courses:
            session.merge(CourseGroupMember(**row))
        session.flush()
        for row in course_relations:
            data = dict(row)
            if data.get("maximum_combined_credits") is not None:
                data["maximum_combined_credits"] = float(data["maximum_combined_credits"])
            session.merge(CourseRelation(**data))
        session.flush()

        print("Upserting academic programs and program relationships...")
        for row in academic_programs:
            data = dict(row)
            if data.get("total_credit_hours") is not None:
                data["total_credit_hours"] = float(data["total_credit_hours"])
            session.merge(AcademicProgram(**data))
        session.flush()
        for row in academic_program_relationships:
            session.merge(ProgramRelationship(**row))
        session.flush()

        print("Upserting requirement sets and program-requirement links...")
        for row in requirement_sets:
            session.merge(RequirementSet(**row))
        session.flush()
        for row in program_requirement_sets:
            session.merge(ProgramRequirementSet(**row))
        session.flush()

        print("Upserting requirement_nodes (parent-before-child)...")
        insert_tree(
            session,
            requirement_nodes,
            RequirementNode,
            parent_key="parent_requirement_node_id",
            id_key="requirement_node_id",
            cast={"required_credit_hours": float},
        )
        session.flush()

        print("Upserting course_rule_nodes (parent-before-child)...")
        insert_tree(
            session,
            course_rule_nodes,
            CourseRuleNode,
            parent_key="parent_rule_node_id",
            id_key="course_rule_node_id",
            cast={"minimum_total_credits": float},
        )
        session.flush()

        session.commit()
        print(
            "Done. Loaded "
            f"{len(colleges)} colleges, {len(departments)} departments, "
            f"{len(subjects)} subjects, {len(courses)} courses, "
            f"{len(course_groups)} course groups, {len(course_group_courses)} course-group members, "
            f"{len(course_relations)} course relations, {len(academic_programs)} academic programs, "
            f"{len(academic_program_relationships)} program relationships, "
            f"{len(requirement_sets)} requirement sets, {len(program_requirement_sets)} program-requirement links, "
            f"{len(requirement_nodes)} requirement nodes, {len(course_rule_nodes)} course_rule_nodes."
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
