"""Validates and persists one `POST /scenarios` submission: the design doc's
Section 9.2 rule ("exactly one PRIMARY_MAJOR per planning scenario") plus every
referenced program/term id, then inserts the `planning_scenarios` row and its
child rows (`scenario_programs`, `student_credits`, `scenario_terms`,
`scenario_preferences`, `scenario_objectives`). Only flushes, never commits --
the caller (the API request via `app.database.get_db`, or a test's rollback
fixture) owns the transaction boundary."""

from __future__ import annotations

from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models.academic_program import AcademicProgram
from app.models.enums import ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_objective import ScenarioObjective
from app.models.scenario_preference import ScenarioPreference
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_term import ScenarioTerm
from app.models.student import Student
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


class ScenarioValidationError(ValueError):
    """A scenario submission violates a business rule (not a missing reference)."""


class ScenarioReferenceNotFoundError(ValueError):
    """A scenario submission references a program/term/student id that doesn't exist."""


def create_scenario(db: Session, payload: ScenarioCreate) -> PlanningScenario:
    """Validate and persist one planning scenario submission, returning the new
    `PlanningScenario` row. Raises `ScenarioValidationError` for business-rule
    violations and `ScenarioReferenceNotFoundError` for missing program/term/
    student ids -- the router translates these into 422/404 responses."""
    _validate_exactly_one_primary_major(payload.programs)
    _validate_programs_exist(db, payload.programs)
    _validate_terms_exist(db, payload)
    student_id = _resolve_student_id(db, payload)
    scenario = _create_planning_scenario(db, payload, student_id)
    db.flush()
    _create_scenario_programs(db, scenario.planning_scenario_id, payload.programs)
    _create_student_credits(db, student_id, payload.completed_courses)
    _create_scenario_terms(db, scenario.planning_scenario_id, payload.term_overrides)
    _create_scenario_preferences(db, scenario.planning_scenario_id, payload.preferences)
    _create_scenario_objectives(db, scenario.planning_scenario_id, payload.objectives)
    db.flush()
    return scenario


def _validate_exactly_one_primary_major(programs: list[ScenarioProgramIn]) -> None:
    """Enforce the design doc's rule that a scenario has exactly one PRIMARY_MAJOR."""
    primary_count = sum(1 for program in programs if program.program_role == ScenarioProgramRole.PRIMARY_MAJOR)
    if primary_count != 1:
        raise ScenarioValidationError(
            f"A scenario must have exactly one PRIMARY_MAJOR program, got {primary_count}."
        )


def _validate_programs_exist(db: Session, programs: list[ScenarioProgramIn]) -> None:
    """Raise `ScenarioReferenceNotFoundError` if any referenced academic_program_id is unknown."""
    requested_ids = {program.academic_program_id for program in programs}
    found_ids = _existing_ids(db, AcademicProgram.academic_program_id, requested_ids)
    missing_ids = requested_ids - found_ids
    if missing_ids:
        raise ScenarioReferenceNotFoundError(f"Unknown academic_program_id(s): {sorted(missing_ids)}")


def _validate_terms_exist(db: Session, payload: ScenarioCreate) -> None:
    """Raise `ScenarioReferenceNotFoundError` if start/target/override term ids are unknown."""
    requested_ids = {payload.start_term_id} | {t.term_id for t in payload.term_overrides}
    if payload.target_graduation_term_id is not None:
        requested_ids.add(payload.target_graduation_term_id)
    found_ids = _existing_ids(db, Term.term_id, requested_ids)
    missing_ids = requested_ids - found_ids
    if missing_ids:
        raise ScenarioReferenceNotFoundError(f"Unknown term_id(s): {sorted(missing_ids)}")


def _existing_ids(db: Session, column: InstrumentedAttribute, requested_ids: set[int]) -> set[int]:
    """Return the subset of `requested_ids` that actually exist in `column`'s table."""
    if not requested_ids:
        return set()
    rows = db.query(column).filter(column.in_(requested_ids)).all()
    return {row[0] for row in rows}


def _resolve_student_id(db: Session, payload: ScenarioCreate) -> int:
    """Return an existing student_id (validated) or create a new `Student` row."""
    if payload.student_id is None:
        student = Student(display_name=payload.student_display_name)
        db.add(student)
        db.flush()
        return student.student_id
    if db.get(Student, payload.student_id) is None:
        raise ScenarioReferenceNotFoundError(f"Unknown student_id: {payload.student_id}")
    return payload.student_id


def _create_planning_scenario(db: Session, payload: ScenarioCreate, student_id: int) -> PlanningScenario:
    """Insert (unflushed) the `planning_scenarios` row itself."""
    scenario = PlanningScenario(
        student_id=student_id,
        start_term_id=payload.start_term_id,
        target_graduation_term_id=payload.target_graduation_term_id,
        default_minimum_credits=payload.default_minimum_credits,
        default_maximum_credits=payload.default_maximum_credits,
        full_time_minimum_credits=payload.full_time_minimum_credits,
        allow_summer=payload.allow_summer,
    )
    db.add(scenario)
    return scenario


def _create_scenario_programs(db: Session, planning_scenario_id: int, programs: list[ScenarioProgramIn]) -> None:
    """Insert one `scenario_programs` row per selected program."""
    for program in programs:
        db.add(
            ScenarioProgram(
                planning_scenario_id=planning_scenario_id,
                academic_program_id=program.academic_program_id,
                program_role=program.program_role,
            )
        )


def _create_student_credits(db: Session, student_id: int, completed_courses: list[StudentCreditIn]) -> None:
    """Insert one `student_credits` row per reported completed/in-progress/transfer course."""
    for credit in completed_courses:
        db.add(
            StudentCredit(
                student_id=student_id,
                course_id=credit.course_id,
                source_type=credit.source_type,
                status=credit.status,
                term_id=credit.term_id,
                external_course_code=credit.external_course_code,
                external_course_title=credit.external_course_title,
                credits_earned=credit.credits_earned,
                grade=credit.grade,
                is_in_residence=credit.is_in_residence,
            )
        )


def _create_scenario_terms(db: Session, planning_scenario_id: int, term_overrides: list[ScenarioTermIn]) -> None:
    """Insert one `scenario_terms` row per per-term override."""
    for term_override in term_overrides:
        db.add(
            ScenarioTerm(
                planning_scenario_id=planning_scenario_id,
                term_id=term_override.term_id,
                minimum_credits=term_override.minimum_credits,
                maximum_credits=term_override.maximum_credits,
                is_excluded=term_override.is_excluded,
            )
        )


def _create_scenario_preferences(
    db: Session, planning_scenario_id: int, preferences: list[ScenarioPreferenceIn]
) -> None:
    """Insert one `scenario_preferences` row per soft/hard preference."""
    for preference in preferences:
        db.add(
            ScenarioPreference(
                planning_scenario_id=planning_scenario_id,
                preference_type=preference.preference_type,
                course_id=preference.course_id,
                term_id=preference.term_id,
                weight=preference.weight,
            )
        )


def _create_scenario_objectives(
    db: Session, planning_scenario_id: int, objectives: list[ScenarioObjectiveIn]
) -> None:
    """Insert one `scenario_objectives` row per selected/ranked objective."""
    for objective in objectives:
        db.add(
            ScenarioObjective(
                planning_scenario_id=planning_scenario_id,
                objective_type=objective.objective_type,
                weight=objective.weight,
                display_order=objective.display_order,
            )
        )
