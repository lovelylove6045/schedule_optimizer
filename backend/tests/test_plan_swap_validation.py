"""Tests plan_swap_validation against real catalog course/prerequisite data:
term-offering eligibility, per-term credit caps (scenario default and
scenario_terms override), and prerequisite ordering against a plan's other
placements or the student's completed coursework."""

import pytest

from app.models.course import Course
from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_term import ScenarioTerm
from app.models.student import Student
from app.models.student_credit import StudentCredit
from app.services import plan_swap_validation

FALL_2026_TERM_ID = 1
SPRING_2027_TERM_ID = 2
FALL_2027_TERM_ID = 4
# A prerequisite-free, fall-offered, 3-credit course used as the generic
# "occupying" course throughout -- these tests are about the *new* course's
# eligibility, not this one's.
FILLER_COURSE_ID = 23
OTHER_FILLER_COURSE_ID = 24
THIRD_FILLER_COURSE_ID = 26
FOURTH_FILLER_COURSE_ID = 27
# ELEC ENG-style 4-credit, prerequisite-free, fall-offered course, for pushing
# a term over its credit cap.
FOUR_CREDIT_COURSE_ID = 41
# PSYCH 4993 "Psychology of Gender": fall-only, with PSYCH 1101 (course_id 839)
# as its one real PREREQUISITE root.
PSYCH_GENDER_COURSE_ID = 874
PSYCH_GENERAL_COURSE_ID = 839


def _make_plan(db_session, default_maximum_credits: float | None = None) -> DegreePlan:
    """Persist a bare scenario + degree plan for a fresh student."""
    student = Student(display_name="Swap Validation Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id, default_maximum_credits=default_maximum_credits)
    db_session.add(scenario)
    db_session.flush()
    plan = DegreePlan(planning_scenario_id=scenario.planning_scenario_id, status="DRAFT")
    db_session.add(plan)
    db_session.flush()
    return plan


def _add_plan_course(db_session, plan: DegreePlan, course_id: int, term_id: int) -> PlanCourse:
    """Persist one plan_courses row for `course_id` in `term_id`."""
    course = db_session.get(Course, course_id)
    plan_course = PlanCourse(
        degree_plan_id=plan.degree_plan_id, course_id=course_id, term_id=term_id, credit_hours=course.credit_hours
    )
    db_session.add(plan_course)
    db_session.flush()
    return plan_course


def test_rejects_a_course_not_offered_in_the_slots_term_type(db_session):
    plan = _make_plan(db_session)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, SPRING_2027_TERM_ID)
    new_course = db_session.get(Course, PSYCH_GENDER_COURSE_ID)

    with pytest.raises(plan_swap_validation.CourseNotOfferedInTermError):
        plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_allows_a_course_offered_in_the_slots_term_type(db_session):
    plan = _make_plan(db_session)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2026_TERM_ID)
    new_course = db_session.get(Course, OTHER_FILLER_COURSE_ID)

    plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_rejects_a_swap_that_would_push_the_term_over_its_default_credit_cap(db_session):
    plan = _make_plan(db_session, default_maximum_credits=12)
    _add_plan_course(db_session, plan, OTHER_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    _add_plan_course(db_session, plan, THIRD_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    _add_plan_course(db_session, plan, FOURTH_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2026_TERM_ID)
    new_course = db_session.get(Course, FOUR_CREDIT_COURSE_ID)

    with pytest.raises(plan_swap_validation.TermCreditCapExceededError):
        plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_allows_a_swap_that_stays_within_the_default_credit_cap(db_session):
    plan = _make_plan(db_session, default_maximum_credits=12)
    _add_plan_course(db_session, plan, OTHER_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    _add_plan_course(db_session, plan, THIRD_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2026_TERM_ID)
    new_course = db_session.get(Course, FOURTH_FILLER_COURSE_ID)

    plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_a_scenario_terms_override_takes_precedence_over_the_scenario_default(db_session):
    plan = _make_plan(db_session, default_maximum_credits=100)
    _add_plan_course(db_session, plan, OTHER_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2026_TERM_ID)
    scenario = db_session.get(PlanningScenario, plan.planning_scenario_id)
    db_session.add(
        ScenarioTerm(planning_scenario_id=scenario.planning_scenario_id, term_id=FALL_2026_TERM_ID, maximum_credits=5)
    )
    db_session.flush()
    new_course = db_session.get(Course, FOURTH_FILLER_COURSE_ID)

    with pytest.raises(plan_swap_validation.TermCreditCapExceededError):
        plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_no_credit_cap_set_never_blocks_a_swap(db_session):
    plan = _make_plan(db_session, default_maximum_credits=None)
    _add_plan_course(db_session, plan, OTHER_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    _add_plan_course(db_session, plan, THIRD_FILLER_COURSE_ID, FALL_2026_TERM_ID)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2026_TERM_ID)
    new_course = db_session.get(Course, FOUR_CREDIT_COURSE_ID)

    plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_rejects_a_course_whose_prerequisite_isnt_placed_or_completed(db_session):
    plan = _make_plan(db_session)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2027_TERM_ID)
    new_course = db_session.get(Course, PSYCH_GENDER_COURSE_ID)

    with pytest.raises(plan_swap_validation.PrerequisiteNotMetError):
        plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_allows_a_course_whose_prerequisite_is_placed_in_an_earlier_term(db_session):
    plan = _make_plan(db_session)
    _add_plan_course(db_session, plan, PSYCH_GENERAL_COURSE_ID, FALL_2026_TERM_ID)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2027_TERM_ID)
    new_course = db_session.get(Course, PSYCH_GENDER_COURSE_ID)

    plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_rejects_a_course_whose_prerequisite_is_only_placed_in_a_later_term(db_session):
    plan = _make_plan(db_session)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2026_TERM_ID)
    _add_plan_course(db_session, plan, PSYCH_GENERAL_COURSE_ID, FALL_2027_TERM_ID)
    new_course = db_session.get(Course, PSYCH_GENDER_COURSE_ID)

    with pytest.raises(plan_swap_validation.PrerequisiteNotMetError):
        plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_allows_a_course_whose_prerequisite_is_already_completed(db_session):
    plan = _make_plan(db_session)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2027_TERM_ID)
    scenario = db_session.get(PlanningScenario, plan.planning_scenario_id)
    db_session.add(
        StudentCredit(student_id=scenario.student_id, course_id=PSYCH_GENERAL_COURSE_ID, source_type="INSTITUTION", status="COMPLETED")
    )
    db_session.flush()
    new_course = db_session.get(Course, PSYCH_GENDER_COURSE_ID)

    plan_swap_validation.validate_swap(db_session, plan_course, new_course)


def test_a_course_with_no_prerequisites_always_passes_that_check(db_session):
    plan = _make_plan(db_session)
    plan_course = _add_plan_course(db_session, plan, FILLER_COURSE_ID, FALL_2026_TERM_ID)
    new_course = db_session.get(Course, OTHER_FILLER_COURSE_ID)

    plan_swap_validation.validate_swap(db_session, plan_course, new_course)
