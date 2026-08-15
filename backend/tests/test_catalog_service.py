from app.services import catalog_service

AERO_BS_PROGRAM_CODE = "AERO_BS_2026"
# AERO ENG 4780 (Aerospace Systems Design I) -- known-good prerequisite tree
# from db/sanity_checks.sql: one GROUP/ALL root, requiring AERO ENG 3251, 3361, 3171.
AERO_ENG_4780_COURSE_ID = 1718
AERO_ENG_3251_COURSE_ID = 1709
AERO_ENG_3361_COURSE_ID = 1710
AERO_ENG_3171_COURSE_ID = 1708


def test_list_programs_returns_the_full_catalog(db_session):
    programs = catalog_service.list_programs(db_session)

    assert len(programs) == 147
    assert any(p.program_code == AERO_BS_PROGRAM_CODE for p in programs)


def test_get_program_found(db_session):
    programs = catalog_service.list_programs(db_session)
    aero = next(p for p in programs if p.program_code == AERO_BS_PROGRAM_CODE)

    found = catalog_service.get_program(db_session, aero.academic_program_id)

    assert found is not None
    assert found.program_code == AERO_BS_PROGRAM_CODE


def test_get_program_not_found(db_session):
    assert catalog_service.get_program(db_session, 999_999) is None


def test_get_prerequisite_tree_resolves_group_of_courses(db_session):
    tree = catalog_service.get_prerequisite_tree(db_session, AERO_ENG_4780_COURSE_ID)

    assert len(tree) == 1
    root = tree[0]
    assert root.node_type == "GROUP"
    assert root.rule_operator == "ALL"
    assert root.requisite_type == "PREREQUISITE"
    assert len(root.children) == 3

    required_ids = {child.required_course.course_id for child in root.children}
    assert required_ids == {AERO_ENG_3251_COURSE_ID, AERO_ENG_3361_COURSE_ID, AERO_ENG_3171_COURSE_ID}
    for child in root.children:
        assert child.node_type == "COURSE"
        assert child.required_course.subject_code == "AERO ENG"


def test_get_prerequisite_tree_empty_for_course_with_none(db_session):
    # "How Should I Live? An Introduction to Ethics" has no course_rule_nodes
    # row at all (it's one of the ~468 courses in the catalog with no
    # prerequisites of any kind).
    tree = catalog_service.get_prerequisite_tree(db_session, 82)

    assert tree == []


def test_get_course_group_members(db_session):
    result = catalog_service.get_course_group_members(db_session, 1)

    assert result is not None
    assert result.course_group.course_group_code == "AERO_ADV_MATH_STAT_2026"
    assert len(result.courses) > 0
    # Credit hours are usually positive, but a few variable/zero-credit
    # courses (e.g. "Oral Examination") are legitimately 0, not missing data.
    assert all(course.credit_hours >= 0 for course in result.courses)


def test_get_course_group_members_not_found(db_session):
    assert catalog_service.get_course_group_members(db_session, 999_999) is None


def test_search_courses_matches_combined_subject_and_number(db_session):
    results = catalog_service.search_courses(db_session, "AERO ENG 4780")

    assert any(c.course_id == AERO_ENG_4780_COURSE_ID for c in results)


def test_search_courses_matches_title(db_session):
    results = catalog_service.search_courses(db_session, "Aerospace Systems Design")

    assert any(c.course_id == AERO_ENG_4780_COURSE_ID for c in results)


def test_search_courses_caps_results(db_session):
    # A single-letter query matches far more than MAX_COURSE_SEARCH_RESULTS courses.
    results = catalog_service.search_courses(db_session, "a")

    assert len(results) == catalog_service.MAX_COURSE_SEARCH_RESULTS


def test_search_courses_blank_query_returns_nothing(db_session):
    assert catalog_service.search_courses(db_session, "   ") == []
