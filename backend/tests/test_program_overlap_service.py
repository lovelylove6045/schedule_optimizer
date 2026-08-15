"""Tests program_overlap_service against the real Aerospace BS/minor catalog
data: the minor shares real courses with the major (a known good "add this
minor, it's mostly free" case), suggestions rank by coverage ratio, and the
program_type/limit filters behave as documented."""

from app.models.enums import ProgramType
from app.services import program_overlap_service

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2


def test_suggests_the_aero_minor_among_minor_suggestions(db_session):
    suggestions = program_overlap_service.suggest_overlapping_programs(
        db_session, AERO_BS_PROGRAM_ID, program_type=ProgramType.MINOR, limit=50
    )

    minor = next((s for s in suggestions if s.academic_program_id == AERO_MINOR_PROGRAM_ID), None)
    assert minor is not None
    assert minor.overlap_course_count > 0
    assert minor.overlap_credit_hours > 0
    assert minor.overlap_ratio is not None and minor.overlap_ratio > 0.5


def test_overlap_courses_are_capped_and_sorted(db_session):
    suggestions = program_overlap_service.suggest_overlapping_programs(
        db_session, AERO_BS_PROGRAM_ID, program_type=ProgramType.MINOR, limit=50
    )
    minor = next(s for s in suggestions if s.academic_program_id == AERO_MINOR_PROGRAM_ID)

    assert len(minor.overlap_courses) <= program_overlap_service.OVERLAP_PREVIEW_LIMIT
    codes = [(c.subject_code, c.course_number) for c in minor.overlap_courses]
    assert codes == sorted(codes)


def test_suggestions_are_sorted_by_coverage_ratio_descending(db_session):
    suggestions = program_overlap_service.suggest_overlapping_programs(db_session, AERO_BS_PROGRAM_ID, limit=50)

    ratios = [s.overlap_ratio or 0.0 for s in suggestions]
    assert ratios == sorted(ratios, reverse=True)
    assert all(s.overlap_course_count > 0 for s in suggestions)


def test_program_type_filter_narrows_results_to_minors(db_session):
    suggestions = program_overlap_service.suggest_overlapping_programs(
        db_session, AERO_BS_PROGRAM_ID, program_type=ProgramType.MINOR, limit=50
    )

    assert len(suggestions) > 0
    assert all(s.program_type == ProgramType.MINOR for s in suggestions)


def test_limit_caps_the_result_count(db_session):
    suggestions = program_overlap_service.suggest_overlapping_programs(db_session, AERO_BS_PROGRAM_ID, limit=1)

    assert len(suggestions) <= 1


def test_excludes_the_target_program_itself(db_session):
    suggestions = program_overlap_service.suggest_overlapping_programs(db_session, AERO_BS_PROGRAM_ID, limit=200)

    assert all(s.academic_program_id != AERO_BS_PROGRAM_ID for s in suggestions)


def test_unknown_program_yields_no_suggestions(db_session):
    assert program_overlap_service.suggest_overlapping_programs(db_session, 999_999) == []
