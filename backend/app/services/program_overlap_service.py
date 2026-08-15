"""Suggests other programs (second majors, minors, emphases) whose own course
requirements double up with a given program's -- so a student picking a
second program can see which ones mostly reuse courses they'd take anyway,
instead of quietly stacking on a mostly-separate set of extra classes.

Computed from the same course-level data the optimizer already ranks in
`optimizer_objectives.MAX_REQUIREMENT_OVERLAP`, but at the catalog level
(every course either program *could* require) rather than one scenario's
solved assignments -- this runs before a scenario exists, while a student is
still choosing what to study."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.academic_program import AcademicProgram
from app.models.course_group_member import CourseGroupMember
from app.models.enums import ProgramType
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.requirement_node import RequirementNode
from app.schemas.course import CourseOut
from app.schemas.program import ProgramOverlapOut
from app.services.common import load_courses_by_id

DEFAULT_SUGGESTION_LIMIT = 10
OVERLAP_PREVIEW_LIMIT = 8
# Groups bigger than this are broad elective pools (e.g. "any gen-ed course"),
# not a specific, meaningful shared requirement -- most course groups in the
# catalog have well under 50 members; the rest are university-wide pools that
# nearly every program can draw from, so counting them would swamp genuine
# major/minor overlap with noise shared by almost any two programs.
MAX_GROUP_SIZE_FOR_OVERLAP = 50


def suggest_overlapping_programs(
    db: Session,
    academic_program_id: int,
    program_type: ProgramType | None = None,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
) -> list[ProgramOverlapOut]:
    """Return other active programs ranked by how much of *their own*
    requirements are already covered by `academic_program_id`'s courses,
    optionally narrowed to one `program_type` (e.g. only MINOR suggestions).
    Ranked by coverage ratio rather than raw shared-course count, so a small
    15-credit minor that's 90% covered outranks a huge major that happens to
    share more courses in absolute terms but covers a smaller slice of itself."""
    course_ids_by_program = _course_ids_by_program(db)
    target_courses = course_ids_by_program.get(academic_program_id, set())
    if not target_courses:
        return []
    candidates = _candidate_programs(db, academic_program_id, program_type)
    courses_by_id = load_courses_by_id(db, {cid for ids in course_ids_by_program.values() for cid in ids})
    overlaps = [
        _build_overlap(candidate, course_ids_by_program.get(candidate.academic_program_id, set()), target_courses, courses_by_id)
        for candidate in candidates
    ]
    ranked = sorted(overlaps, key=_overlap_sort_key, reverse=True)
    return [overlap for overlap in ranked if overlap.overlap_course_count > 0][:limit]


def _overlap_sort_key(overlap: ProgramOverlapOut) -> tuple[float, float]:
    """Rank primarily by coverage ratio (treating an unknown total as 0
    coverage), tie-broken by absolute overlap credit hours."""
    return (overlap.overlap_ratio or 0.0, overlap.overlap_credit_hours)


def _candidate_programs(
    db: Session, exclude_program_id: int, program_type: ProgramType | None
) -> list[AcademicProgram]:
    """Return every other active program, optionally narrowed to one program_type."""
    query = db.query(AcademicProgram).filter(
        AcademicProgram.academic_program_id != exclude_program_id, AcademicProgram.is_active.is_(True)
    )
    if program_type is not None:
        query = query.filter(AcademicProgram.program_type == program_type)
    return query.order_by(AcademicProgram.program_name).all()


def _course_ids_by_program(db: Session) -> dict[int, set[int]]:
    """Map every program to the full set of course_ids its requirement trees
    reference, directly or through an elective course group. Computed for
    every program at once via two bulk queries, so ranking suggestions for one
    program doesn't cost one requirement-tree walk per candidate program."""
    result: dict[int, set[int]] = {}
    _add_direct_course_ids(db, result)
    _add_group_course_ids(db, result)
    return result


def _add_direct_course_ids(db: Session, result: dict[int, set[int]]) -> None:
    """Add each program's directly-named COURSE requirement_nodes' course ids into `result`."""
    rows = (
        db.query(ProgramRequirementSet.academic_program_id, RequirementNode.required_course_id)
        .join(RequirementNode, RequirementNode.requirement_set_id == ProgramRequirementSet.requirement_set_id)
        .filter(RequirementNode.required_course_id.isnot(None))
        .all()
    )
    for program_id, course_id in rows:
        result.setdefault(program_id, set()).add(course_id)


def _add_group_course_ids(db: Session, result: dict[int, set[int]]) -> None:
    """Add each program's COURSE_GROUP requirement_nodes' member course ids into
    `result`, skipping groups bigger than MAX_GROUP_SIZE_FOR_OVERLAP (see its
    docstring for why)."""
    small_group_ids = _small_course_group_ids(db)
    if not small_group_ids:
        return
    rows = (
        db.query(ProgramRequirementSet.academic_program_id, CourseGroupMember.course_id)
        .join(RequirementNode, RequirementNode.requirement_set_id == ProgramRequirementSet.requirement_set_id)
        .join(CourseGroupMember, CourseGroupMember.course_group_id == RequirementNode.course_group_id)
        .filter(RequirementNode.course_group_id.in_(small_group_ids))
        .all()
    )
    for program_id, course_id in rows:
        result.setdefault(program_id, set()).add(course_id)


def _small_course_group_ids(db: Session) -> set[int]:
    """Return the ids of every course group with at most MAX_GROUP_SIZE_FOR_OVERLAP members."""
    rows = (
        db.query(CourseGroupMember.course_group_id)
        .group_by(CourseGroupMember.course_group_id)
        .having(func.count(CourseGroupMember.course_id) <= MAX_GROUP_SIZE_FOR_OVERLAP)
        .all()
    )
    return {row[0] for row in rows}


def _build_overlap(
    candidate: AcademicProgram,
    candidate_courses: set[int],
    target_courses: set[int],
    courses_by_id: dict[int, CourseOut],
) -> ProgramOverlapOut:
    """Build one candidate program's overlap summary against the target program's course set."""
    shared_ids = candidate_courses & target_courses
    total_credit_hours = float(candidate.total_credit_hours) if candidate.total_credit_hours is not None else None
    overlap_credit_hours = sum(courses_by_id[cid].credit_hours for cid in shared_ids if cid in courses_by_id)
    return ProgramOverlapOut(
        academic_program_id=candidate.academic_program_id,
        program_code=candidate.program_code,
        program_name=candidate.program_name,
        program_type=candidate.program_type,
        total_credit_hours=total_credit_hours,
        overlap_course_count=len(shared_ids),
        overlap_credit_hours=overlap_credit_hours,
        overlap_ratio=(overlap_credit_hours / total_credit_hours if total_credit_hours else None),
        overlap_courses=_sorted_preview(shared_ids, courses_by_id),
    )


def _sorted_preview(course_ids: set[int], courses_by_id: dict[int, CourseOut]) -> list[CourseOut]:
    """Return up to OVERLAP_PREVIEW_LIMIT of the given courses, sorted by subject then number."""
    courses = [courses_by_id[cid] for cid in course_ids if cid in courses_by_id]
    courses.sort(key=lambda c: (c.subject_code, c.course_number))
    return courses[:OVERLAP_PREVIEW_LIMIT]
