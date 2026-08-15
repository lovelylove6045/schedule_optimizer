"""Lets a student directly edit one course slot in an already-generated plan
without re-running the solver: swap it for an alternative, add a brand-new
course to a term, or remove one entirely.

Swapping mutates the existing `plan_courses` row in place rather than
deleting/recreating it, so its `requirement_allocations` rows (which point at
plan_course_id, not course_id) keep tracking the same requirement node
without any extra bookkeeping. Adding creates a new row with no
`requirement_allocations` of its own -- like the solver's own
beyond-requirement electives, it just adds to the plan's credit totals.
Removing deletes both the row and its `requirement_allocations`.

Every add/swap is checked against `plan_swap_validation` first --
offered-in-term, the term's credit cap, and prerequisite ordering -- so a
manual edit can't produce a schedule the solver itself would have rejected."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.requirement_allocation import RequirementAllocation
from app.models.term import Term
from app.services import plan_swap_validation

STUDENT_SWAP_SOURCE = "STUDENT_SWAP"
STUDENT_ADDED_SOURCE = "STUDENT_ADDED"


class PlanCourseNotFoundError(Exception):
    """Raised when an edit targets a plan_course_id that isn't part of the given plan."""


class DegreePlanNotFoundError(Exception):
    """Raised when an edit targets a degree_plan_id that doesn't exist."""


class TermNotFoundError(Exception):
    """Raised when an add targets a term_id that doesn't exist."""


class CourseNotFoundError(Exception):
    """Raised when a swap/add's course_id doesn't exist in the catalog."""


class DuplicateCourseError(Exception):
    """Raised when the requested course is already assigned elsewhere in the same plan."""


def swap_plan_course(db: Session, degree_plan_id: int, plan_course_id: int, new_course_id: int) -> DegreePlan:
    """Replace the course assigned to one `plan_courses` row with
    `new_course_id`, keeping its term unchanged, and return the updated plan."""
    plan_course = _load_plan_course(db, degree_plan_id, plan_course_id)
    new_course = _load_course(db, new_course_id)
    _check_not_duplicate(db, degree_plan_id, new_course_id, exclude_plan_course_id=plan_course_id)
    plan_swap_validation.validate_swap(db, plan_course, new_course)
    credit_delta = float(new_course.credit_hours) - float(plan_course.credit_hours)
    plan_course.course_id = new_course_id
    plan_course.credit_hours = new_course.credit_hours
    plan_course.placement_source = STUDENT_SWAP_SOURCE
    _sync_allocation_credit(db, plan_course_id, new_course.credit_hours)
    plan = db.get(DegreePlan, degree_plan_id)
    _apply_credit_delta(plan, credit_delta)
    db.flush()
    return plan


def add_plan_course(db: Session, degree_plan_id: int, course_id: int, term_id: int) -> DegreePlan:
    """Add `course_id` to `degree_plan_id` in `term_id` as a brand-new slot --
    e.g. an extra elective the student wants beyond what the solver assigned --
    and return the updated plan."""
    plan = _load_degree_plan(db, degree_plan_id)
    term = _load_term(db, term_id)
    course = _load_course(db, course_id)
    _check_not_duplicate(db, degree_plan_id, course_id, exclude_plan_course_id=None)
    plan_swap_validation.validate_add(db, degree_plan_id, term.term_id, course)
    plan_course = PlanCourse(
        degree_plan_id=degree_plan_id,
        course_id=course_id,
        term_id=term.term_id,
        credit_hours=course.credit_hours,
        placement_source=STUDENT_ADDED_SOURCE,
    )
    db.add(plan_course)
    _apply_credit_delta(plan, float(course.credit_hours))
    db.flush()
    return plan


def remove_plan_course(db: Session, degree_plan_id: int, plan_course_id: int) -> DegreePlan:
    """Remove one `plan_courses` row entirely -- a solver-assigned or student-
    added course the student no longer wants -- deleting its
    `requirement_allocations` rows too (the FK would otherwise block the
    delete) and adjusting the plan's cached credit totals. Doesn't try to
    re-satisfy whatever requirement node the course was counted against; like
    a swap, this is a deliberate student action."""
    plan_course = _load_plan_course(db, degree_plan_id, plan_course_id)
    plan = db.get(DegreePlan, degree_plan_id)
    credit_hours = float(plan_course.credit_hours)
    db.query(RequirementAllocation).filter(RequirementAllocation.plan_course_id == plan_course_id).delete()
    db.delete(plan_course)
    _apply_credit_delta(plan, -credit_hours)
    db.flush()
    return plan


def _load_plan_course(db: Session, degree_plan_id: int, plan_course_id: int) -> PlanCourse:
    """Return the plan_courses row, raising if it doesn't belong to this plan."""
    plan_course = db.get(PlanCourse, plan_course_id)
    if plan_course is None or plan_course.degree_plan_id != degree_plan_id:
        raise PlanCourseNotFoundError(f"Plan course {plan_course_id} not found on plan {degree_plan_id}")
    return plan_course


def _load_degree_plan(db: Session, degree_plan_id: int) -> DegreePlan:
    """Return the degree_plans row, raising if it doesn't exist."""
    plan = db.get(DegreePlan, degree_plan_id)
    if plan is None:
        raise DegreePlanNotFoundError(f"Plan {degree_plan_id} not found")
    return plan


def _load_term(db: Session, term_id: int) -> Term:
    """Return the terms row, raising if it doesn't exist."""
    term = db.get(Term, term_id)
    if term is None:
        raise TermNotFoundError(f"Term {term_id} not found")
    return term


def _load_course(db: Session, course_id: int) -> Course:
    """Return the courses row, raising if it doesn't exist."""
    course = db.get(Course, course_id)
    if course is None:
        raise CourseNotFoundError(f"Course {course_id} not found")
    return course


def _check_not_duplicate(
    db: Session, degree_plan_id: int, new_course_id: int, exclude_plan_course_id: int | None
) -> None:
    """Raise if `new_course_id` is already assigned to a different slot on this plan."""
    query = db.query(PlanCourse.plan_course_id).filter(
        PlanCourse.degree_plan_id == degree_plan_id, PlanCourse.course_id == new_course_id
    )
    if exclude_plan_course_id is not None:
        query = query.filter(PlanCourse.plan_course_id != exclude_plan_course_id)
    if query.first() is not None:
        raise DuplicateCourseError(f"Course {new_course_id} is already in this plan")


def _sync_allocation_credit(db: Session, plan_course_id: int, credit_hours: float) -> None:
    """Keep every requirement_allocations row's stored credit in sync with its
    plan_course after a swap; the row's FK still points at the same node."""
    db.query(RequirementAllocation).filter(RequirementAllocation.plan_course_id == plan_course_id).update(
        {RequirementAllocation.credit_hours_applied: credit_hours}
    )


def _apply_credit_delta(plan: DegreePlan, credit_delta: float) -> None:
    """Adjust the plan's cached credit totals by an edit's credit-hour delta."""
    if plan.total_credit_hours is not None:
        plan.total_credit_hours = float(plan.total_credit_hours) + credit_delta
    if plan.additional_credit_hours is not None:
        plan.additional_credit_hours = float(plan.additional_credit_hours) + credit_delta
