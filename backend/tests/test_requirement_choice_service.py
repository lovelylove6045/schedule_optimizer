"""Tests the elective decision points `requirement_choice_service` finds in real
Aerospace BS/minor requirement trees: the literal "MATH 1214 or MATH 1211"
alternative, credit-hour-based course groups, option truncation for broad pools,
and completed-coursework satisfaction."""

from app.models.student import Student
from app.models.student_credit import StudentCredit
from app.services import requirement_choice_service

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2
MATH_1214_CHOICE_LABEL = "MATH 1214 or MATH 1211"


def _choice_by_label(choices, label):
    """Find one choice by its exact label, or None."""
    return next((choice for choice in choices if choice.label == label), None)


def test_finds_the_literal_either_or_course_choice(db_session):
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])

    choice = _choice_by_label(choices, MATH_1214_CHOICE_LABEL)
    assert choice is not None
    assert choice.kind == "ANY_OF"
    assert choice.choose_count == 1
    assert choice.course_group_id is None
    assert choice.options_truncated is False
    codes = {f"{c.subject_code} {c.course_number}" for c in choice.options}
    assert codes == {"MATH 1214", "MATH 1211"}


def test_course_group_choice_reports_its_credit_hour_requirement(db_session):
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])

    # "MAE Technical Electives - 9 Credits": states its size in credit hours, not a
    # course count, which is how 240 of the catalog's 252 COURSE_GROUP nodes work.
    group_choices = [c for c in choices if c.kind == "COURSE_GROUP" and c.required_credit_hours == 9.0]
    assert group_choices, "Aerospace BS should have a 9-credit technical elective group"
    choice = group_choices[0]
    assert choice.course_group_id is not None
    assert choice.total_option_count > requirement_choice_service.INLINE_OPTION_LIMIT
    assert len(choice.options) == requirement_choice_service.INLINE_OPTION_LIMIT
    assert choice.options_truncated is True


def test_options_are_sorted_by_subject_then_number(db_session):
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])

    for choice in choices:
        keys = [(c.subject_code, c.course_number) for c in choice.options]
        assert keys == sorted(keys)


def test_every_choice_offers_at_least_two_options(db_session):
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])

    assert len(choices) > 0
    assert all(len(choice.options) >= 2 for choice in choices)


def test_completed_coursework_marks_a_choice_already_satisfied(db_session):
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])
    choice = _choice_by_label(choices, MATH_1214_CHOICE_LABEL)
    assert choice.already_satisfied is False
    picked_course_id = choice.options[0].course_id

    resolved = requirement_choice_service.list_requirement_choices(
        db_session, [AERO_BS_PROGRAM_ID], completed_course_ids={picked_course_id}
    )

    assert _choice_by_label(resolved, MATH_1214_CHOICE_LABEL).already_satisfied is True


def test_one_completed_course_does_not_satisfy_a_multi_credit_group(db_session):
    """A 9-credit elective group isn't settled by one 3-credit course -- the same rule
    `credit_matching_service._is_group_satisfied` applies."""
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])
    choice = next(c for c in choices if c.required_credit_hours == 9.0)
    one_member = choice.options[0]
    assert one_member.credit_hours < 9.0

    resolved = requirement_choice_service.list_requirement_choices(
        db_session, [AERO_BS_PROGRAM_ID], completed_course_ids={one_member.course_id}
    )

    assert next(c for c in resolved if c.requirement_node_id == choice.requirement_node_id).already_satisfied is False


def test_shared_requirement_nodes_are_not_duplicated_across_programs(db_session):
    """Aero BS and the Aero minor both attach the same gen-ed requirement set, so a
    choice inside it must be offered once, not twice."""
    choices = requirement_choice_service.list_requirement_choices(
        db_session, [AERO_BS_PROGRAM_ID, AERO_MINOR_PROGRAM_ID]
    )

    node_ids = [choice.requirement_node_id for choice in choices]
    assert len(node_ids) == len(set(node_ids))


def test_choices_carry_their_owning_program_and_requirement_set(db_session):
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])

    assert all(choice.academic_program_id == AERO_BS_PROGRAM_ID for choice in choices)
    assert all(choice.program_name for choice in choices)
    assert all(choice.requirement_set_name for choice in choices)


def test_no_programs_yields_no_choices(db_session):
    assert requirement_choice_service.list_requirement_choices(db_session, []) == []


def test_student_credits_are_not_consulted_directly(db_session):
    """The service takes completed course ids as an argument rather than reading
    `student_credits`, because the wizard asks these questions before a student row
    exists. A completed credit in the database alone must not change the result."""
    student = Student(display_name="Choice Student")
    db_session.add(student)
    db_session.flush()
    choices = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])
    choice = _choice_by_label(choices, MATH_1214_CHOICE_LABEL)
    db_session.add(
        StudentCredit(
            student_id=student.student_id,
            course_id=choice.options[0].course_id,
            source_type="INSTITUTIONAL",
            status="COMPLETED",
            grade="A",
        )
    )
    db_session.flush()

    unchanged = requirement_choice_service.list_requirement_choices(db_session, [AERO_BS_PROGRAM_ID])

    assert _choice_by_label(unchanged, MATH_1214_CHOICE_LABEL).already_satisfied is False
