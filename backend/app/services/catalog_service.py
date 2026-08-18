"""Read-only lookups over the catalog: programs, courses, and the
prerequisite/corequisite tree (`course_rule_nodes`) attached to a course."""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.academic_program import AcademicProgram
from app.models.college import College
from app.models.course import Course
from app.models.course_group import CourseGroup
from app.models.course_group_member import CourseGroupMember
from app.models.course_rule_node import CourseRuleNode
from app.models.department import Department
from app.models.program_relationship import ProgramRelationship
from app.models.subject import Subject
from app.models.term import Term
from app.schemas.college import CollegeOut
from app.schemas.course import CourseGroupMembersOut, CourseGroupOut, CourseOut
from app.schemas.prerequisite import PrerequisiteNodeOut
from app.schemas.program import ProgramOut
from app.services.common import course_out, load_courses_by_id

MAX_COURSE_SEARCH_RESULTS = 50


def list_colleges(db: Session) -> list[CollegeOut]:
    """Return every college/school, alphabetically by name -- the first choice a
    client asks for so the program picker can be narrowed to one school."""
    rows = db.query(College).order_by(College.college_name).all()
    return [CollegeOut.model_validate(row) for row in rows]


def list_programs(db: Session) -> list[ProgramOut]:
    """Return every academic program, alphabetically by name, each already joined
    to its department and (via `departments.college_id`) its college, so a client
    can filter the catalog by school without a second request. Outer-joined
    because `departments.college_id` is nullable."""
    rows = (
        db.query(AcademicProgram, Department, College)
        .outerjoin(Department, Department.department_id == AcademicProgram.department_id)
        .outerjoin(College, College.college_id == Department.college_id)
        .order_by(AcademicProgram.program_name)
        .all()
    )
    parent_ids = _compatible_parent_ids(db)
    return [
        _program_out(program, department, college, parent_ids.get(program.academic_program_id, []))
        for program, department, college in rows
    ]


def _compatible_parent_ids(db: Session) -> dict[int, list[int]]:
    """Return HAS_EMPHASIS parent program ids keyed by child emphasis id."""
    rows = (
        db.query(ProgramRelationship.child_program_id, ProgramRelationship.parent_program_id)
        .filter(ProgramRelationship.relationship_type == "HAS_EMPHASIS")
        .all()
    )
    parents: dict[int, list[int]] = {}
    for child_id, parent_id in rows:
        parents.setdefault(child_id, []).append(parent_id)
    return parents


def _program_out(
    program: AcademicProgram,
    department: Department | None,
    college: College | None,
    compatible_parent_program_ids: list[int],
) -> ProgramOut:
    """Convert one joined (program, department, college) row into a `ProgramOut`."""
    return ProgramOut(
        academic_program_id=program.academic_program_id,
        department_id=program.department_id,
        program_code=program.program_code,
        program_name=program.program_name,
        program_type=program.program_type,
        total_credit_hours=(
            float(program.total_credit_hours) if program.total_credit_hours is not None else None
        ),
        is_active=program.is_active,
        department_code=department.department_code if department else None,
        department_name=department.department_name if department else None,
        college_id=college.college_id if college else None,
        college_code=college.college_code if college else None,
        college_name=college.college_name if college else None,
        compatible_parent_program_ids=compatible_parent_program_ids,
    )


def list_terms(db: Session) -> list[Term]:
    """Return every term in chronological order, for scenario-creation clients to
    pick a `start_term_id`/`target_graduation_term_id` from."""
    return db.query(Term).order_by(Term.sequence_index.asc()).all()


def get_program(db: Session, program_id: int) -> AcademicProgram | None:
    """Look up one academic program by primary key, or `None` if it doesn't exist."""
    return db.get(AcademicProgram, program_id)


def get_course(db: Session, course_id: int) -> Course | None:
    """Look up one course by primary key, or `None` if it doesn't exist."""
    return db.get(Course, course_id)


def search_courses(
    db: Session, query: str, college_id: int | None = None, department_id: int | None = None
) -> list[CourseOut]:
    """Return matching courses, optionally restricted to a college or department."""
    trimmed = query.strip()
    if not trimmed:
        return []
    like_pattern = f"%{trimmed}%"
    combined_code = func.concat(Subject.subject_code, " ", Course.course_number)
    rows = (
        db.query(Course, Subject.subject_code)
        .join(Subject, Subject.subject_id == Course.subject_id)
        .join(Department, Department.department_id == Subject.department_id)
        .filter(
            or_(
                Subject.subject_code.ilike(like_pattern),
                Course.course_number.ilike(like_pattern),
                Course.course_title.ilike(like_pattern),
                combined_code.ilike(like_pattern),
            )
        )
    )
    if college_id is not None:
        rows = rows.filter(Department.college_id == college_id)
    if department_id is not None:
        rows = rows.filter(Department.department_id == department_id)
    matches = rows.order_by(Subject.subject_code.asc(), Course.course_number.asc()).limit(MAX_COURSE_SEARCH_RESULTS).all()
    return [course_out(course, subject_code) for course, subject_code in matches]


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
