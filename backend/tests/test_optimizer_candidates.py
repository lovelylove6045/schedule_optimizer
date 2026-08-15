"""Tests optimizer_candidates.py's candidate-course-universe building against real
Aerospace BS/minor catalog data: a clean single-program case, prerequisite-closure
growth capping, completed-course exclusion, and cross-program overlap detection."""

from app.models.enums import ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_program import ScenarioProgram
from app.models.student import Student
from app.models.student_credit import StudentCredit
from app.services import optimizer_candidates

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2  # heavy real overlap with Aero BS -- same department's minor
COMP_SCI_1972_COURSE_ID = 1122  # a real Aero BS programming-requirement course


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


def test_build_candidate_course_set_caps_prerequisite_closure_growth(db_session):
    scenario = _make_scenario(db_session, [AERO_BS_PROGRAM_ID])

    result = optimizer_candidates.build_candidate_course_set(db_session, scenario)

    direct_course_ids: set[int] = set()
    for course_ids in result.course_ids_by_program.values():
        direct_course_ids |= course_ids
    closure_growth = result.assignable_course_ids - direct_course_ids
    assert result.closure_capped is True
    assert len(closure_growth) <= optimizer_candidates.MAX_CLOSURE_GROWTH


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
