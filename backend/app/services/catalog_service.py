"""Read-only lookups over the catalog: programs, courses, and the
prerequisite/corequisite tree (`course_rule_nodes`) attached to a course."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.academic_program import AcademicProgram
from app.models.course import Course
from app.models.course_group import CourseGroup
from app.models.course_group_member import CourseGroupMember
from app.models.course_rule_node import CourseRuleNode
from app.schemas.course import CourseGroupMembersOut, CourseGroupOut, CourseOut
from app.schemas.prerequisite import PrerequisiteNodeOut
from app.services.common import load_courses_by_id


def list_programs(db: Session) -> list[AcademicProgram]:
    """Return every academic program, alphabetically by name."""
    return db.query(AcademicProgram).order_by(AcademicProgram.program_name).all()


def get_program(db: Session, program_id: int) -> AcademicProgram | None:
    """Look up one academic program by primary key, or `None` if it doesn't exist."""
    return db.get(AcademicProgram, program_id)


def get_course(db: Session, course_id: int) -> Course | None:
    """Look up one course by primary key, or `None` if it doesn't exist."""
    return db.get(Course, course_id)


def get_prerequisite_tree(db: Session, course_id: int) -> list[PrerequisiteNodeOut]:
    """Every `course_rule_nodes` row targeting this course, resolved into a
    nested tree of root nodes (`parent_rule_node_id IS NULL`). A course
    typically has more than one root -- e.g. one PREREQUISITE tree and one
    separate COREQUISITE tree -- so this returns a list, not a single tree."""
    rows = (
        db.query(CourseRuleNode)
        .filter(CourseRuleNode.target_course_id == course_id)
        .order_by(CourseRuleNode.course_rule_node_id.asc())
        .all()
    )
    if not rows:
        return []
    courses_by_id = load_courses_by_id(db, _required_course_ids(rows))
    children_by_parent = _index_rule_nodes_by_parent(rows)
    return [
        _build_prerequisite_node(row, courses_by_id, children_by_parent)
        for row in children_by_parent.get(None, [])
    ]


def _required_course_ids(rows: list[CourseRuleNode]) -> set[int]:
    """Collect the distinct `required_course_id`s referenced by a list of rule nodes."""
    return {row.required_course_id for row in rows if row.required_course_id}


def _index_rule_nodes_by_parent(rows: list[CourseRuleNode]) -> dict[int | None, list[CourseRuleNode]]:
    """Group `course_rule_nodes` rows by `parent_rule_node_id` for O(1) child lookups while building the tree."""
    children_by_parent: dict[int | None, list[CourseRuleNode]] = {}
    for row in rows:
        children_by_parent.setdefault(row.parent_rule_node_id, []).append(row)
    return children_by_parent


def _build_prerequisite_node(
    node: CourseRuleNode,
    courses_by_id: dict[int, CourseOut],
    children_by_parent: dict[int | None, list[CourseRuleNode]],
) -> PrerequisiteNodeOut:
    """Recursively convert one `course_rule_nodes` row and its descendants into a `PrerequisiteNodeOut`."""
    return PrerequisiteNodeOut(
        course_rule_node_id=node.course_rule_node_id,
        requisite_type=node.requisite_type,
        node_type=node.node_type,
        rule_operator=node.rule_operator,
        required_course=courses_by_id.get(node.required_course_id) if node.required_course_id else None,
        required_subject_id=node.required_subject_id,
        required_academic_program_id=node.required_academic_program_id,
        required_count=node.required_count,
        minimum_grade=node.minimum_grade,
        minimum_total_credits=(
            float(node.minimum_total_credits) if node.minimum_total_credits is not None else None
        ),
        minimum_course_level=node.minimum_course_level,
        minimum_standing=node.minimum_standing,
        text_value=node.text_value,
        source_text=node.source_text,
        children=[
            _build_prerequisite_node(child, courses_by_id, children_by_parent)
            for child in children_by_parent.get(node.course_rule_node_id, [])
        ],
    )


def get_course_group_members(db: Session, course_group_id: int) -> CourseGroupMembersOut | None:
    """Return a course group's metadata plus its member courses, ordered by subject and course number."""
    group = db.get(CourseGroup, course_group_id)
    if group is None:
        return None
    member_rows = db.query(CourseGroupMember).filter(CourseGroupMember.course_group_id == course_group_id).all()
    courses_by_id = load_courses_by_id(db, {row.course_id for row in member_rows})
    courses = sorted(courses_by_id.values(), key=lambda c: (c.subject_code, c.course_number))
    return CourseGroupMembersOut(course_group=CourseGroupOut.model_validate(group), courses=courses)
