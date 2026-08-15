"""Resolving which requirement_sets apply to a set of programs, and flattening
one requirement_set's `requirement_nodes` rows into a nested, evaluable tree."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.course_group import CourseGroup
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.requirement_node import RequirementNode
from app.models.requirement_set import RequirementSet
from app.schemas.course import CourseGroupOut, CourseOut
from app.schemas.requirement import RequirementNodeOut, RequirementSetOut
from app.services.common import load_courses_by_id


def resolve_requirement_sets(db: Session, program_ids: list[int]) -> list[RequirementSet]:
    """Every requirement_set attached to any of the given programs, deduplicated
    (programs can share a set, e.g. a common general-education set) and ordered
    by the lowest display_order any of those programs gave it."""
    if not program_ids:
        return []
    rows = (
        db.query(ProgramRequirementSet, RequirementSet)
        .join(RequirementSet, RequirementSet.requirement_set_id == ProgramRequirementSet.requirement_set_id)
        .filter(ProgramRequirementSet.academic_program_id.in_(program_ids))
        .all()
    )
    best_order, sets_by_id = _index_requirement_sets_by_best_order(rows)
    return sorted(
        sets_by_id.values(), key=lambda rs: (best_order[rs.requirement_set_id], rs.requirement_set_id)
    )


def _index_requirement_sets_by_best_order(
    rows: list[tuple[ProgramRequirementSet, RequirementSet]],
) -> tuple[dict[int, int], dict[int, RequirementSet]]:
    """Reduce (link, requirement_set) rows to each set's lowest display_order across all linking programs."""
    best_order: dict[int, int] = {}
    sets_by_id: dict[int, RequirementSet] = {}
    for link, req_set in rows:
        sets_by_id[req_set.requirement_set_id] = req_set
        order = link.display_order if link.display_order is not None else 0
        if req_set.requirement_set_id not in best_order or order < best_order[req_set.requirement_set_id]:
            best_order[req_set.requirement_set_id] = order
    return best_order, sets_by_id


def flatten_requirement_tree(db: Session, requirement_set_id: int) -> RequirementSetOut | None:
    """Resolve one requirement_set's `requirement_nodes` rows (a flat table,
    self-referencing via `parent_requirement_node_id`) into a nested tree:
    each node carries its operator, its children, and (for leaves) the full
    course/course_group it points at -- ready to evaluate without any more
    database round-trips."""
    req_set = db.get(RequirementSet, requirement_set_id)
    if req_set is None:
        return None
    node_rows = _load_requirement_node_rows(db, requirement_set_id)
    course_ids = {row.required_course_id for row in node_rows if row.required_course_id}
    course_group_ids = {row.course_group_id for row in node_rows if row.course_group_id}
    courses_by_id = load_courses_by_id(db, course_ids)
    groups_by_id = _load_course_groups(db, course_group_ids)
    children_by_parent = _index_requirement_nodes_by_parent(node_rows)
    root_nodes = [
        _build_requirement_node(row, courses_by_id, groups_by_id, children_by_parent)
        for row in children_by_parent.get(None, [])
    ]
    return RequirementSetOut(
        requirement_set_id=req_set.requirement_set_id,
        requirement_set_code=req_set.requirement_set_code,
        requirement_set_name=req_set.requirement_set_name,
        requirement_set_type=req_set.requirement_set_type,
        description=req_set.description,
        nodes=root_nodes,
    )


def _load_requirement_node_rows(db: Session, requirement_set_id: int) -> list[RequirementNode]:
    """Fetch all `requirement_nodes` rows belonging to one requirement set, in id order."""
    return (
        db.query(RequirementNode)
        .filter(RequirementNode.requirement_set_id == requirement_set_id)
        .order_by(RequirementNode.requirement_node_id.asc())
        .all()
    )


def _index_requirement_nodes_by_parent(
    node_rows: list[RequirementNode],
) -> dict[int | None, list[RequirementNode]]:
    """Group requirement nodes by parent id and sort each sibling group by display_order, then id."""
    children_by_parent: dict[int | None, list[RequirementNode]] = {}
    for row in node_rows:
        children_by_parent.setdefault(row.parent_requirement_node_id, []).append(row)
    for siblings in children_by_parent.values():
        siblings.sort(key=lambda r: (r.display_order if r.display_order is not None else 0, r.requirement_node_id))
    return children_by_parent


def _build_requirement_node(
    node: RequirementNode,
    courses_by_id: dict[int, CourseOut],
    groups_by_id: dict[int, CourseGroupOut],
    children_by_parent: dict[int | None, list[RequirementNode]],
) -> RequirementNodeOut:
    """Recursively convert one `requirement_nodes` row and its descendants into a `RequirementNodeOut`."""
    return RequirementNodeOut(
        requirement_node_id=node.requirement_node_id,
        node_type=node.node_type,
        node_operator=node.node_operator,
        node_name=node.node_name,
        required_course=courses_by_id.get(node.required_course_id) if node.required_course_id else None,
        course_group=groups_by_id.get(node.course_group_id) if node.course_group_id else None,
        required_credit_hours=(
            float(node.required_credit_hours) if node.required_credit_hours is not None else None
        ),
        required_count=node.required_count,
        minimum_grade=node.minimum_grade,
        minimum_course_level=node.minimum_course_level,
        minimum_distinct_subjects=node.minimum_distinct_subjects,
        display_order=node.display_order,
        is_active=node.is_active,
        source_text=node.source_text,
        children=[
            _build_requirement_node(child, courses_by_id, groups_by_id, children_by_parent)
            for child in children_by_parent.get(node.requirement_node_id, [])
        ],
    )


def _load_course_groups(db: Session, course_group_ids: set[int]) -> dict[int, CourseGroupOut]:
    """Fetch the given course groups and return them as `CourseGroupOut` objects keyed by id."""
    if not course_group_ids:
        return {}
    rows = db.query(CourseGroup).filter(CourseGroup.course_group_id.in_(course_group_ids)).all()
    return {g.course_group_id: CourseGroupOut.model_validate(g) for g in rows}
