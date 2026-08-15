from app.services import requirement_service

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2
ARCH_ENG_BS_PROGRAM_ID = 3  # shares MST_GEN_ED_2026 with Aero BS
AERO_BS_CORE_REQUIREMENT_SET_ID = 1
AERO_BS_PROGRAMMING_REQUIREMENT_SET_ID = 2


def test_resolve_requirement_sets_returns_all_eight_aero_bs_sets(db_session):
    sets = requirement_service.resolve_requirement_sets(db_session, [AERO_BS_PROGRAM_ID])

    codes = {rs.requirement_set_code for rs in sets}
    assert codes == {
        "AERO_BS_2026_CORE",
        "AERO_BS_2026_PROGRAMMING",
        "AERO_BS_2026_COMMUNICATION",
        "AERO_BS_2026_DESIGN",
        "AERO_BS_2026_ADV_MATH",
        "AERO_BS_2026_ETHICS",
        "AERO_BS_2026_TECH",
        "MST_GEN_ED_2026",
    }


def test_resolve_requirement_sets_dedupes_a_set_shared_by_two_programs(db_session):
    # Both Aero BS and Architectural Engineering BS point at MST_GEN_ED_2026 --
    # asking for both programs at once should return it exactly once.
    sets = requirement_service.resolve_requirement_sets(
        db_session, [AERO_BS_PROGRAM_ID, ARCH_ENG_BS_PROGRAM_ID]
    )

    gen_ed_matches = [rs for rs in sets if rs.requirement_set_code == "MST_GEN_ED_2026"]
    assert len(gen_ed_matches) == 1


def test_resolve_requirement_sets_empty_for_no_programs(db_session):
    assert requirement_service.resolve_requirement_sets(db_session, []) == []


def test_flatten_requirement_tree_core_set(db_session):
    result = requirement_service.flatten_requirement_tree(db_session, AERO_BS_CORE_REQUIREMENT_SET_ID)

    assert result is not None
    assert result.requirement_set_code == "AERO_BS_2026_CORE"
    assert len(result.nodes) == 1

    root = result.nodes[0]
    assert root.node_type == "GROUP"
    assert root.node_operator == "ALL"
    assert root.node_name == "Aerospace BS Required Core"
    assert _count_nodes(result.nodes) == 33
    # 30 direct children: 29 concrete required courses, plus one GROUP/ANY
    # choice between MATH 1214 and MATH 1211.
    assert len(root.children) == 30
    course_children = [c for c in root.children if c.node_type == "COURSE"]
    group_children = [c for c in root.children if c.node_type == "GROUP"]
    assert len(course_children) == 29
    assert len(group_children) == 1
    assert group_children[0].node_operator == "ANY"
    for child in course_children:
        assert child.required_course is not None


def test_flatten_requirement_tree_programming_set_nested_groups(db_session):
    result = requirement_service.flatten_requirement_tree(
        db_session, AERO_BS_PROGRAMMING_REQUIREMENT_SET_ID
    )

    assert result is not None
    root = result.nodes[0]
    assert root.node_operator == "ANY"
    assert len(root.children) == 2
    for lecture_lab_group in root.children:
        assert lecture_lab_group.node_operator == "ALL"
        assert len(lecture_lab_group.children) == 2
        assert all(c.required_course is not None for c in lecture_lab_group.children)


def test_flatten_requirement_tree_not_found(db_session):
    assert requirement_service.flatten_requirement_tree(db_session, 999_999) is None


def _count_nodes(nodes) -> int:
    return len(nodes) + sum(_count_nodes(n.children) for n in nodes)
