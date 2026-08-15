"""Finds the *elective decision points* in a set of programs' requirement trees:
the nodes where more than one course would satisfy the same requirement, so a
client can ask the student "which of these do you want?" before solving.

Two node shapes count as a decision point:

* a `COURSE_GROUP` leaf with 2+ member courses (an approved elective list), and
* a container node whose operator is `ANY`/`N_OF` and whose children are all
  plain `COURSE` leaves (the literal "MATH 1214 or MATH 1215" case).

Everything else -- `ALL` containers, single-course leaves, `CREDITS_FROM` pools
whose children are themselves containers -- isn't a choice the student makes, so
it's skipped; any real choice nested inside such a node surfaces on its own as
the walk recurses.

Nothing here writes to the database. A student's answers come back as
`REQUIRE_COURSE` entries in `ScenarioCreate.preferences`, which
`scenario_service` persists and `optimizer_model._add_hard_preference_constraints`
already enforces."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.academic_program import AcademicProgram
from app.models.course import Course
from app.models.course_group_member import CourseGroupMember
from app.models.plan_course import PlanCourse
from app.models.requirement_allocation import RequirementAllocation
from app.models.requirement_node import RequirementNode
from app.schemas.choice import RequirementChoiceKind, RequirementChoiceOut
from app.schemas.course import CourseOut
from app.schemas.requirement import RequirementNodeOut, RequirementSetOut
from app.services import plan_swap_validation, requirement_service
from app.services.common import load_courses_by_id

# Options inlined per choice. Most course groups are small (157 of 242 have 30
# members or fewer), but ~15 broad elective pools run into the hundreds or
# thousands -- those come back truncated with `options_truncated=True` so the
# client can fetch the full list from `GET /course-groups/{id}/courses` on demand
# instead of every choice paying for the largest pool in the payload.
INLINE_OPTION_LIMIT = 40


def list_requirement_choices(
    db: Session, program_ids: list[int], completed_course_ids: set[int] | None = None
) -> list[RequirementChoiceOut]:
    """Return every elective decision point across the given programs' requirement
    trees, in program -> requirement-set -> display order, deduplicated by
    requirement node (programs routinely share a gen-ed requirement set)."""
    completed = completed_course_ids or set()
    program_names = _program_names(db, program_ids)
    choices: list[RequirementChoiceOut] = []
    seen_node_ids: set[int] = set()
    for program_id in program_ids:
        for req_set in _flattened_requirement_sets(db, program_id):
            choices.extend(
                _choices_in_requirement_set(
                    db, req_set, program_id, program_names.get(program_id, ""), completed, seen_node_ids
                )
            )
    return choices


def _program_names(db: Session, program_ids: list[int]) -> dict[int, str]:
    """Map academic_program_id -> program_name for the requested programs."""
    if not program_ids:
        return {}
    rows = (
        db.query(AcademicProgram.academic_program_id, AcademicProgram.program_name)
        .filter(AcademicProgram.academic_program_id.in_(program_ids))
        .all()
    )
    return dict(rows)


def _flattened_requirement_sets(db: Session, program_id: int) -> list[RequirementSetOut]:
    """Resolve and flatten every requirement set attached to one program."""
    resolved = requirement_service.resolve_requirement_sets(db, [program_id])
    flattened = [
        requirement_service.flatten_requirement_tree(db, req_set.requirement_set_id)
        for req_set in resolved
    ]
    return [req_set for req_set in flattened if req_set is not None]


def _choices_in_requirement_set(
    db: Session,
    req_set: RequirementSetOut,
    program_id: int,
    program_name: str,
    completed_course_ids: set[int],
    seen_node_ids: set[int],
) -> list[RequirementChoiceOut]:
    """Collect one requirement set's decision points, skipping nodes already
    emitted for an earlier program (shared gen-ed sets would otherwise repeat)."""
    candidate_nodes = _collect_choice_nodes(req_set.nodes)
    group_ids = {node.course_group.course_group_id for node in candidate_nodes if node.course_group}
    members_by_group = _load_group_members(db, group_ids)
    courses_by_id = load_courses_by_id(db, {cid for ids in members_by_group.values() for cid in ids})
    choices: list[RequirementChoiceOut] = []
    for node in candidate_nodes:
        if node.requirement_node_id in seen_node_ids:
            continue
        choice = _build_choice(
            node, req_set, program_id, program_name, members_by_group, courses_by_id, completed_course_ids
        )
        if choice is not None:
            seen_node_ids.add(node.requirement_node_id)
            choices.append(choice)
    return choices


def _collect_choice_nodes(nodes: list[RequirementNodeOut]) -> list[RequirementNodeOut]:
    """Depth-first collect every node that looks like an elective decision point,
    in display order, still recursing through non-choice containers."""
    found: list[RequirementNodeOut] = []
    for node in sorted(nodes, key=_display_order_key):
        if _is_course_group_choice(node) or _is_alternative_course_choice(node):
            found.append(node)
        found.extend(_collect_choice_nodes(node.children))
    return found


def _display_order_key(node: RequirementNodeOut) -> tuple[int, int]:
    """Sort key putting nodes in their catalog display order, ties broken by id."""
    return (node.display_order if node.display_order is not None else 0, node.requirement_node_id)


def _is_course_group_choice(node: RequirementNodeOut) -> bool:
    """Return whether this node is a COURSE_GROUP leaf (an approved elective list)."""
    return node.node_type == "COURSE_GROUP" and node.course_group is not None


def _is_alternative_course_choice(node: RequirementNodeOut) -> bool:
    """Return whether this node is a literal "course A or course B" container:
    an ANY/N_OF operator over 2+ children that are all plain COURSE leaves."""
    if node.node_operator not in ("ANY", "N_OF") or len(node.children) < 2:
        return False
    return all(child.node_type == "COURSE" and child.required_course is not None for child in node.children)


def _load_group_members(db: Session, course_group_ids: set[int]) -> dict[int, list[int]]:
    """Return each course group's member course ids, keyed by course_group_id."""
    if not course_group_ids:
        return {}
    rows = (
        db.query(CourseGroupMember.course_group_id, CourseGroupMember.course_id)
        .filter(CourseGroupMember.course_group_id.in_(course_group_ids))
        .all()
    )
    members: dict[int, list[int]] = {}
    for group_id, course_id in rows:
        members.setdefault(group_id, []).append(course_id)
    return members


def _build_choice(
    node: RequirementNodeOut,
    req_set: RequirementSetOut,
    program_id: int,
    program_name: str,
    members_by_group: dict[int, list[int]],
    courses_by_id: dict[int, CourseOut],
    completed_course_ids: set[int],
) -> RequirementChoiceOut | None:
    """Build one `RequirementChoiceOut`, or None if the node turns out to offer
    fewer than two real options (e.g. a course group with a single member)."""
    kind, all_options, course_group_id = _resolve_options(node, members_by_group, courses_by_id)
    if len(all_options) < 2:
        return None
    choose_count = _choose_count(node)
    return RequirementChoiceOut(
        choice_id=f"node-{node.requirement_node_id}",
        requirement_node_id=node.requirement_node_id,
        kind=kind,
        label=_choice_label(node, choose_count),
        choose_count=choose_count,
        required_credit_hours=node.required_credit_hours,
        academic_program_id=program_id,
        program_name=program_name,
        requirement_set_id=req_set.requirement_set_id,
        requirement_set_name=req_set.requirement_set_name,
        course_group_id=course_group_id,
        total_option_count=len(all_options),
        options=all_options[:INLINE_OPTION_LIMIT],
        options_truncated=len(all_options) > INLINE_OPTION_LIMIT,
        already_satisfied=_is_already_satisfied(node, all_options, completed_course_ids, choose_count),
    )


def _resolve_options(
    node: RequirementNodeOut,
    members_by_group: dict[int, list[int]],
    courses_by_id: dict[int, CourseOut],
) -> tuple[RequirementChoiceKind, list[CourseOut], int | None]:
    """Return this node's (kind, sorted option courses, course_group_id)."""
    if _is_course_group_choice(node):
        group_id = node.course_group.course_group_id
        options = [courses_by_id[cid] for cid in members_by_group.get(group_id, []) if cid in courses_by_id]
        return "COURSE_GROUP", _sorted_courses(options), group_id
    kind: RequirementChoiceKind = "N_OF" if node.node_operator == "N_OF" else "ANY_OF"
    options = [child.required_course for child in node.children if child.required_course is not None]
    return kind, _sorted_courses(options), None


def _sorted_courses(courses: list[CourseOut]) -> list[CourseOut]:
    """Sort options the way a catalog lists them: subject code, then course number."""
    return sorted(courses, key=lambda course: (course.subject_code, course.course_number))


def _choose_count(node: RequirementNodeOut) -> int:
    """Return how many courses the student picks here (1 unless the node is an
    explicit N_OF / multi-course group)."""
    if node.node_operator == "ANY":
        return 1
    return max(node.required_count or 1, 1)


def _choice_label(node: RequirementNodeOut, choose_count: int) -> str:
    """Return the clearest available human label for this decision point."""
    if node.node_name:
        return node.node_name
    if node.course_group is not None:
        return node.course_group.course_group_name
    if choose_count > 1:
        return f"Choose {choose_count} of these courses"
    return "Choose one of these courses"


def list_swap_options_for_plan(db: Session, degree_plan_id: int) -> dict[int, list[CourseOut]]:
    """Return, for each `plan_courses` row that satisfies a choice-shaped
    requirement node (an approved course group, or a literal "course A or
    course B" alternative), every catalog course that would equally satisfy
    that same node *and* pass `plan_swap_validation` for that exact slot --
    offered in the term, within its credit cap, and with prerequisites this
    plan already places early enough. A course already placed in a different
    term of this same plan is excluded too (offering it would just bounce as
    a duplicate-course error). A course satisfying a node with no real (valid)
    alternative is simply absent here, so the plan board never offers a swap
    the backend would then reject."""
    allocations = _plan_course_allocations(db, degree_plan_id)
    if not allocations:
        return {}
    nodes_by_id = _load_requirement_nodes(db, {a.requirement_node_id for a in allocations})
    alternatives_by_node_id = _group_alternatives(db, nodes_by_id) | _sibling_alternatives(db, nodes_by_id)
    plan_courses_by_id = _load_plan_courses(db, {a.plan_course_id for a in allocations})
    used_course_ids = _course_ids_in_plan(db, degree_plan_id)
    result: dict[int, list[CourseOut]] = {}
    for allocation in allocations:
        candidates = alternatives_by_node_id.get(allocation.requirement_node_id)
        plan_course = plan_courses_by_id.get(allocation.plan_course_id)
        if not candidates or plan_course is None:
            continue
        valid_options = _valid_swap_candidates(db, plan_course, candidates, used_course_ids)
        if valid_options:
            result[allocation.plan_course_id] = valid_options
    return result


def _load_plan_courses(db: Session, plan_course_ids: set[int]) -> dict[int, PlanCourse]:
    """Fetch plan_courses rows by id, keyed by their own plan_course_id."""
    if not plan_course_ids:
        return {}
    rows = db.query(PlanCourse).filter(PlanCourse.plan_course_id.in_(plan_course_ids)).all()
    return {row.plan_course_id: row for row in rows}


def _course_ids_in_plan(db: Session, degree_plan_id: int) -> set[int]:
    """Return every course_id already placed anywhere in this plan (any term),
    for excluding duplicates from the swap candidate lists."""
    rows = db.query(PlanCourse.course_id).filter(PlanCourse.degree_plan_id == degree_plan_id).all()
    return {course_id for (course_id,) in rows}


def _valid_swap_candidates(
    db: Session, plan_course: PlanCourse, candidates: list[CourseOut], used_course_ids: set[int]
) -> list[CourseOut]:
    """Filter requirement-shaped `candidates` down to the ones that would also
    pass `plan_swap_validation` if swapped into `plan_course`'s slot, excluding
    anything already placed elsewhere in this plan. The currently-assigned
    course always passes trivially (swapping "into" itself is a no-op), so
    it's kept without re-validating even though it's technically "in the plan"."""
    valid: list[CourseOut] = []
    for candidate in candidates:
        if candidate.course_id == plan_course.course_id:
            valid.append(candidate)
            continue
        if candidate.course_id in used_course_ids:
            continue
        course = db.get(Course, candidate.course_id)
        if course is not None and _passes_swap_validation(db, plan_course, course):
            valid.append(candidate)
    return valid


def _passes_swap_validation(db: Session, plan_course: PlanCourse, course: Course) -> bool:
    """Return whether swapping `plan_course` to `course` would pass every
    `plan_swap_validation` check, swallowing its exceptions into a bool since
    this is a pre-filter, not the swap itself."""
    try:
        plan_swap_validation.validate_swap(db, plan_course, course)
        return True
    except (
        plan_swap_validation.CourseNotOfferedInTermError,
        plan_swap_validation.TermCreditCapExceededError,
        plan_swap_validation.PrerequisiteNotMetError,
    ):
        return False


def _plan_course_allocations(db: Session, degree_plan_id: int) -> list[RequirementAllocation]:
    """Return this plan's requirement_allocations that resolve to an assigned
    plan_courses row, as opposed to a pre-existing student_credits row."""
    return (
        db.query(RequirementAllocation)
        .filter(
            RequirementAllocation.degree_plan_id == degree_plan_id,
            RequirementAllocation.plan_course_id.isnot(None),
        )
        .all()
    )


def _load_requirement_nodes(db: Session, node_ids: set[int]) -> dict[int, RequirementNode]:
    """Fetch requirement_nodes rows by id, keyed by their own requirement_node_id."""
    if not node_ids:
        return {}
    rows = db.query(RequirementNode).filter(RequirementNode.requirement_node_id.in_(node_ids)).all()
    return {row.requirement_node_id: row for row in rows}


def _group_alternatives(db: Session, nodes_by_id: dict[int, RequirementNode]) -> dict[int, list[CourseOut]]:
    """Resolve alternatives for every allocated COURSE_GROUP leaf: its own group's other members."""
    group_nodes = {
        node_id: node for node_id, node in nodes_by_id.items() if node.node_type == "COURSE_GROUP" and node.course_group_id
    }
    if not group_nodes:
        return {}
    members_by_group = _load_group_members(db, {node.course_group_id for node in group_nodes.values()})
    courses_by_id = load_courses_by_id(db, {cid for ids in members_by_group.values() for cid in ids})
    result: dict[int, list[CourseOut]] = {}
    for node_id, node in group_nodes.items():
        member_ids = members_by_group.get(node.course_group_id, [])
        options = _sorted_courses([courses_by_id[cid] for cid in member_ids if cid in courses_by_id])
        if len(options) >= 2:
            result[node_id] = options
    return result


def _sibling_alternatives(db: Session, nodes_by_id: dict[int, RequirementNode]) -> dict[int, list[CourseOut]]:
    """Resolve alternatives for every allocated plain COURSE leaf whose parent is
    an ANY/N_OF container of other COURSE leaves (a literal "A or B" choice)."""
    leaf_nodes = {
        node_id: node
        for node_id, node in nodes_by_id.items()
        if node.node_type == "COURSE" and node.parent_requirement_node_id is not None
    }
    if not leaf_nodes:
        return {}
    parents_by_id = _load_requirement_nodes(db, {node.parent_requirement_node_id for node in leaf_nodes.values()})
    choice_parent_ids = {pid for pid, parent in parents_by_id.items() if parent.node_operator in ("ANY", "N_OF")}
    if not choice_parent_ids:
        return {}
    siblings_by_parent = _load_children(db, choice_parent_ids)
    course_ids = {row.required_course_id for rows in siblings_by_parent.values() for row in rows if row.required_course_id}
    courses_by_id = load_courses_by_id(db, course_ids)
    result: dict[int, list[CourseOut]] = {}
    for node_id, node in leaf_nodes.items():
        if node.parent_requirement_node_id not in choice_parent_ids:
            continue
        siblings = siblings_by_parent.get(node.parent_requirement_node_id, [])
        options = _sorted_courses([courses_by_id[row.required_course_id] for row in siblings if row.required_course_id in courses_by_id])
        if len(options) >= 2:
            result[node_id] = options
    return result


def _load_children(db: Session, parent_ids: set[int]) -> dict[int, list[RequirementNode]]:
    """Fetch every requirement_nodes row whose parent is one of `parent_ids`, grouped by parent id."""
    rows = db.query(RequirementNode).filter(RequirementNode.parent_requirement_node_id.in_(parent_ids)).all()
    result: dict[int, list[RequirementNode]] = {}
    for row in rows:
        result.setdefault(row.parent_requirement_node_id, []).append(row)
    return result


def _is_already_satisfied(
    node: RequirementNodeOut,
    options: list[CourseOut],
    completed_course_ids: set[int],
    choose_count: int,
) -> bool:
    """Return whether the reported completed coursework already covers this choice,
    applying the same count-and-credit-hours rule as
    `credit_matching_service._is_group_satisfied`."""
    completed_options = [course for course in options if course.course_id in completed_course_ids]
    if len(completed_options) < choose_count:
        return False
    if node.required_credit_hours is not None:
        earned = sum(course.credit_hours for course in completed_options)
        return earned >= node.required_credit_hours
    return True
