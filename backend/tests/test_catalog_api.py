"""Tests the catalog-discovery endpoints the frontend wizard needs before a scenario
exists: colleges, college/department metadata on programs, elective choices, and one
course group's full member list."""

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2
AERO_ADV_MATH_STAT_GROUP_ID = 1


def test_list_colleges(client):
    response = client.get("/colleges")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    codes = {college["college_code"] for college in body}
    assert codes == {"CEC", "KUMMER", "CASE"}


def test_programs_carry_department_and_college(client):
    response = client.get("/programs")

    assert response.status_code == 200
    body = response.json()
    aero = next(p for p in body if p["academic_program_id"] == AERO_BS_PROGRAM_ID)
    assert aero["department_code"] == "MAE"
    assert aero["college_code"] == "CEC"
    assert aero["college_name"] == "College of Engineering and Computing"
    # Every currently-loaded department maps to a college, so the picker can always
    # be grouped by school without a null bucket.
    assert all(p["college_id"] is not None for p in body)


def test_requirement_choices_for_one_program(client):
    response = client.get("/requirement-choices", params={"program_ids": str(AERO_BS_PROGRAM_ID)})

    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    labels = {choice["label"] for choice in body}
    assert "MATH 1214 or MATH 1211" in labels
    assert all(len(choice["options"]) >= 2 for choice in body)


def test_requirement_choices_accepts_completed_course_ids(client):
    base = client.get("/requirement-choices", params={"program_ids": str(AERO_BS_PROGRAM_ID)}).json()
    choice = next(c for c in base if c["label"] == "MATH 1214 or MATH 1211")
    completed_id = choice["options"][0]["course_id"]

    response = client.get(
        "/requirement-choices",
        params={"program_ids": str(AERO_BS_PROGRAM_ID), "completed_course_ids": str(completed_id)},
    )

    assert response.status_code == 200
    resolved = next(c for c in response.json() if c["label"] == "MATH 1214 or MATH 1211")
    assert resolved["already_satisfied"] is True


def test_requirement_choices_rejects_a_non_numeric_program_id(client):
    response = client.get("/requirement-choices", params={"program_ids": "abc"})

    assert response.status_code == 400


def test_requirement_choices_404s_for_an_unknown_program(client):
    response = client.get("/requirement-choices", params={"program_ids": "999999"})

    assert response.status_code == 404


def test_requirement_choices_requires_at_least_one_program(client):
    response = client.get("/requirement-choices", params={"program_ids": " "})

    assert response.status_code == 400


def test_get_course_group_courses(client):
    response = client.get(f"/course-groups/{AERO_ADV_MATH_STAT_GROUP_ID}/courses")

    assert response.status_code == 200
    body = response.json()
    assert body["course_group"]["course_group_code"] == "AERO_ADV_MATH_STAT_2026"
    assert len(body["courses"]) > 0


def test_get_course_group_courses_404_for_missing_group(client):
    response = client.get("/course-groups/999999/courses")

    assert response.status_code == 404


def test_program_overlap_suggestions_finds_the_aero_minor(client):
    response = client.get(f"/programs/{AERO_BS_PROGRAM_ID}/overlap-suggestions", params={"program_type": "MINOR"})

    assert response.status_code == 200
    body = response.json()
    assert any(s["academic_program_id"] == AERO_MINOR_PROGRAM_ID for s in body)
    assert all(s["overlap_course_count"] > 0 for s in body)


def test_program_overlap_suggestions_respects_program_type_filter(client):
    response = client.get(f"/programs/{AERO_BS_PROGRAM_ID}/overlap-suggestions", params={"program_type": "MINOR"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert all(s["program_type"] == "MINOR" for s in body)


def test_program_overlap_suggestions_404_for_unknown_program(client):
    response = client.get("/programs/999999/overlap-suggestions")

    assert response.status_code == 404
