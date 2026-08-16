"""Tests optimizer_candidates.py's candidate-course-universe building against real
Aerospace BS/minor catalog data: a clean single-program case, prerequisite-closure
growth capping, completed-course exclusion, and cross-program overlap detection."""

from app.models.academic_program import AcademicProgram
from app.models.course import Course
from app.models.enums import ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_program import ScenarioProgram
from app.models.student import Student
from app.models.student_credit import StudentCredit
from app.services import optimizer_candidates

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2  # heavy real overlap with Aero BS -- same department's minor
COMP_SCI_1972_COURSE_ID = 1122  # a real Aero BS programming-requirement course
AERO_ENG_4780_COURSE_ID = 1718  # has a 3-course PREREQUISITE tree (see test_catalog_service)


def _make_scenario(db_session, program_ids: list[int], student_id: int | None = None) -> PlanningScenario:
    """Create (unflushed-to-caller) a minimal PlanningScenario with the given
    scenario_programs, for a fresh student unless one is provided."""
    if student_id is None:
        student = Student(display_name="Test Student")
        db_session.add(student)
        db_session.flush()
        student_id = student.student_id
    scenario = PlanningScenario(student_id=student_id, allow_summer=True)
    db_session.add(scenario)
    db_session.flush()
    for index, program_id in enumerate(program_ids):
        role = ScenarioProgramRole.PRIMARY_MAJOR if index == 0 else ScenarioProgramRole.MINOR
        db_session.add(
            ScenarioProgram(
                planning_scenario_id=scenario.planning_scenario_id,
                academic_program_id=program_id,
                program_role=role,
            )
        )
    db_session.flush()
    return scenario


def test_build_candidate_course_set_includes_direct_requirement_courses(db_session):
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    assert len(result.requirement_sets) == 8
    assert COMP_SCI_1972_COURSE_ID in result.assignable_course_ids
    assert COMP_SCI_1972_COURSE_ID in result.courses_by_id


def test_build_candidate_course_set_excludes_completed_courses(db_session):
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    db_session.add(
        StudentCredit(
            student_id=student.student_id,
            course_id=COMP_SCI_1972_COURSE_ID,
            source_type="INSTITUTIONAL",
            status="COMPLETED",
            grade="A",
        )
    )
    db_session.flush()
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID], student_id=student.student_id)

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    assert COMP_SCI_1972_COURSE_ID in result.completed_course_ids
    assert COMP_SCI_1972_COURSE_ID not in result.assignable_course_ids


def test_build_candidate_course_set_does_not_cap_a_real_program(db_session):
    """The closure cap is a safety valve against a pathological expansion, not
    something a normal degree should trip. Aerospace BS's full prerequisite closure
    is 88 extra courses over 3 levels; when MAX_CLOSURE_GROWTH was 60 it bound here,
    and every generated plan carried ~24 "prerequisite excluded by the cap" warnings
    for prerequisites the model simply hadn't looked at."""
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    direct_course_ids: set[int] = set()
    for course_ids in result.course_ids_by_program.values():
        direct_course_ids |= course_ids
    closure_growth = result.assignable_course_ids - direct_course_ids
    assert result.closure_capped is False
    assert 0 < len(closure_growth) <= optimizer_candidates.MAX_CLOSURE_GROWTH


def test_expand_prerequisite_closure_caps_growth_and_is_deterministic(db_session, monkeypatch):
    """With the cap lowered far enough to bind, expansion stops at the cap and
    truncates in sorted id order (so the same scenario always yields the same
    candidate set, rather than depending on set iteration order)."""
    monkeypatch.setattr(optimizer_candidates, "MAX_CLOSURE_GROWTH", 5)
    seed_course_ids = {COMP_SCI_1972_COURSE_ID, AERO_ENG_4780_COURSE_ID}

    first, first_capped = optimizer_candidates._expand_prerequisite_closure(db_session, seed_course_ids, set())
    second, second_capped = optimizer_candidates._expand_prerequisite_closure(db_session, seed_course_ids, set())

    assert first_capped is True and second_capped is True
    assert len(first - seed_course_ids) == 5
    assert first == second


def test_course_ids_by_program_detects_real_cross_program_overlap(db_session):
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID, AERO_MINOR_PROGRAM_ID])

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    assert set(result.course_ids_by_program.keys()) == {AERO_BS_PROGRAM_ID, AERO_MINOR_PROGRAM_ID}
    shared = result.course_ids_by_program[AERO_BS_PROGRAM_ID] & result.course_ids_by_program[AERO_MINOR_PROGRAM_ID]
    assert len(shared) > 0, "Aero BS and its own department's minor should share at least one course"


def test_build_candidate_course_set_empty_for_no_programs(db_session):
    scenario = _make_scenario(db_session, [])

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    assert result.requirement_sets == []
    assert result.assignable_course_ids == set()


def test_credit_floor_remaining_matches_the_primary_programs_published_total(db_session):
    """A fresh student with no completed courses should see credit_floor_remaining
    equal to the primary major's own published total_credit_hours."""
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])
    program = db_session.get(AcademicProgram, AERO_BS_PROGRAM_ID)

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    assert result.credit_floor_remaining == float(program.total_credit_hours)


def test_credit_floor_remaining_is_reduced_by_completed_credit_hours(db_session):
    """Credits the student already earned should count against the remaining floor."""
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    db_session.add(
        StudentCredit(
            student_id=student.student_id,
            course_id=COMP_SCI_1972_COURSE_ID,
            source_type="INSTITUTIONAL",
            status="COMPLETED",
            credits_earned=3,
            grade="A",
        )
    )
    db_session.flush()
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID], student_id=student.student_id)
    program = db_session.get(AcademicProgram, AERO_BS_PROGRAM_ID)

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    assert result.credit_floor_remaining == float(program.total_credit_hours) - 3


def test_unrelated_completed_course_does_not_reduce_degree_credit_floor(db_session):
    """Keep unrelated completed coursework out of conservative degree-progress credits."""
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID], student.student_id)
    candidate_ids = optimizer_candidates.build_candidate_course_set(db_session, scenario).assignable_course_ids
    unrelated_course_id = next(
        course_id
        for (course_id,) in db_session.query(Course.course_id).order_by(Course.course_id).all()
        if course_id not in candidate_ids
    )
    db_session.add(
        StudentCredit(
            student_id=student.student_id,
            course_id=unrelated_course_id,
            source_type="INSTITUTIONAL",
            status="COMPLETED",
            credits_earned=3,
        )
    )
    db_session.flush()
    program = db_session.get(AcademicProgram, AERO_BS_PROGRAM_ID)
    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)
    assert result.credit_floor_remaining == float(program.total_credit_hours)


def test_credit_floor_remaining_is_none_without_a_major_role_program(db_session):
    """A scenario with only a MINOR-role program has no bachelor's-level graduation
    total to enforce, so credit_floor_remaining should be None."""
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(student_id=student.student_id, allow_summer=True)
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioProgram(
            planning_scenario_id=scenario.planning_scenario_id,
            academic_program_id=AERO_MINOR_PROGRAM_ID,
            program_role=ScenarioProgramRole.MINOR,
        )
    )
    db_session.flush()

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    assert result.credit_floor_remaining is None
