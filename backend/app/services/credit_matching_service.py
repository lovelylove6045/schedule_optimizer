"""Marks which nodes of an already-flattened requirement tree
(`requirement_service.flatten_requirement_tree`) are satisfied by a given
student's completed coursework (`student_credits`)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_group_member import CourseGroupMember
from app.models.course_relation import CourseRelation
from app.models.enums import CourseRelationType
from app.models.student_credit import StudentCredit
from app.schemas.requirement import RequirementNodeOut, RequirementSetOut

# student_credits.status isn't a DB-level enum (see backend/app/models/enums.py
# docstring) -- "COMPLETED" is the only status this service treats as counting
# towards a requirement; "IN_PROGRESS"/"PLANNED" rows, if present, don't.
COMPLETED_STATUS = "COMPLETED"

# Letter grades only -- pass/fail, transfer, and other non-letter grades are
# handled separately in _meets_minimum_grade below.
_GRADE_POINTS = {
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D+": 1.3,
    "D": 1.0,
    "D-": 0.7,
    "F": 0.0,
}


# Sentinel "grade" for a course that isn't actually completed yet but should be
# treated as satisfying the requirement anyway (e.g. a course a degree plan
# assigns to a future term) -- not a real letter grade, so
# `_meets_minimum_grade` always accepts it, matching how transfer/pass-fail
# grades are already treated.
PLANNED_GRADE_SENTINEL = "PLANNED"


@dataclass(frozen=True)
class GroupMember:
    """Describe the catalog attributes needed to evaluate one group member."""

    credit_hours: float
    subject_id: int
    course_level: int


def match_completed_courses(
    db: Session,
    student_id: int,
    requirement_set: RequirementSetOut,
    extra_completed_course_ids: set[int] | None = None,
) -> RequirementSetOut:
    """Return a new `RequirementSetOut` with every node's `is_satisfied`
    filled in, treating both the student's actual `student_credits` and any
    `extra_completed_course_ids` (e.g. a degree plan's newly-assigned
    courses) as completed. Leave the input untouched (Pydantic models here
    are treated as immutable data, not mutated in place)."""
    best_grade_by_course = _best_completed_grade_by_course(db, student_id)
    for course_id in extra_completed_course_ids or set():
        best_grade_by_course.setdefault(course_id, PLANNED_GRADE_SENTINEL)
    best_grade_by_course = _expand_equivalent_grades(db, best_grade_by_course)
    course_group_ids = _collect_course_group_ids(requirement_set.nodes)
    members_by_group = _load_course_group_members(db, course_group_ids)
    new_nodes = [_evaluate_node(node, best_grade_by_course, members_by_group) for node in requirement_set.nodes]
    return requirement_set.model_copy(update={"nodes": new_nodes})


def _best_completed_grade_by_course(db: Session, student_id: int) -> dict[int, str | None]:
    """Return each completed course's best-earned grade for this student,
    keyed by course_id (a course can be completed more than once, e.g. a retake)."""
    credits = (
        db.query(StudentCredit)
        .filter(StudentCredit.student_id == student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    best: dict[int, str | None] = {}
    for credit in credits:
        if credit.course_id is None:
            continue
        if credit.course_id not in best or _grade_rank(credit.grade) > _grade_rank(best[credit.course_id]):
            best[credit.course_id] = credit.grade
    return best


def _expand_equivalent_grades(
    db: Session, best_grade_by_course: dict[int, str | None]
) -> dict[int, str | None]:
    """Apply directed cross-listed/equivalent relations to completed-course matching."""
    if not best_grade_by_course:
        return best_grade_by_course
    course_ids = set(best_grade_by_course)
    rows = (
        db.query(CourseRelation)
        .filter(
            CourseRelation.relation_type.in_(
                (CourseRelationType.CROSS_LISTED, CourseRelationType.EQUIVALENT)
            ),
            (CourseRelation.course_id.in_(course_ids) | CourseRelation.related_course_id.in_(course_ids)),
        )
        .all()
    )
    expanded = dict(best_grade_by_course)
    for relation in rows:
        if relation.course_id in best_grade_by_course:
            expanded.setdefault(relation.related_course_id, best_grade_by_course[relation.course_id])
        if relation.is_bidirectional and relation.related_course_id in best_grade_by_course:
            expanded.setdefault(relation.course_id, best_grade_by_course[relation.related_course_id])
    return expanded


def _grade_rank(grade: str | None) -> float:
    """Map a letter grade to a comparable numeric rank; missing/unknown grades rank lowest."""
    if not grade:
        return -1.0
    return _GRADE_POINTS.get(grade.upper(), 0.0)


def _meets_minimum_grade(earned_grade: str | None, minimum_grade: str | None) -> bool:
    """Return whether an earned grade satisfies a minimum-grade requirement.
    Non-letter grades (P, CR, S, transfer credit, etc.) always satisfy the
    requirement, since schools generally accept them regardless of the
    course's in-house minimum-grade policy."""
    if not minimum_grade:
        return True
    if not earned_grade:
        return False
    earned_points = _GRADE_POINTS.get(earned_grade.upper())
    minimum_points = _GRADE_POINTS.get(minimum_grade.upper())
    if earned_points is None or minimum_points is None:
        return True
    return earned_points >= minimum_points


def _collect_course_group_ids(nodes: list[RequirementNodeOut]) -> set[int]:
    """Recursively collect every `course_group_id` referenced anywhere in a requirement (sub)tree."""
    ids: set[int] = set()
    for node in nodes:
        if node.course_group is not None:
            ids.add(node.course_group.course_group_id)
        ids |= _collect_course_group_ids(node.children)
    return ids


def _load_course_group_members(
    db: Session, course_group_ids: set[int]
) -> dict[int, dict[int, GroupMember]]:
    """Fetch each course group's member courses as {course_id: credit_hours}, keyed by
    course_group_id. Credit hours come along because a COURSE_GROUP node's threshold is
    usually expressed in credit hours rather than a course count (see `_is_group_satisfied`)."""
    if not course_group_ids:
        return {}
    rows = (
        db.query(
            CourseGroupMember.course_group_id,
            CourseGroupMember.course_id,
            Course.credit_hours,
            Course.subject_id,
            Course.course_level,
        )
        .join(Course, Course.course_id == CourseGroupMember.course_id)
        .filter(CourseGroupMember.course_group_id.in_(course_group_ids))
        .all()
    )
    members: dict[int, dict[int, GroupMember]] = {cgid: {} for cgid in course_group_ids}
    for group_id, course_id, credit_hours, subject_id, course_level in rows:
        members[group_id][course_id] = GroupMember(float(credit_hours), subject_id, course_level)
    return members


def _evaluate_node(
    node: RequirementNodeOut,
    best_grade_by_course: dict[int, str | None],
    members_by_group: dict[int, dict[int, GroupMember]],
) -> RequirementNodeOut:
    """Recursively evaluate a node's descendants first, then return a copy
    of the node with its own `is_satisfied` filled in."""
    children = [_evaluate_node(child, best_grade_by_course, members_by_group) for child in node.children]
    satisfied = _is_node_satisfied(node, children, best_grade_by_course, members_by_group)
    return node.model_copy(update={"children": children, "is_satisfied": satisfied})


def _is_node_satisfied(
    node: RequirementNodeOut,
    children: list[RequirementNodeOut],
    best_grade_by_course: dict[int, str | None],
    members_by_group: dict[int, dict[int, GroupMember]],
) -> bool:
    """Determine whether one node is satisfied, given its already-evaluated children."""
    if node.node_type == "COURSE" and node.required_course is not None:
        course_id = node.required_course.course_id
        meets_level = (
            node.minimum_course_level is None
            or node.required_course.course_level >= node.minimum_course_level
        )
        return meets_level and course_id in best_grade_by_course and _meets_minimum_grade(
            best_grade_by_course[course_id], node.minimum_grade
        )
    if node.node_type == "COURSE_GROUP" and node.course_group is not None:
        return _is_group_satisfied(node, best_grade_by_course, members_by_group)
    if node.node_type == "CREDIT_REQUIREMENT":
        # No course/course_group is attached (see db/SUMMARY.md §4), so this
        # can't be auto-verified against student_credits; a human must sign off.
        return False
    if children:
        return _aggregate(node, children)
    # A childless, non-leaf node shouldn't occur in real data; don't claim it's satisfied.
    return False


def _is_group_satisfied(
    node: RequirementNodeOut,
    best_grade_by_course: dict[int, str | None],
    members_by_group: dict[int, dict[int, GroupMember]],
) -> bool:
    """Determine whether a COURSE_GROUP leaf is satisfied by completed coursework.
    A group carries its threshold in `required_credit_hours` (240 of the 252 real
    COURSE_GROUP nodes do -- e.g. "Gen Ed HASS, 15 credit hours"), in
    `required_count`, or in both; whichever are present must all hold. This used to
    return true as soon as *any* single member was completed, which quietly treated
    a 15-credit elective block as satisfied by one 3-credit course."""
    members = members_by_group.get(node.course_group.course_group_id, {})
    satisfying = [
        course_id
        for course_id, member in members.items()
        if course_id in best_grade_by_course
        and (node.minimum_course_level is None or member.course_level >= node.minimum_course_level)
        and _meets_minimum_grade(best_grade_by_course[course_id], node.minimum_grade)
    ]
    if node.required_count is not None and len(satisfying) < node.required_count:
        return False
    if node.required_credit_hours is not None:
        earned = sum(members[course_id].credit_hours for course_id in satisfying)
        if earned < node.required_credit_hours:
            return False
    if node.minimum_distinct_subjects is not None:
        distinct_subjects = {members[course_id].subject_id for course_id in satisfying}
        if len(distinct_subjects) < node.minimum_distinct_subjects:
            return False
    if node.required_credit_hours is not None:
        return True
    # Neither threshold given: a single member completed is all this group asks for.
    return len(satisfying) >= 1


def _aggregate(node: RequirementNodeOut, children: list[RequirementNodeOut]) -> bool:
    """Combine already-evaluated children's satisfaction per the node's operator (defaults to ALL)."""
    satisfied_children = [c for c in children if c.is_satisfied]
    if node.node_operator == "ANY":
        return len(satisfied_children) >= 1
    if node.node_operator == "N_OF":
        return len(satisfied_children) >= (node.required_count or 1)
    if node.node_operator in ("CREDITS_FROM", "UNITS_FROM"):
        total_credits = sum(
            (c.required_course.credit_hours if c.required_course else 0.0) for c in satisfied_children
        )
        return node.required_credit_hours is not None and total_credits >= node.required_credit_hours
    return len(satisfied_children) == len(children)
