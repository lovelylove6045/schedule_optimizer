from app.models.student import Student
from app.models.student_credit import StudentCredit
from app.schemas.requirement import RequirementNodeOut, RequirementSetOut
from app.services import credit_matching_service, requirement_service
from app.services.common import load_courses_by_id

AERO_BS_PROGRAMMING_REQUIREMENT_SET_ID = 2
COMP_SCI_1972_COURSE_ID = 1122  # lecture
COMP_SCI_1982_COURSE_ID = 1126  # its lab (ANY[ALL(1972,1982), ALL(1570,1580)])
COMP_SCI_1570_COURSE_ID = 1115

# Aerospace BS "Technical Electives" set: ALL(node 55 = 9 credit hours of MAE
# technical electives, node 56 = 3 credit hours of 5000-level MAE electives).
AERO_BS_TECHNICAL_ELECTIVE_SET_ID = 7
NINE_CREDIT_GROUP_NODE_ID = 55
# Three 3-credit members of node 55's course group.
MAE_TECH_ELECTIVE_COURSE_IDS = [1712, 1727, 1728]


def _make_student(db_session) -> int:
    student = Student(display_name="Test Student")
    db_session.add(student)
    db_session.flush()
    return student.student_id


def _add_completed_credit(db_session, student_id: int, course_id: int, grade: str | None = "B") -> None:
    db_session.add(
        StudentCredit(
            student_id=student_id,
            course_id=course_id,
            source_type="INSTITUTIONAL",
            status="COMPLETED",
            grade=grade,
        )
    )
    db_session.flush()


def test_match_completed_courses_propagates_all_and_any_operators(db_session):
    student_id = _make_student(db_session)
    _add_completed_credit(db_session, student_id, COMP_SCI_1972_COURSE_ID)
    _add_completed_credit(db_session, student_id, COMP_SCI_1982_COURSE_ID)

    tree = requirement_service.flatten_requirement_tree(db_session, AERO_BS_PROGRAMMING_REQUIREMENT_SET_ID)
    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)

    root = matched.nodes[0]
    assert root.node_operator == "ANY"
    lecture_lab_1972, lecture_lab_1570 = root.children

    # Completed both halves of the 1972/1982 lecture+lab -> that ALL group,
    # and both of its individual COURSE leaves, are satisfied.
    assert lecture_lab_1972.is_satisfied is True
    assert all(c.is_satisfied for c in lecture_lab_1972.children)

    # Never touched 1570/1580 -> that ALL group is not satisfied.
    assert lecture_lab_1570.is_satisfied is False
    assert all(not c.is_satisfied for c in lecture_lab_1570.children)

    # The root is ANY, and one branch is fully satisfied -> root is satisfied.
    assert root.is_satisfied is True


def test_match_completed_courses_nothing_completed_leaves_everything_unsatisfied(db_session):
    student_id = _make_student(db_session)  # no credits at all

    tree = requirement_service.flatten_requirement_tree(db_session, AERO_BS_PROGRAMMING_REQUIREMENT_SET_ID)
    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)

    assert matched.nodes[0].is_satisfied is False
    assert not any(_any_satisfied(node) for node in matched.nodes)


def test_match_completed_courses_does_not_mutate_the_input(db_session):
    student_id = _make_student(db_session)
    _add_completed_credit(db_session, student_id, COMP_SCI_1972_COURSE_ID)
    _add_completed_credit(db_session, student_id, COMP_SCI_1982_COURSE_ID)

    tree = requirement_service.flatten_requirement_tree(db_session, AERO_BS_PROGRAMMING_REQUIREMENT_SET_ID)
    credit_matching_service.match_completed_courses(db_session, student_id, tree)

    assert tree.nodes[0].is_satisfied is None


def test_meets_minimum_grade_boundary(db_session):
    student_id = _make_student(db_session)
    _add_completed_credit(db_session, student_id, COMP_SCI_1570_COURSE_ID, grade="C")
    course = load_courses_by_id(db_session, {COMP_SCI_1570_COURSE_ID})[COMP_SCI_1570_COURSE_ID]

    tree = _single_course_node_tree(course, minimum_grade="B")
    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)
    assert matched.nodes[0].is_satisfied is False, "a C shouldn't satisfy a B minimum"

    tree = _single_course_node_tree(course, minimum_grade="C")
    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)
    assert matched.nodes[0].is_satisfied is True, "a C should satisfy a C minimum"


def test_meets_minimum_grade_pass_fail_always_satisfies(db_session):
    student_id = _make_student(db_session)
    _add_completed_credit(db_session, student_id, COMP_SCI_1570_COURSE_ID, grade="P")
    course = load_courses_by_id(db_session, {COMP_SCI_1570_COURSE_ID})[COMP_SCI_1570_COURSE_ID]

    tree = _single_course_node_tree(course, minimum_grade="A")
    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)

    assert matched.nodes[0].is_satisfied is True


def test_credit_requirement_node_is_never_auto_satisfied(db_session):
    student_id = _make_student(db_session)
    tree = RequirementSetOut(
        requirement_set_id=-1,
        requirement_set_code="SYNTHETIC",
        requirement_set_name="Synthetic",
        requirement_set_type="TEST",
        nodes=[
            RequirementNodeOut(
                requirement_node_id=-1,
                node_type="CREDIT_REQUIREMENT",
                required_credit_hours=12.0,
                node_name="12 credits of an approved minor",
            )
        ],
    )

    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)

    assert matched.nodes[0].is_satisfied is False


def test_course_group_requires_its_full_credit_hour_total(db_session):
    """Aerospace BS requirement set 7 is ALL(9-credit MAE technical electives,
    3-credit 5000-level MAE electives). Completing one 3-credit member of the
    9-credit group must NOT satisfy it -- the old `any(member completed)` rule
    reported a 15-credit elective block as done after a single course."""
    student_id = _make_student(db_session)
    _add_completed_credit(db_session, student_id, MAE_TECH_ELECTIVE_COURSE_IDS[0])

    tree = requirement_service.flatten_requirement_tree(db_session, AERO_BS_TECHNICAL_ELECTIVE_SET_ID)
    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)

    nine_credit_group = _node_by_id(matched.nodes, NINE_CREDIT_GROUP_NODE_ID)
    assert nine_credit_group.required_credit_hours == 9.0
    assert nine_credit_group.is_satisfied is False
    assert matched.nodes[0].is_satisfied is False


def test_course_group_is_satisfied_once_its_credit_hours_are_covered(db_session):
    student_id = _make_student(db_session)
    for course_id in MAE_TECH_ELECTIVE_COURSE_IDS:  # 3 x 3 credit hours = 9
        _add_completed_credit(db_session, student_id, course_id)

    tree = requirement_service.flatten_requirement_tree(db_session, AERO_BS_TECHNICAL_ELECTIVE_SET_ID)
    matched = credit_matching_service.match_completed_courses(db_session, student_id, tree)

    assert _node_by_id(matched.nodes, NINE_CREDIT_GROUP_NODE_ID).is_satisfied is True


def test_course_group_with_no_threshold_needs_only_one_member(db_session):
    """The 12 COURSE_GROUP nodes that state neither a count nor credit hours keep the
    original "any single member" behaviour."""
    student_id = _make_student(db_session)
    _add_completed_credit(db_session, student_id, MAE_TECH_ELECTIVE_COURSE_IDS[0])
    group = _node_by_id(
        requirement_service.flatten_requirement_tree(db_session, AERO_BS_TECHNICAL_ELECTIVE_SET_ID).nodes,
        NINE_CREDIT_GROUP_NODE_ID,
    )
    untresholded = RequirementSetOut(
        requirement_set_id=-1,
        requirement_set_code="SYNTHETIC",
        requirement_set_name="Synthetic",
        requirement_set_type="TEST",
        nodes=[group.model_copy(update={"required_credit_hours": None, "required_count": None})],
    )

    matched = credit_matching_service.match_completed_courses(db_session, student_id, untresholded)

    assert matched.nodes[0].is_satisfied is True


def _node_by_id(nodes: list[RequirementNodeOut], node_id: int) -> RequirementNodeOut | None:
    """Depth-first search a flattened tree for one node by requirement_node_id."""
    for node in nodes:
        if node.requirement_node_id == node_id:
            return node
        found = _node_by_id(node.children, node_id)
        if found is not None:
            return found
    return None


def _single_course_node_tree(course, minimum_grade: str) -> RequirementSetOut:
    return RequirementSetOut(
        requirement_set_id=-1,
        requirement_set_code="SYNTHETIC",
        requirement_set_name="Synthetic",
        requirement_set_type="TEST",
        nodes=[
            RequirementNodeOut(
                requirement_node_id=-1,
                node_type="COURSE",
                required_course=course,
                minimum_grade=minimum_grade,
            )
        ],
    )


def _any_satisfied(node) -> bool:
    return bool(node.is_satisfied) or any(_any_satisfied(child) for child in node.children)
