"""Builds the solver's candidate course universe for one planning scenario:
every course its resolved requirement trees could assign (including
course_group alternatives), plus their prerequisite/corequisite closure via
`course_rule_nodes`, minus whatever the student already completed."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.academic_program import AcademicProgram
from app.models.course import Course
from app.models.course_group_member import CourseGroupMember
from app.models.course_rule_node import CourseRuleNode
from app.models.course_relation import CourseRelation
from app.models.enums import (
    CourseRelationType,
    RequisiteType,
    ScenarioPreferenceType,
    ScenarioProgramRole,
)
from app.models.planning_scenario import PlanningScenario
from app.models.overlap_policy import OverlapPolicy
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_preference import ScenarioPreference
from app.models.student_credit import StudentCredit
from app.schemas.course import CourseOut
from app.schemas.requirement import RequirementNodeOut, RequirementSetOut
from app.services import credit_matching_service, requirement_service
from app.services.common import load_courses_by_id
from app.services.credit_matching_service import COMPLETED_STATUS

# Safety valve on prerequisite-closure growth, not a modeling decision. The
# original value (60) was set before the closure was measured against the full
# catalog and turned out to bind on ordinary scenarios: Aerospace BS alone wants
# 88 extra courses over 3 levels, so every generated plan came back carrying
# ~24 "a prerequisite was excluded by the closure growth cap" warnings. The whole
# prerequisite graph is only 4,777 `course_rule_nodes` rows over 2,120 courses,
# so a cap in the hundreds still bounds a pathological expansion (the
# same-or-above-level language/biology ladder in db/SUMMARY.md §3a) while never
# firing on a real degree program.
MAX_CLOSURE_GROWTH = 500
_CLOSURE_REQUISITE_TYPES = (
    RequisiteType.PREREQUISITE,
    RequisiteType.COREQUISITE,
    RequisiteType.PRE_OR_COREQUISITE,
)
# A minor/emphasis doesn't have its own "total credits to graduate" -- it just
# adds specific coursework on top of a bachelor's degree, already enforced via
# the requirement-node constraints. Only a MAJOR-level program's own published
# total is a real graduation floor.
_CREDIT_FLOOR_ROLES = (ScenarioProgramRole.PRIMARY_MAJOR, ScenarioProgramRole.SECOND_MAJOR)
_STANDARD_COURSE_TYPE = "STANDARD"
_EXPLICIT_COURSE_PREFERENCE_TYPES = (
    ScenarioPreferenceType.REQUIRE_COURSE,
    ScenarioPreferenceType.PREFER_COURSE,
    ScenarioPreferenceType.FIX_COURSE_TO_TERM,
)


@dataclass(frozen=True)
class CandidateCourseSet:
    """The full solver input derived from one scenario: its requirement
    trees (already flattened and credit-matched), which courses are open
    decision variables, which are already completed, and whether the
    prerequisite-closure growth cap was hit while building it."""

    requirement_sets: list[RequirementSetOut]
    assignable_course_ids: set[int]
    completed_course_ids: set[int]
    courses_by_id: dict[int, CourseOut]
    excluded_nonstandard_course_ids: set[int]
    group_members: dict[int, set[int]]
    course_ids_by_program: dict[int, set[int]]
    closure_capped: bool
    # credit_hours for every course_group member, including ones already completed
    # (and so absent from `courses_by_id`, which only holds assignable courses).
    # `optimizer_model` needs these to enforce a group's required_credit_hours.
    credit_hours_by_course_id: dict[int, float]
    # How many more credit hours (beyond what's already completed) the scenario's
    # major(s) officially require to graduate, or None if no program in scope has
    # a published total_credit_hours. `optimizer_model` only enforces this as a
    # hard floor when the scenario opted in (see enforce_program_credit_minimum).
    credit_floor_remaining: float | None
    # The student's total earned credit hours so far (transfer + completed
    # coursework), independent of this scenario's own requirement trees.
    # `optimizer_model` adds each term's newly-assigned credits on top of this to
    # approximate class standing for STANDING/SUBJECT_LEVEL prerequisite leaves.
    completed_credit_hours: float
    subject_id_by_course_id: dict[int, int]
    course_level_by_course_id: dict[int, int]
    equivalent_course_ids: dict[int, set[int]]
    duplicate_credit_relations: list[CourseRelation]
    selected_program_ids: set[int]
    overlap_policies: list[OverlapPolicy]
    requirement_set_id_by_node_id: dict[int, int]
    program_ids_by_requirement_set: dict[int, set[int]]


def build_candidate_course_set(
    db: Session, scenario: PlanningScenario, program_ids_override: list[int] | None = None
) -> CandidateCourseSet:
    """Build the candidate course universe for a scenario, ready to hand to `optimizer_model`.
    `program_ids_override` lets `optimizer_service` build a 'primary major alone' baseline
    without the scenario's other scenario_programs rows."""
    program_ids = (
        program_ids_override
        if program_ids_override is not None
        else _resolve_scenario_program_ids(db, scenario.planning_scenario_id)
    )
    requirement_sets = _collect_requirement_sets(db, program_ids, scenario.student_id)
    completed_course_ids = _collect_completed_course_ids(db, scenario.student_id)
    group_ids = _collect_course_group_ids(requirement_sets)
    group_members = _load_group_members(db, group_ids)
    group_course_levels = _load_group_course_levels(db, group_members)
    course_ids_by_requirement_set = _index_course_ids_by_requirement_set(
        requirement_sets, group_members, group_course_levels
    )
    course_ids_by_program = _index_course_ids_by_program(
        db, program_ids, course_ids_by_requirement_set
    )
    direct_course_ids: set[int] = set()
    for course_ids in course_ids_by_requirement_set.values():
        direct_course_ids |= course_ids
    explicit_course_ids = _collect_explicit_course_ids(db, scenario.planning_scenario_id)
    equivalent_course_ids = _load_equivalent_course_ids(db, direct_course_ids | completed_course_ids)
    expanded_direct_ids = direct_course_ids | {
        equivalent_id for course_id in direct_course_ids for equivalent_id in equivalent_course_ids.get(course_id, set())
    } | explicit_course_ids
    unfiltered_course_ids, closure_capped = _expand_prerequisite_closure(
        db, expanded_direct_ids, completed_course_ids
    )
    unfiltered_courses = load_courses_by_id(db, unfiltered_course_ids)
    courses_by_id, excluded_nonstandard_course_ids = _filter_optimization_courses(
        unfiltered_courses, explicit_course_ids
    )
    assignable_course_ids = set(courses_by_id)
    eligible_requirement_ids = assignable_course_ids | completed_course_ids
    group_members = _filter_course_id_sets(group_members, eligible_requirement_ids)
    course_ids_by_requirement_set = _filter_course_id_sets(
        course_ids_by_requirement_set, eligible_requirement_ids
    )
    course_ids_by_program = _filter_course_id_sets(
        course_ids_by_program, eligible_requirement_ids
    )
    completed_credit_hours = _completed_credit_hours_total(db, scenario.student_id)
    credit_hours_by_course_id, subject_ids, course_levels = _load_course_metadata(
        db, group_members, courses_by_id, completed_course_ids
    )
    applicable_completed_credits = _degree_applicable_completed_credit_hours(
        db, scenario.student_id, direct_course_ids, equivalent_course_ids
    )
    return CandidateCourseSet(
        requirement_sets=requirement_sets,
        assignable_course_ids=assignable_course_ids,
        completed_course_ids=completed_course_ids,
        courses_by_id=courses_by_id,
        excluded_nonstandard_course_ids=excluded_nonstandard_course_ids,
        group_members=group_members,
        course_ids_by_program=course_ids_by_program,
        closure_capped=closure_capped,
        credit_hours_by_course_id=credit_hours_by_course_id,
        credit_floor_remaining=_resolve_credit_floor_remaining(
            db, scenario, program_ids, applicable_completed_credits
        ),
        completed_credit_hours=completed_credit_hours,
        subject_id_by_course_id=subject_ids,
        course_level_by_course_id=course_levels,
        equivalent_course_ids=equivalent_course_ids,
        duplicate_credit_relations=_load_duplicate_credit_relations(
            db, assignable_course_ids | completed_course_ids
        ),
        selected_program_ids=set(program_ids),
        overlap_policies=_load_overlap_policies(db, program_ids),
        requirement_set_id_by_node_id=_index_requirement_set_ids_by_node(requirement_sets),
        program_ids_by_requirement_set=_index_program_ids_by_requirement_set(
            db, program_ids
        ),
    )


def _collect_explicit_course_ids(db: Session, planning_scenario_id: int) -> set[int]:
    """Return courses the student explicitly required, preferred, or fixed to a term."""
    rows = db.query(ScenarioPreference.course_id).filter(
        ScenarioPreference.planning_scenario_id == planning_scenario_id,
        ScenarioPreference.preference_type.in_(_EXPLICIT_COURSE_PREFERENCE_TYPES),
        ScenarioPreference.course_id.isnot(None),
    ).all()
    return {course_id for (course_id,) in rows}


def _filter_optimization_courses(
    courses_by_id: dict[int, CourseOut], explicit_course_ids: set[int]
) -> tuple[dict[int, CourseOut], set[int]]:
    """Keep standard and explicitly selected courses and return excluded non-standard ids."""
    included = {
        course_id: course
        for course_id, course in courses_by_id.items()
        if course.course_type == _STANDARD_COURSE_TYPE or course_id in explicit_course_ids
    }
    return included, set(courses_by_id) - included.keys()


def _filter_course_id_sets(
    course_ids_by_owner: dict[int, set[int]], eligible_course_ids: set[int]
) -> dict[int, set[int]]:
    """Restrict each indexed course-id set to courses eligible for requirement use."""
    return {
        owner_id: course_ids & eligible_course_ids
        for owner_id, course_ids in course_ids_by_owner.items()
    }


def _index_requirement_set_ids_by_node(
    requirement_sets: list[RequirementSetOut],
) -> dict[int, int]:
    """Return the owning requirement-set id for every flattened node."""
    result: dict[int, int] = {}
    for requirement_set in requirement_sets:
        _record_node_requirement_set_ids(
            requirement_set.nodes, requirement_set.requirement_set_id, result
        )
    return result


def _record_node_requirement_set_ids(
    nodes: list[RequirementNodeOut], requirement_set_id: int, result: dict[int, int]
) -> None:
    """Recursively record one requirement set's ownership for its nodes."""
    for node in nodes:
        result[node.requirement_node_id] = requirement_set_id
        _record_node_requirement_set_ids(node.children, requirement_set_id, result)


def _load_overlap_policies(db: Session, program_ids: list[int]) -> list[OverlapPolicy]:
    """Return explicit policies whose program pair is fully selected in this scenario."""
    if len(program_ids) < 2:
        return []
    return (
        db.query(OverlapPolicy)
        .filter(
            OverlapPolicy.program_a_id.in_(program_ids),
            OverlapPolicy.program_b_id.in_(program_ids),
        )
        .all()
    )


def _resolve_credit_floor_remaining(
    db: Session, scenario: PlanningScenario, program_ids: list[int], completed_credit_hours: float
) -> float | None:
    """Return how many more credit hours the scenario's in-scope MAJOR-role
    program(s) require beyond what the student has already earned, or None if
    none of them has a published total_credit_hours to compare against."""
    target = _resolve_credit_floor_target(db, scenario.planning_scenario_id, program_ids)
    if target is None:
        return None
    return max(target - completed_credit_hours, 0.0)


def _resolve_credit_floor_target(db: Session, planning_scenario_id: int, program_ids: list[int]) -> float | None:
    """Return the highest published total_credit_hours among this scenario's
    MAJOR-role programs (restricted to `program_ids`, so the 'primary major
    alone' baseline solve sees only that program's own total) -- the credit
    floor a bachelor's degree already requires no matter how many majors are
    combined with it."""
    if not program_ids:
        return None
    rows = (
        db.query(AcademicProgram.total_credit_hours)
        .join(ScenarioProgram, ScenarioProgram.academic_program_id == AcademicProgram.academic_program_id)
        .filter(
            ScenarioProgram.planning_scenario_id == planning_scenario_id,
            ScenarioProgram.academic_program_id.in_(program_ids),
            ScenarioProgram.program_role.in_(_CREDIT_FLOOR_ROLES),
            AcademicProgram.total_credit_hours.isnot(None),
        )
        .all()
    )
    totals = [float(total) for (total,) in rows if total is not None]
    return max(totals) if totals else None


def _completed_credit_hours_total(db: Session, student_id: int) -> float:
    """Return a student's total earned credit hours across every COMPLETED
    student_credits row, falling back to the catalog's credit_hours for an
    institutional course reported without its own explicit credits_earned."""
    rows = (
        db.query(StudentCredit.course_id, StudentCredit.credits_earned, Course.credit_hours)
        .outerjoin(Course, StudentCredit.course_id == Course.course_id)
        .filter(StudentCredit.student_id == student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    institutional: dict[int, float] = {}
    external_total = 0.0
    for course_id, earned, catalog in rows:
        credits = float(earned if earned is not None else (catalog or 0))
        if course_id is None:
            external_total += credits
        else:
            institutional[course_id] = max(institutional.get(course_id, 0), credits)
    return external_total + _cap_related_completed_credits(db, institutional)


def _load_course_metadata(
    db: Session,
    group_members: dict[int, set[int]],
    courses_by_id: dict[int, CourseOut],
    completed_course_ids: set[int],
) -> tuple[dict[int, float], dict[int, int], dict[int, int]]:
    """Return metadata for assignable, group-member, and completed courses."""
    credit_hours = {course_id: course.credit_hours for course_id, course in courses_by_id.items()}
    subject_ids = {course_id: course.subject_id for course_id, course in courses_by_id.items()}
    course_levels = {course_id: course.course_level for course_id, course in courses_by_id.items()}
    member_ids = {course_id for members in group_members.values() for course_id in members}
    missing_ids = (member_ids | completed_course_ids) - credit_hours.keys()
    if missing_ids:
        rows = (
            db.query(Course.course_id, Course.credit_hours, Course.subject_id, Course.course_level)
            .filter(Course.course_id.in_(missing_ids))
            .all()
        )
        for course_id, hours, subject_id, course_level in rows:
            credit_hours[course_id] = float(hours)
            subject_ids[course_id] = subject_id
            course_levels[course_id] = course_level
    return credit_hours, subject_ids, course_levels


def _load_equivalent_course_ids(db: Session, course_ids: set[int]) -> dict[int, set[int]]:
    """Map each requirement course to directed equivalent courses that may satisfy it."""
    if not course_ids:
        return {}
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
    equivalents: dict[int, set[int]] = {}
    for relation in rows:
        equivalents.setdefault(relation.related_course_id, set()).add(relation.course_id)
        if relation.is_bidirectional:
            equivalents.setdefault(relation.course_id, set()).add(relation.related_course_id)
    return equivalents


def _load_duplicate_credit_relations(db: Session, course_ids: set[int]) -> list[CourseRelation]:
    """Return duplicate-credit relations whose two courses are in the candidate universe."""
    if not course_ids:
        return []
    return (
        db.query(CourseRelation)
        .filter(
            CourseRelation.relation_type.in_(
                (CourseRelationType.DUPLICATE_CREDIT, CourseRelationType.MUTUALLY_EXCLUSIVE)
            ),
            CourseRelation.course_id.in_(course_ids),
            CourseRelation.related_course_id.in_(course_ids),
        )
        .all()
    )


def _degree_applicable_completed_credit_hours(
    db: Session,
    student_id: int,
    direct_course_ids: set[int],
    equivalent_course_ids: dict[int, set[int]],
) -> float:
    """Return completed credits conservatively known to apply to selected requirements."""
    applicable_ids = set(direct_course_ids)
    for course_id in direct_course_ids:
        applicable_ids |= equivalent_course_ids.get(course_id, set())
    rows = (
        db.query(StudentCredit.course_id, StudentCredit.credits_earned, Course.credit_hours)
        .outerjoin(Course, StudentCredit.course_id == Course.course_id)
        .filter(
            StudentCredit.student_id == student_id,
            StudentCredit.status == COMPLETED_STATUS,
            StudentCredit.course_id.in_(applicable_ids),
        )
        .all()
    )
    credits_by_course: dict[int, float] = {}
    for course_id, earned, catalog in rows:
        credits = float(earned if earned is not None else (catalog or 0))
        credits_by_course[course_id] = max(credits_by_course.get(course_id, 0), credits)
    return _cap_related_completed_credits(db, credits_by_course)


def _cap_related_completed_credits(
    db: Session, credits_by_course: dict[int, float]
) -> float:
    """Return completed credits after relation-based duplicate-credit caps."""
    course_ids = set(credits_by_course)
    if len(course_ids) < 2:
        return sum(credits_by_course.values())
    relations = db.query(CourseRelation).filter(
        CourseRelation.course_id.in_(course_ids),
        CourseRelation.related_course_id.in_(course_ids),
        CourseRelation.relation_type.in_(
            (
                CourseRelationType.CROSS_LISTED,
                CourseRelationType.EQUIVALENT,
                CourseRelationType.DUPLICATE_CREDIT,
                CourseRelationType.MUTUALLY_EXCLUSIVE,
            )
        ),
    ).all()
    total = sum(credits_by_course.values())
    seen_pairs: set[tuple[int, int]] = set()
    for relation in relations:
        pair = tuple(sorted((relation.course_id, relation.related_course_id)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        first = credits_by_course[relation.course_id]
        second = credits_by_course[relation.related_course_id]
        allowed = (
            float(relation.maximum_combined_credits)
            if relation.maximum_combined_credits is not None
            else max(first, second)
        )
        total -= max(first + second - allowed, 0)
    return max(total, 0)


def _resolve_scenario_program_ids(db: Session, planning_scenario_id: int) -> list[int]:
    """Return every academic_program_id selected for this scenario (primary major + any goals)."""
    rows = (
        db.query(ScenarioProgram.academic_program_id)
        .filter(ScenarioProgram.planning_scenario_id == planning_scenario_id)
        .all()
    )
    return [program_id for (program_id,) in rows]


def _collect_requirement_sets(
    db: Session, program_ids: list[int], student_id: int
) -> list[RequirementSetOut]:
    """Resolve, flatten, and credit-match every requirement set attached to the given programs."""
    requirement_sets = requirement_service.resolve_requirement_sets(db, program_ids)
    flattened = [
        requirement_service.flatten_requirement_tree(db, req_set.requirement_set_id)
        for req_set in requirement_sets
    ]
    return [
        credit_matching_service.match_completed_courses(db, student_id, req_set)
        for req_set in flattened
        if req_set is not None
    ]


def _index_course_ids_by_requirement_set(
    requirement_sets: list[RequirementSetOut],
    group_members: dict[int, set[int]],
    course_levels: dict[int, int],
) -> dict[int, set[int]]:
    """Return each requirement set's referenced course ids (COURSE leaves plus
    COURSE_GROUP members), keyed by requirement_set_id."""
    result: dict[int, set[int]] = {}
    for req_set in requirement_sets:
        course_ids = _collect_eligible_course_ids_from_nodes(
            req_set.nodes, group_members, course_levels
        )
        result[req_set.requirement_set_id] = course_ids
    return result


def _collect_eligible_course_ids_from_nodes(
    nodes: list[RequirementNodeOut],
    group_members: dict[int, set[int]],
    course_levels: dict[int, int],
) -> set[int]:
    """Collect direct requirement candidates after authoritative node-level filtering."""
    course_ids: set[int] = set()
    for node in nodes:
        if node.required_course is not None:
            if node.minimum_course_level is None or node.required_course.course_level >= node.minimum_course_level:
                course_ids.add(node.required_course.course_id)
        if node.course_group is not None:
            members = group_members.get(node.course_group.course_group_id, set())
            course_ids |= {
                course_id
                for course_id in members
                if node.minimum_course_level is None
                or course_levels.get(course_id, 0) >= node.minimum_course_level
            }
        course_ids |= _collect_eligible_course_ids_from_nodes(node.children, group_members, course_levels)
    return course_ids


def _load_group_course_levels(
    db: Session, group_members: dict[int, set[int]]
) -> dict[int, int]:
    """Return course levels for all group members so node floors can prune candidates early."""
    course_ids = {course_id for members in group_members.values() for course_id in members}
    if not course_ids:
        return {}
    return dict(
        db.query(Course.course_id, Course.course_level).filter(Course.course_id.in_(course_ids)).all()
    )


def _index_course_ids_by_program(
    db: Session, program_ids: list[int], course_ids_by_requirement_set: dict[int, set[int]]
) -> dict[int, set[int]]:
    """Return each program's referenced course ids (union across all its own requirement
    sets), keyed by academic_program_id -- the signal `optimizer_objectives` uses to detect
    genuine cross-PROGRAM double counting (UC-15), as distinct from a single program's own
    multiple requirement sets (core/gen-ed/electives) naturally sharing a course."""
    requirement_set_ids_by_program = _load_requirement_set_ids_by_program(db, program_ids)
    result: dict[int, set[int]] = {}
    for program_id in program_ids:
        course_ids: set[int] = set()
        for requirement_set_id in requirement_set_ids_by_program.get(program_id, set()):
            course_ids |= course_ids_by_requirement_set.get(requirement_set_id, set())
        result[program_id] = course_ids
    return result


def _load_requirement_set_ids_by_program(db: Session, program_ids: list[int]) -> dict[int, set[int]]:
    """Return each program's linked requirement_set ids, keyed by academic_program_id."""
    if not program_ids:
        return {}
    rows = (
        db.query(ProgramRequirementSet.academic_program_id, ProgramRequirementSet.requirement_set_id)
        .filter(ProgramRequirementSet.academic_program_id.in_(program_ids))
        .all()
    )
    result: dict[int, set[int]] = {}
    for program_id, requirement_set_id in rows:
        result.setdefault(program_id, set()).add(requirement_set_id)
    return result


def _index_program_ids_by_requirement_set(
    db: Session, program_ids: list[int]
) -> dict[int, set[int]]:
    """Return selected program owners for every linked requirement set."""
    result: dict[int, set[int]] = {}
    for program_id, set_ids in _load_requirement_set_ids_by_program(db, program_ids).items():
        for requirement_set_id in set_ids:
            result.setdefault(requirement_set_id, set()).add(program_id)
    return result


def _collect_course_group_ids(requirement_sets: list[RequirementSetOut]) -> set[int]:
    """Recursively collect every course_group id referenced across all given requirement trees."""
    group_ids: set[int] = set()
    for req_set in requirement_sets:
        group_ids |= _collect_group_ids_from_nodes(req_set.nodes)
    return group_ids


def _collect_group_ids_from_nodes(nodes: list[RequirementNodeOut]) -> set[int]:
    """Recursively collect course_group ids from requirement nodes and their children."""
    group_ids: set[int] = set()
    for node in nodes:
        if node.course_group is not None:
            group_ids.add(node.course_group.course_group_id)
        group_ids |= _collect_group_ids_from_nodes(node.children)
    return group_ids


def _load_group_members(db: Session, course_group_ids: set[int]) -> dict[int, set[int]]:
    """Return each course group's member course ids, keyed by course_group_id."""
    if not course_group_ids:
        return {}
    rows = (
        db.query(CourseGroupMember.course_group_id, CourseGroupMember.course_id)
        .filter(CourseGroupMember.course_group_id.in_(course_group_ids))
        .all()
    )
    members: dict[int, set[int]] = {}
    for group_id, course_id in rows:
        members.setdefault(group_id, set()).add(course_id)
    return members


def _collect_completed_course_ids(db: Session, student_id: int) -> set[int]:
    """Return course ids the student has already completed (status COMPLETED, real course only)."""
    rows = (
        db.query(StudentCredit.course_id)
        .filter(StudentCredit.student_id == student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    return {course_id for (course_id,) in rows if course_id is not None}


def _expand_prerequisite_closure(
    db: Session, course_ids: set[int], completed_course_ids: set[int]
) -> tuple[set[int], bool]:
    """Breadth-first expand `course_ids` to include their PREREQUISITE/COREQUISITE
    chains via course_rule_nodes, capped at MAX_CLOSURE_GROWTH additional courses so
    a loosely-linked cluster (e.g. the same-or-above-level language ladder documented
    in db/SUMMARY.md) can't balloon the candidate set. When the cap does bind, the
    truncation is taken in sorted id order so the same scenario always produces the
    same candidate set (iterating a `set` directly made it depend on hash ordering)."""
    visited = set(course_ids) - completed_course_ids
    frontier = set(visited)
    growth = 0
    capped = False
    while frontier and growth < MAX_CLOSURE_GROWTH:
        next_ids = _direct_prerequisite_course_ids(db, frontier) - completed_course_ids - visited
        if not next_ids:
            break
        if growth + len(next_ids) > MAX_CLOSURE_GROWTH:
            next_ids = set(sorted(next_ids)[: MAX_CLOSURE_GROWTH - growth])
            capped = True
        visited |= next_ids
        growth += len(next_ids)
        frontier = next_ids
    return visited, capped


def _direct_prerequisite_course_ids(db: Session, course_ids: set[int]) -> set[int]:
    """Return course ids directly required as a PREREQUISITE/COREQUISITE/PRE_OR_COREQUISITE
    of any of the given target courses."""
    rows = (
        db.query(CourseRuleNode.required_course_id)
        .filter(
            CourseRuleNode.target_course_id.in_(course_ids),
            CourseRuleNode.requisite_type.in_(_CLOSURE_REQUISITE_TYPES),
            CourseRuleNode.required_course_id.isnot(None),
        )
        .all()
    )
    return {course_id for (course_id,) in rows}
