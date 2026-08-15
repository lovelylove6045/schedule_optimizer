"""Writes one solver-generated `optimizer_service.GeneratedPlan` out to `degree_plans`
plus its `plan_courses`, `requirement_allocations` (including already-completed
`student_credits` allocations), and `optimization_messages`. A course satisfying more
than one requirement node is represented by multiple `requirement_allocations` rows
pointing at the same `plan_course`/`student_credit` -- the schema has no separate
`is_shared` flag, so that's how double counting shows up.

`persist_plan` only flushes, never commits: like the rest of this codebase's request-
scoped `Session` (see `app/database.py`), committing is the caller's decision (the
Phase 4 API route, or a test's transaction-rollback fixture)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.degree_plan import DegreePlan
from app.models.optimization_message import OptimizationMessage
from app.models.plan_course import PlanCourse
from app.models.requirement_allocation import RequirementAllocation
from app.models.student_credit import StudentCredit
from app.schemas.course import CourseOut
from app.schemas.plan import DegreePlanOut, OptimizationMessageOut, PlanCourseOut
from app.services.common import load_courses_by_id
from app.services.credit_matching_service import COMPLETED_STATUS
from app.services.optimizer_service import GeneratedPlan

INFEASIBLE_STATUS = "INFEASIBLE"
DRAFT_STATUS = "DRAFT"


def persist_plan(
    db: Session, planning_scenario_id: int, student_id: int, generated_plan: GeneratedPlan
) -> DegreePlan:
    """Persist (flush, not commit) one `GeneratedPlan`: a `degree_plans` row, its
    `plan_courses`/`requirement_allocations` (skipped if infeasible), and any
    `optimization_messages`."""
    plan = _create_degree_plan(db, planning_scenario_id, generated_plan)
    db.flush()
    if generated_plan.infeasibility_reason is not None:
        _add_message(db, plan.degree_plan_id, "ERROR", "INFEASIBLE", generated_plan.infeasibility_reason)
        db.flush()
        return plan
    plan_courses_by_course_id = _create_plan_courses(db, plan.degree_plan_id, generated_plan)
    db.flush()
    _create_requirement_allocations(db, plan.degree_plan_id, student_id, generated_plan, plan_courses_by_course_id)
    _add_diagnostic_messages(db, plan.degree_plan_id, generated_plan)
    db.flush()
    return plan


def _create_degree_plan(db: Session, planning_scenario_id: int, generated_plan: GeneratedPlan) -> DegreePlan:
    """Insert (unflushed) the `degree_plans` row summarizing one generated plan. The
    strategy label lives in `plan_name` -- the schema has no dedicated strategy_code column."""
    plan = DegreePlan(
        planning_scenario_id=planning_scenario_id,
        plan_name=generated_plan.strategy_code,
        status=INFEASIBLE_STATUS if generated_plan.infeasibility_reason is not None else DRAFT_STATUS,
        total_credit_hours=generated_plan.total_credit_hours or None,
        additional_credit_hours=generated_plan.additional_credit_hours,
        projected_graduation_term_id=generated_plan.projected_graduation_term_id,
        solver_status=generated_plan.status,
    )
    db.add(plan)
    return plan


def _create_plan_courses(
    db: Session, degree_plan_id: int, generated_plan: GeneratedPlan
) -> dict[int, PlanCourse]:
    """Insert (unflushed) one `plan_courses` row per assigned course, returning them
    keyed by course_id for the requirement_allocations step."""
    plan_courses_by_course_id: dict[int, PlanCourse] = {}
    for course_id, term_id in generated_plan.assignments.items():
        plan_course = PlanCourse(
            degree_plan_id=degree_plan_id,
            course_id=course_id,
            term_id=term_id,
            credit_hours=generated_plan.courses_by_id[course_id].credit_hours,
        )
        db.add(plan_course)
        plan_courses_by_course_id[course_id] = plan_course
    return plan_courses_by_course_id


def _create_requirement_allocations(
    db: Session,
    degree_plan_id: int,
    student_id: int,
    generated_plan: GeneratedPlan,
    plan_courses_by_course_id: dict[int, PlanCourse],
) -> None:
    """Insert one `requirement_allocations` row per (node, satisfying course) pair."""
    completed_credit_by_course_id = _completed_credit_by_course_id(db, student_id)
    for node_id, course_ids in generated_plan.node_satisfying_course_ids.items():
        for course_id in course_ids:
            _add_one_requirement_allocation(
                db, degree_plan_id, node_id, course_id, plan_courses_by_course_id, completed_credit_by_course_id
            )


def _completed_credit_by_course_id(db: Session, student_id: int) -> dict[int, StudentCredit]:
    """Return the student's completed `student_credits` rows, keyed by course_id."""
    rows = (
        db.query(StudentCredit)
        .filter(StudentCredit.student_id == student_id, StudentCredit.status == COMPLETED_STATUS)
        .all()
    )
    return {row.course_id: row for row in rows if row.course_id is not None}


def _add_one_requirement_allocation(
    db: Session,
    degree_plan_id: int,
    requirement_node_id: int,
    course_id: int,
    plan_courses_by_course_id: dict[int, PlanCourse],
    completed_credit_by_course_id: dict[int, StudentCredit],
) -> None:
    """Insert one `requirement_allocations` row, linking to whichever of the newly
    assigned `plan_courses` or the student's own `student_credits` accounts for this course."""
    plan_course = plan_courses_by_course_id.get(course_id)
    student_credit = completed_credit_by_course_id.get(course_id)
    if plan_course is None and student_credit is None:
        return
    db.add(
        RequirementAllocation(
            degree_plan_id=degree_plan_id,
            requirement_node_id=requirement_node_id,
            plan_course_id=plan_course.plan_course_id if plan_course else None,
            student_credit_id=student_credit.student_credit_id if student_credit else None,
            credit_hours_applied=_allocation_credit_hours(plan_course, student_credit),
        )
    )


def _allocation_credit_hours(
    plan_course: PlanCourse | None, student_credit: StudentCredit | None
) -> float | None:
    """Return the credit hours to record for one `requirement_allocations` row."""
    if plan_course is not None:
        return plan_course.credit_hours
    if student_credit is not None:
        return student_credit.credits_earned
    return None


def _add_diagnostic_messages(db: Session, degree_plan_id: int, generated_plan: GeneratedPlan) -> None:
    """Add one `optimization_messages` row per advisor-signoff or unmodeled-prerequisite caveat."""
    for node_id in generated_plan.credit_requirement_node_ids:
        _add_message(
            db,
            degree_plan_id,
            "WARNING",
            "ADVISOR_SIGNOFF_NEEDED",
            "This plan assumes a CREDIT_REQUIREMENT-type requirement (e.g. an unlisted "
            "ROTC/placeholder credit slot) is satisfied outside the tool; an advisor should confirm it.",
            requirement_node_id=node_id,
        )
    for course_id in generated_plan.unmodeled_prerequisite_course_ids:
        _add_message(
            db,
            degree_plan_id,
            "WARNING",
            "PREREQUISITE_CLOSURE_CAPPED",
            "A prerequisite course for this plan was excluded from the candidate set by the "
            "closure growth cap; this plan assumes it's satisfiable and should be double-checked.",
            course_id=course_id,
        )
    if generated_plan.unmodeled_prerequisite_node_ids:
        _add_message(
            db,
            degree_plan_id,
            "INFO",
            "UNVERIFIED_PREREQUISITE_TYPE",
            f"{len(generated_plan.unmodeled_prerequisite_node_ids)} prerequisite condition(s) "
            "(standing, exam, consent, or similar) can't be verified by the solver and are "
            "assumed satisfied; confirm with an advisor.",
        )


def _add_message(
    db: Session,
    degree_plan_id: int,
    severity: str,
    message_code: str,
    message_text: str,
    requirement_node_id: int | None = None,
    course_id: int | None = None,
) -> None:
    """Insert one `optimization_messages` row (unflushed)."""
    db.add(
        OptimizationMessage(
            degree_plan_id=degree_plan_id,
            severity=severity,
            message_code=message_code,
            message_text=message_text,
            requirement_node_id=requirement_node_id,
            course_id=course_id,
        )
    )


def load_degree_plan(db: Session, degree_plan_id: int) -> DegreePlanOut | None:
    """Read a persisted `DegreePlan` back out, with its courses and messages, as a
    `DegreePlanOut` (used by tests now, and Phase 4's API layer later)."""
    plan = db.get(DegreePlan, degree_plan_id)
    if plan is None:
        return None
    courses_by_id = _load_plan_course_details(db, degree_plan_id)
    return DegreePlanOut(
        degree_plan_id=plan.degree_plan_id,
        planning_scenario_id=plan.planning_scenario_id,
        plan_name=plan.plan_name,
        status=plan.status,
        total_credit_hours=plan.total_credit_hours,
        additional_credit_hours=plan.additional_credit_hours,
        projected_graduation_term_id=plan.projected_graduation_term_id,
        solver_objective_value=plan.solver_objective_value,
        solver_status=plan.solver_status,
        courses=courses_by_id,
        messages=_load_plan_messages(db, degree_plan_id),
    )


def _load_plan_course_details(db: Session, degree_plan_id: int) -> list[PlanCourseOut]:
    """Load one `PlanCourseOut` (with its full course) per `plan_courses` row on this plan."""
    plan_courses = db.query(PlanCourse).filter(PlanCourse.degree_plan_id == degree_plan_id).all()
    courses_by_id = load_courses_by_id(db, {pc.course_id for pc in plan_courses})
    return [_plan_course_out(pc, courses_by_id) for pc in plan_courses]


def _plan_course_out(plan_course: PlanCourse, courses_by_id: dict[int, CourseOut]) -> PlanCourseOut:
    """Convert one `PlanCourse` ORM row plus its already-joined course into a `PlanCourseOut`."""
    return PlanCourseOut(
        plan_course_id=plan_course.plan_course_id,
        course=courses_by_id[plan_course.course_id],
        term_id=plan_course.term_id,
        credit_hours=plan_course.credit_hours,
        placement_source=plan_course.placement_source,
    )


def _load_plan_messages(db: Session, degree_plan_id: int) -> list[OptimizationMessageOut]:
    """Load every `optimization_messages` row for this plan as `OptimizationMessageOut`."""
    rows = db.query(OptimizationMessage).filter(OptimizationMessage.degree_plan_id == degree_plan_id).all()
    return [OptimizationMessageOut.model_validate(row) for row in rows]
