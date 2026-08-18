AERO_BS_PROGRAM_ID = 1
AERO_ENG_4780_COURSE_ID = 1718


def test_get_programs(client):
    response = client.get("/programs")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 147
    assert any(p["program_code"] == "AERO_BS_2026" for p in body)


def test_get_program_requirements(client):
    response = client.get(f"/programs/{AERO_BS_PROGRAM_ID}/requirements")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 8
    codes = {rs["requirement_set_code"] for rs in body}
    assert "AERO_BS_2026_CORE" in codes


def test_get_program_requirements_404_for_missing_program(client):
    response = client.get("/programs/999999/requirements")

    assert response.status_code == 404


def test_get_course_prerequisites(client):
    response = client.get(f"/courses/{AERO_ENG_4780_COURSE_ID}/prerequisites")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["node_type"] == "GROUP"
    assert body[0]["rule_operator"] == "ALL"
    assert len(body[0]["children"]) == 3


def test_get_course_prerequisites_404_for_missing_course(client):
    response = client.get("/courses/999999/prerequisites")

    assert response.status_code == 404


def test_search_courses(client):
    response = client.get("/courses", params={"search": "AERO ENG 4780"})

    assert response.status_code == 200
    body = response.json()
    assert any(c["course_id"] == AERO_ENG_4780_COURSE_ID for c in body)


def test_search_courses_returns_descriptions_and_respects_school_filters(client):
    """Return audit detail while narrowing course matches to the requested school."""
    matching = client.get("/courses", params={"search": "AERO ENG 4780", "college_id": 1, "department_id": 17})
    excluded = client.get("/courses", params={"search": "AERO ENG 4780", "college_id": 999999})
    assert matching.status_code == 200
    assert matching.json()[0]["course_description"]
    assert excluded.status_code == 200
    assert excluded.json() == []


def test_search_courses_requires_nonempty_query(client):
    response = client.get("/courses", params={"search": ""})

    assert response.status_code == 422


def test_cors_preflight_accepts_private_lan_frontend(client):
    """Allow Vite when the frontend is opened through a private LAN address."""
    response = client.options(
        "/colleges",
        headers={
            "Origin": "http://192.168.1.4:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://192.168.1.4:5173"


def test_cors_preflight_rejects_unconfigured_public_origin(client):
    """Keep arbitrary public websites outside the local-development CORS boundary."""
    response = client.options(
        "/colleges",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
