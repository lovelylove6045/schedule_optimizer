"""Tests scenario_service.create_scenario()'s validation rules and persistence
against real Aerospace BS catalog data."""

import pytest

from app.models.enums import OptimizationObjectiveType, ScenarioPreferenceType, ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_objective import ScenarioObjective
from app.models.scenario_preference import ScenarioPreference
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_term import ScenarioTerm
from app.models.student_credit import StudentCredit
from app.models.term import Term
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioObjectiveIn,
    ScenarioPreferenceIn,
    ScenarioProgramIn,
    ScenarioTermIn,
    StudentCreditIn,
)
from app.services import scenario_service
from app.services.scenario_service import ScenarioReferenceNotFoundError, ScenarioValidationError

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2
COMP_SCI_1972_COURSE_ID = 1122


def _two_terms(db_session) -> list[Term]:
    """Return the first two terms in chronological order, for start/override term ids."""
    return db_session.query(Term).order_by(Term.sequence_index.asc()).limit(2).all()


def test_create_scenario_persists_every_child_row(db_session):
    """A full submission (programs, completed course, term override, preference,
    objective) should persist one row per child table, linked to the new scenario."""
    start_term, override_term = _two_terms(db_session)
    payload = ScenarioCreate(
        student_display_name="Test Student",
        start_term_id=start_term.term_id,
        allow_summer=True,
        programs=[
            ScenarioProgramIn(academic_program_id=AERO_BS_PROGRAM_ID, program_role=ScenarioProgramRole.PRIMARY_MAJOR),
            ScenarioProgramIn(academic_program_id=AERO_MINOR_PROGRAM_ID, program_role=ScenarioProgramRole.MINOR),
        ],
        completed_courses=[StudentCreditIn(course_id=COMP_SCI_1972_COURSE_ID, status="COMPLETED", grade="A")],
        term_overrides=[ScenarioTermIn(term_id=override_term.term_id, maximum_credits=12)],
        preferences=[ScenarioPreferenceIn(preference_type=ScenarioPreferenceType.AVOID_COURSE, course_id=COMP_SCI_1972_COURSE_ID)],
        objectives=[ScenarioObjectiveIn(objective_type=OptimizationObjectiveType.EARLIEST_GRADUATION, display_order=0)],
    )

    scenario = scenario_service.create_scenario(db_session, payload)

    assert db_session.get(PlanningScenario, scenario.planning_scenario_id) is not None
    programs = db_session.query(ScenarioProgram).filter_by(planning_scenario_id=scenario.planning_scenario_id).all()
    assert len(programs) == 2
    credits = db_session.query(StudentCredit).filter_by(student_id=scenario.student_id).all()
    assert len(credits) == 1
    terms = db_session.query(ScenarioTerm).filter_by(planning_scenario_id=scenario.planning_scenario_id).all()
    assert len(terms) == 1
    preferences = db_session.query(ScenarioPreference).filter_by(planning_scenario_id=scenario.planning_scenario_id).all()
    assert len(preferences) == 1
    objectives = db_session.query(ScenarioObjective).filter_by(planning_scenario_id=scenario.planning_scenario_id).all()
    assert len(objectives) == 1


def test_create_scenario_rejects_zero_primary_majors(db_session):
    """A scenario with no PRIMARY_MAJOR program should raise ScenarioValidationError."""
    start_term = _two_terms(db_session)[0]
    payload = ScenarioCreate(
        start_term_id=start_term.term_id,
        programs=[ScenarioProgramIn(academic_program_id=AERO_MINOR_PROGRAM_ID, program_role=ScenarioProgramRole.MINOR)],
    )

    with pytest.raises(ScenarioValidationError):
        scenario_service.create_scenario(db_session, payload)


def test_create_scenario_rejects_two_primary_majors(db_session):
    """A scenario with two PRIMARY_MAJOR programs should raise ScenarioValidationError."""
    start_term = _two_terms(db_session)[0]
    payload = ScenarioCreate(
        start_term_id=start_term.term_id,
        programs=[
            ScenarioProgramIn(academic_program_id=AERO_BS_PROGRAM_ID, program_role=ScenarioProgramRole.PRIMARY_MAJOR),
            ScenarioProgramIn(academic_program_id=AERO_MINOR_PROGRAM_ID, program_role=ScenarioProgramRole.PRIMARY_MAJOR),
        ],
    )

    with pytest.raises(ScenarioValidationError):
        scenario_service.create_scenario(db_session, payload)


def test_create_scenario_rejects_unknown_program_id(db_session):
    """An unknown academic_program_id should raise ScenarioReferenceNotFoundError."""
    start_term = _two_terms(db_session)[0]
    payload = ScenarioCreate(
        start_term_id=start_term.term_id,
        programs=[ScenarioProgramIn(academic_program_id=999_999, program_role=ScenarioProgramRole.PRIMARY_MAJOR)],
    )

    with pytest.raises(ScenarioReferenceNotFoundError):
        scenario_service.create_scenario(db_session, payload)


def test_create_scenario_rejects_unknown_start_term_id(db_session):
    """An unknown start_term_id should raise ScenarioReferenceNotFoundError."""
    payload = ScenarioCreate(
        start_term_id=999_999,
        programs=[ScenarioProgramIn(academic_program_id=AERO_BS_PROGRAM_ID, program_role=ScenarioProgramRole.PRIMARY_MAJOR)],
    )

    with pytest.raises(ScenarioReferenceNotFoundError):
        scenario_service.create_scenario(db_session, payload)


def test_create_scenario_creates_a_new_student_when_none_given(db_session):
    """No student_id in the payload should create a brand-new Student row."""
    start_term = _two_terms(db_session)[0]
    payload = ScenarioCreate(
        student_display_name="Brand New Student",
        start_term_id=start_term.term_id,
        programs=[ScenarioProgramIn(academic_program_id=AERO_BS_PROGRAM_ID, program_role=ScenarioProgramRole.PRIMARY_MAJOR)],
    )

    scenario = scenario_service.create_scenario(db_session, payload)

    assert scenario.student_id is not None
