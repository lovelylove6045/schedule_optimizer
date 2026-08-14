"""Narrow-scope catalog loader for Phase 1.3 (see docs/PHASES.md).

Loads exactly the data needed for the Aerospace Engineering BS major plus the
Aerospace Engineering Minor: both programs' requirement trees, every course
reachable from those trees (directly, or via course_groups), and the
prerequisite/corequisite closure of those courses. Prerequisites aren't
present as structured data anywhere in schedule_optimizer_db/, so they're
parsed out of catalog_scraper/output/*.json course descriptions on the fly
(see prereq_parser.py) — best effort, not a full grammar.

Safe to re-run: every table is keyed by its real primary key from the source
JSON and loaded with session.merge() (upsert), except course_rule_nodes,
which are derived data with no natural key, so they're deleted and
regenerated for every course touched by this run.

Run from backend/ so it uses the same dependencies as the API:

    cd backend
    uv run python ../db/load_catalog.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
SCHEDULE_DB_DIR = REPO_ROOT / "schedule_optimizer_db"
SCRAPER_DIR = REPO_ROOT / "catalog_scraper" / "output"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import SessionLocal  # noqa: E402
from app.models.academic_program import AcademicProgram  # noqa: E402
from app.models.college import College  # noqa: E402
from app.models.course import Course  # noqa: E402
from app.models.course_group import CourseGroup  # noqa: E402
from app.models.course_group_member import CourseGroupMember  # noqa: E402
from app.models.course_relation import CourseRelation  # noqa: E402
from app.models.course_rule_node import CourseRuleNode  # noqa: E402
from app.models.department import Department  # noqa: E402
from app.models.program_requirement_set import ProgramRequirementSet  # noqa: E402
from app.models.requirement_node import RequirementNode  # noqa: E402
from app.models.requirement_set import RequirementSet  # noqa: E402
from app.models.subject import Subject  # noqa: E402

from prereq_parser import RequisiteParser, RuleNode  # noqa: E402

PRIMARY_PROGRAM_CODE = "AERO_BS_2026"
MINOR_PROGRAM_CODE = "AERO_MINOR_2026"

# Safety valve: stop expanding the prerequisite closure once it has pulled in
# this many courses *beyond* the initial (directly-required) scope. Free-text
# parsing could in principle chain-react through most of the catalog; this
# caps that without limiting the (much larger) directly-required gen-ed pool.
MAX_CLOSURE_GROWTH = 300

_COURSE_NUMBER_RE = re.compile(r"(\d{3,4}[A-Za-z]?)")

# Roughly 2-3% of catalog_scraper descriptions end with one or more Missouri
# reverse-transfer (MOTR) equivalency notes, e.g. "... MATH 1120 - MOTR MATH
# 130: Pre-Calculus Algebra". These restate the course's own code right
# before "MOTR", which the prerequisite parser would otherwise misread as a
# (self-referential!) course mention. Truncate the description there.
_MOTR_SUFFIX_RE = re.compile(
    r"\b[A-Z][A-Za-z&]{1,10}(?:\s+[A-Z][A-Za-z&]{1,10}){0,2}\s+\d{3,4}[A-Za-z]?\s*-\s*MOTR\b"
)


def _strip_motr_suffix(description: str) -> str:
    m = _MOTR_SUFFIX_RE.search(description)
    return description[: m.start()].rstrip() if m else description


def load_json(name: str) -> list[dict]:
    with open(SCHEDULE_DB_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def load_all_scraper_courses() -> list[dict]:
    records: list[dict] = []
    for path in sorted(SCRAPER_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            records.extend(json.load(f))
    return records


def build_description_index(scraper_records: list[dict]) -> dict[tuple[str, str], str]:
    """(SUBJECT_CODE, "1215") -> course description, from catalog_scraper output."""
    index: dict[tuple[str, str], str] = {}
    for rec in scraper_records:
        subject_code = rec["subject_code"].strip().upper()
        course_field = rec.get("course", "")
        rest = course_field[len(rec["subject_code"]) :]
        num_m = _COURSE_NUMBER_RE.search(rest)
        if not num_m:
            continue
        index[(subject_code, num_m.group(1).upper())] = _strip_motr_suffix(rec.get("description", "") or "")
    return index


def resolve_scope(
    academic_programs: list[dict],
    program_requirement_sets: list[dict],
    requirement_sets: list[dict],
    requirement_nodes: list[dict],
    course_groups: list[dict],
    course_group_courses: list[dict],
) -> dict:
    programs_by_code = {p["program_code"]: p for p in academic_programs}
    primary = programs_by_code[PRIMARY_PROGRAM_CODE]
    minor = programs_by_code[MINOR_PROGRAM_CODE]
    program_ids = {primary["academic_program_id"], minor["academic_program_id"]}

    requirement_set_ids = {
        prs["requirement_set_id"]
        for prs in program_requirement_sets
        if prs["academic_program_id"] in program_ids
    }
    scoped_requirement_sets = [rs for rs in requirement_sets if rs["requirement_set_id"] in requirement_set_ids]
    scoped_program_requirement_sets = [
        prs for prs in program_requirement_sets if prs["academic_program_id"] in program_ids
    ]
    scoped_requirement_nodes = [
        rn for rn in requirement_nodes if rn["requirement_set_id"] in requirement_set_ids
    ]

    course_group_ids = {rn["course_group_id"] for rn in scoped_requirement_nodes if rn.get("course_group_id")}
    scoped_course_groups = [cg for cg in course_groups if cg["course_group_id"] in course_group_ids]
    scoped_course_group_courses = [
        cgc for cgc in course_group_courses if cgc["course_group_id"] in course_group_ids
    ]

    initial_course_ids = {
        rn["required_course_id"] for rn in scoped_requirement_nodes if rn.get("required_course_id")
    }
    initial_course_ids |= {cgc["course_id"] for cgc in scoped_course_group_courses}

    return {
        "program_ids": program_ids,
        "programs": [p for p in academic_programs if p["academic_program_id"] in program_ids],
        "requirement_sets": scoped_requirement_sets,
        "program_requirement_sets": scoped_program_requirement_sets,
        "requirement_nodes": scoped_requirement_nodes,
        "course_groups": scoped_course_groups,
        "course_group_courses": scoped_course_group_courses,
        "initial_course_ids": initial_course_ids,
    }


def compute_prereq_closure(
    initial_course_ids: set[int],
    courses_by_id: dict[int, dict],
    subject_code_by_id: dict[int, str],
    parser: RequisiteParser,
    description_index: dict[tuple[str, str], str],
) -> tuple[set[int], dict[int, list[RuleNode]]]:
    final_course_ids: set[int] = set(initial_course_ids)
    rule_nodes_by_course: dict[int, list[RuleNode]] = {}
    queue = list(initial_course_ids)
    seen: set[int] = set()

    while queue:
        course_id = queue.pop()
        if course_id in seen:
            continue
        seen.add(course_id)

        course = courses_by_id.get(course_id)
        if not course:
            continue
        subject_code = subject_code_by_id.get(course["subject_id"], "").strip().upper()
        number = str(course["course_number"]).strip().upper()
        description = description_index.get((subject_code, number))
        if not description:
            continue

        nodes = parser.parse_description(description)
        if not nodes:
            continue
        _drop_self_references(nodes, course_id)
        rule_nodes_by_course[course_id] = nodes

        referenced = parser.referenced_course_ids(nodes)
        new_ids = referenced - final_course_ids
        if not new_ids:
            continue
        growth = len(final_course_ids) - len(initial_course_ids)
        if growth >= MAX_CLOSURE_GROWTH:
            print(
                f"  Warning: hit MAX_CLOSURE_GROWTH={MAX_CLOSURE_GROWTH}, "
                f"not expanding into {len(new_ids)} more course(s) referenced by course {course_id}."
            )
            continue
        final_course_ids |= new_ids
        queue.extend(new_ids)

    _drop_out_of_scope_references(rule_nodes_by_course, final_course_ids)
    return final_course_ids, rule_nodes_by_course


def _drop_self_references(nodes: list[RuleNode], course_id: int) -> None:
    """A course can never legitimately be its own prerequisite. This mostly
    guards against description-parsing quirks (e.g. a trailing crosswalk note
    that restates the course's own code) turning into a bogus self-loop,
    which would otherwise hang any recursive prerequisite-chain query."""

    def sanitize(node: RuleNode) -> None:
        if node.node_type == "COURSE" and node.required_course_id == course_id:
            node.node_type = "TEXT"
            node.text_value = node.source_text or "[self-referential mention dropped]"
            node.required_course_id = None
        for child in node.children:
            sanitize(child)

    for node in nodes:
        sanitize(node)


def _drop_out_of_scope_references(
    rule_nodes_by_course: dict[int, list[RuleNode]], final_course_ids: set[int]
) -> None:
    """Defensively downgrade any COURSE node whose target fell outside the
    closure (e.g. the MAX_CLOSURE_GROWTH safety valve tripped) into a TEXT
    node, so a capped closure can never produce a dangling foreign key."""

    def sanitize(node: RuleNode) -> None:
        if node.node_type == "COURSE" and node.required_course_id not in final_course_ids:
            node.node_type = "TEXT"
            node.text_value = node.source_text or f"[course id {node.required_course_id}, out of load scope]"
            node.required_course_id = None
        for child in node.children:
            sanitize(child)

    for nodes in rule_nodes_by_course.values():
        for node in nodes:
            sanitize(node)


def insert_rule_node(session, node: RuleNode, target_course_id: int, parent_id: int | None) -> None:
    row = CourseRuleNode(
        target_course_id=target_course_id,
        parent_rule_node_id=parent_id,
        requisite_type=node.requisite_type,
        node_type=node.node_type,
        rule_operator=node.rule_operator,
        required_course_id=node.required_course_id,
        minimum_grade=node.minimum_grade,
        minimum_standing=node.minimum_standing,
        text_value=node.text_value,
        source_text=node.source_text,
    )
    session.add(row)
    session.flush()
    for child in node.children:
        insert_rule_node(session, child, target_course_id, row.course_rule_node_id)


def main() -> None:
    print("Loading schedule_optimizer_db seed files...")
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

    courses_by_id = {c["course_id"]: c for c in courses}
    subjects_by_id = {s["subject_id"]: s for s in subjects}
    departments_by_id = {d["department_id"]: d for d in departments}
    subject_code_by_id = {s["subject_id"]: s["subject_code"] for s in subjects}

    course_lookup: dict[tuple[str, str], int] = {}
    for c in courses:
        subj = subjects_by_id.get(c["subject_id"])
        if not subj:
            continue
        key = (subj["subject_code"].strip().upper(), str(c["course_number"]).strip().upper())
        course_lookup[key] = c["course_id"]

    scope = resolve_scope(
        academic_programs,
        program_requirement_sets,
        requirement_sets,
        requirement_nodes,
        course_groups,
        course_group_courses,
    )
    print(
        f"Scope: {len(scope['requirement_sets'])} requirement sets, "
        f"{len(scope['requirement_nodes'])} requirement nodes, "
        f"{len(scope['course_groups'])} course groups, "
        f"{len(scope['initial_course_ids'])} directly-required courses."
    )

    print("Loading catalog_scraper descriptions for prerequisite parsing...")
    scraper_records = load_all_scraper_courses()
    description_index = build_description_index(scraper_records)
    subject_codes = [s["subject_code"] for s in subjects]
    parser = RequisiteParser(subject_codes, course_lookup)

    final_course_ids, rule_nodes_by_course = compute_prereq_closure(
        scope["initial_course_ids"], courses_by_id, subject_code_by_id, parser, description_index
    )
    print(
        f"Prerequisite closure: {len(final_course_ids)} total courses "
        f"({len(final_course_ids) - len(scope['initial_course_ids'])} pulled in via prerequisites), "
        f"parsed rule trees for {len(rule_nodes_by_course)} courses."
    )

    final_courses = [courses_by_id[cid] for cid in final_course_ids if cid in courses_by_id]
    needed_subject_ids = {c["subject_id"] for c in final_courses}
    needed_department_ids = {
        subjects_by_id[sid]["department_id"] for sid in needed_subject_ids if sid in subjects_by_id
    }
    needed_college_ids = {
        departments_by_id[did]["college_id"]
        for did in needed_department_ids
        if did in departments_by_id and departments_by_id[did].get("college_id")
    }

    scoped_colleges = [c for c in colleges if c["college_id"] in needed_college_ids]
    scoped_departments = [d for d in departments if d["department_id"] in needed_department_ids]
    scoped_subjects = [s for s in subjects if s["subject_id"] in needed_subject_ids]
    scoped_course_relations = [
        cr
        for cr in course_relations
        if cr["course_id"] in final_course_ids and cr["related_course_id"] in final_course_ids
    ]

    session = SessionLocal()
    try:
        print("Upserting colleges/departments/subjects/courses...")
        for row in scoped_colleges:
            session.merge(College(**row))
        session.flush()
        for row in scoped_departments:
            session.merge(Department(**row))
        session.flush()
        for row in scoped_subjects:
            session.merge(Subject(**row))
        session.flush()
        for row in final_courses:
            data = dict(row)
            data["credit_hours"] = float(data["credit_hours"])
            session.merge(Course(**data))
        session.flush()

        print("Upserting course groups/members/relations...")
        for row in scope["course_groups"]:
            session.merge(CourseGroup(**row))
        session.flush()
        for row in scope["course_group_courses"]:
            session.merge(CourseGroupMember(**row))
        session.flush()
        for row in scoped_course_relations:
            data = dict(row)
            if data.get("maximum_combined_credits") is not None:
                data["maximum_combined_credits"] = float(data["maximum_combined_credits"])
            session.merge(CourseRelation(**data))
        session.flush()

        print("Upserting academic programs and requirement trees...")
        for row in scope["programs"]:
            data = dict(row)
            if data.get("total_credit_hours") is not None:
                data["total_credit_hours"] = float(data["total_credit_hours"])
            session.merge(AcademicProgram(**data))
        session.flush()
        for row in scope["requirement_sets"]:
            session.merge(RequirementSet(**row))
        session.flush()
        for row in scope["program_requirement_sets"]:
            session.merge(ProgramRequirementSet(**row))
        session.flush()

        # requirement_nodes form a tree via parent_requirement_node_id; insert
        # parents before children so the self-referencing FK is always satisfiable.
        nodes_by_parent: dict[int | None, list[dict]] = {}
        for row in scope["requirement_nodes"]:
            nodes_by_parent.setdefault(row["parent_requirement_node_id"], []).append(row)

        def insert_requirement_nodes(parent_id: int | None) -> None:
            for row in nodes_by_parent.get(parent_id, []):
                data = dict(row)
                if data.get("required_credit_hours") is not None:
                    data["required_credit_hours"] = float(data["required_credit_hours"])
                session.merge(RequirementNode(**data))
                session.flush()
                insert_requirement_nodes(row["requirement_node_id"])

        insert_requirement_nodes(None)
        session.flush()

        print("Rebuilding course_rule_nodes from parsed prerequisites...")
        session.query(CourseRuleNode).filter(
            CourseRuleNode.target_course_id.in_(final_course_ids)
        ).delete(synchronize_session=False)
        session.flush()

        rule_node_count = 0

        def count_nodes(node: RuleNode) -> int:
            return 1 + sum(count_nodes(child) for child in node.children)

        for course_id, nodes in rule_nodes_by_course.items():
            for node in nodes:
                insert_rule_node(session, node, course_id, None)
                rule_node_count += count_nodes(node)

        session.commit()
        print(
            "Done. Loaded "
            f"{len(scoped_colleges)} colleges, {len(scoped_departments)} departments, "
            f"{len(scoped_subjects)} subjects, {len(final_courses)} courses, "
            f"{len(scope['course_groups'])} course groups, {len(scope['course_group_courses'])} course-group members, "
            f"{len(scoped_course_relations)} course relations, {len(scope['programs'])} academic programs, "
            f"{len(scope['requirement_sets'])} requirement sets, {len(scope['program_requirement_sets'])} program-requirement links, "
            f"{len(scope['requirement_nodes'])} requirement nodes, {rule_node_count} course_rule_nodes."
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
