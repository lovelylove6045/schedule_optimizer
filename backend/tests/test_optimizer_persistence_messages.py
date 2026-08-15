"""Tests how `optimizer_persistence` turns a plan's caveats into
`optimization_messages` rows. The point of these is aggregation: each caveat gets
exactly one row no matter how many nodes/courses it covers, because emitting one
row per item produced 25 near-identical warnings on a real Aerospace BS plan."""

from app.models.enums import ScenarioPreferenceType, ScenarioProgramRole
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_preference import ScenarioPreference
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_term import ScenarioTerm
from app.models.student import Student
from app.services import optimizer_persistence
from app.services.optimizer_service import GeneratedPlan

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2
AERO_ENG_3251_COURSE_ID = 1709
AERO_ENG_3361_COURSE_ID = 1710
AERO_ENG_3171_COURSE_ID = 1708


def _make_scenario(db_session, **overrides) -> tuple[int, int]:
    """Create a minimal scenario and return its (planning_scenario_id, student_id)."""
    student = Student(display_name="Message Student")
    db_session.add(student)
    db_session.flush()
    scenario = PlanningScenario(
        student_id=student.student_id,
        start_term_id=overrides.pop("start_term_id", 1),
        allow_summer=overrides.pop("allow_summer", True),
        **overrides,
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioProgram(
            planning_scenario_id=scenario.planning_scenario_id,
            academic_program_id=AERO_BS_PROGRAM_ID,
            program_role=ScenarioProgramRole.PRIMARY_MAJOR,
        )
    )
    db_session.flush()
    return scenario.planning_scenario_id, student.student_id


def _plan(**overrides) -> GeneratedPlan:
    """Build a feasible, assignment-free GeneratedPlan carrying only the caveats
    a test cares about."""
    defaults = dict(
        strategy_code="EARLIEST_GRADUATION",
        objective_type=None,
        status="OPTIMAL",
        assignments={},
        courses_by_id={},
        total_credit_hours=0.0,
        additional_credit_hours=None,
        projected_graduation_term_id=None,
        node_satisfaction={},
        node_satisfying_course_ids={},
        credit_requirement_node_ids=set(),
        unmodeled_prerequisite_course_ids=set(),
        unmodeled_prerequisite_node_ids=set(),
        infeasibility_reason=None,
    )
    return GeneratedPlan(**{**defaults, **overrides})


def _messages(db_session, scenario_id: int, student_id: int, plan: GeneratedPlan):
    """Persist one plan and read its messages back."""
    saved = optimizer_persistence.persist_plan(db_session, scenario_id, student_id, plan)
    loaded = optimizer_persistence.load_degree_plan(db_session, saved.degree_plan_id)
    return loaded.messages


def test_many_unmodeled_prerequisites_produce_one_message_naming_courses(db_session):
    scenario_id, student_id = _make_scenario(db_session)
    plan = _plan(
        unmodeled_prerequisite_course_ids={
            AERO_ENG_3251_COURSE_ID,
            AERO_ENG_3361_COURSE_ID,
            AERO_ENG_3171_COURSE_ID,
        }
    )

    messages = _messages(db_session, scenario_id, student_id, plan)

    capped = [m for m in messages if m.message_code == "PREREQUISITE_NOT_MODELED"]
    assert len(capped) == 1
    assert capped[0].severity == "WARNING"
    assert "3 prerequisite course(s)" in capped[0].message_text
    assert "AERO ENG 3251" in capped[0].message_text


def test_unmodeled_prerequisite_message_truncates_a_long_course_list(db_session):
    scenario_id, student_id = _make_scenario(db_session)
    plan = _plan(unmodeled_prerequisite_course_ids=set(range(1700, 1720)))

    messages = _messages(db_session, scenario_id, student_id, plan)

    capped = next(m for m in messages if m.message_code == "PREREQUISITE_NOT_MODELED")
    assert "20 prerequisite course(s)" in capped.message_text
    assert "more" in capped.message_text


def test_many_credit_requirement_nodes_produce_one_message(db_session):
    scenario_id, student_id = _make_scenario(db_session)
    plan = _plan(credit_requirement_node_ids={101, 102, 103, 104})

    messages = _messages(db_session, scenario_id, student_id, plan)

    signoff = [m for m in messages if m.message_code == "ADVISOR_SIGNOFF_NEEDED"]
    assert len(signoff) == 1
    assert "4 requirement(s)" in signoff[0].message_text


def test_unverified_prerequisite_conditions_produce_one_counted_message(db_session):
    scenario_id, student_id = _make_scenario(db_session)
    plan = _plan(unmodeled_prerequisite_node_ids=set(range(1, 367)))

    messages = _messages(db_session, scenario_id, student_id, plan)

    info = [m for m in messages if m.message_code == "UNVERIFIED_PREREQUISITE_TYPE"]
    assert len(info) == 1
    assert info[0].severity == "INFO"
    assert "366 prerequisite condition(s)" in info[0].message_text


def test_a_plan_with_no_caveats_gets_no_messages(db_session):
    scenario_id, student_id = _make_scenario(db_session)

    messages = _messages(db_session, scenario_id, student_id, _plan())

    assert messages == []


def test_infeasible_plan_suggests_the_constraints_it_could_relax(db_session):
    """UC-57: an infeasible result should name the specific knobs this scenario has,
    not just say no schedule exists."""
    scenario_id, student_id = _make_scenario(
        db_session, target_graduation_term_id=2, default_maximum_credits=9, allow_summer=False
    )
    db_session.add(ScenarioTerm(planning_scenario_id=scenario_id, term_id=3, is_excluded=True))
    db_session.add(
        ScenarioPreference(
            planning_scenario_id=scenario_id,
            preference_type=ScenarioPreferenceType.REQUIRE_COURSE,
            course_id=AERO_ENG_3251_COURSE_ID,
        )
    )
    db_session.add(
        ScenarioProgram(
            planning_scenario_id=scenario_id,
            academic_program_id=AERO_MINOR_PROGRAM_ID,
            program_role=ScenarioProgramRole.MINOR,
        )
    )
    db_session.flush()

    messages = _messages(
        db_session, scenario_id, student_id, _plan(status="INFEASIBLE", infeasibility_reason="no schedule")
    )

    assert [m.message_code for m in messages if m.severity == "ERROR"] == ["INFEASIBLE"]
    suggestion = next(m for m in messages if m.message_code == "SUGGESTED_ADJUSTMENTS")
    text = suggestion.message_text
    assert "target graduation term" in text
    assert "above 9 credits" in text
    assert "allow summer terms" in text
    assert "1 term(s) you excluded" in text
    assert "1 chosen course(s)" in text
    assert "1 additional program(s)" in text


def test_feasible_plan_gets_no_suggested_adjustments(db_session):
    scenario_id, student_id = _make_scenario(db_session)

    messages = _messages(db_session, scenario_id, student_id, _plan())

    assert not any(m.message_code == "SUGGESTED_ADJUSTMENTS" for m in messages)
