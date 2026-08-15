"""End-to-end HTTP tests for the Phase 4 exit criteria: POST /scenarios ->
POST /scenarios/{id}/generate -> GET /plans/{id}, reproducing Phase 3's
verified scenarios over HTTP, plus scenario-creation validation errors."""

AERO_BS_PROGRAM_ID = 1
AERO_MINOR_PROGRAM_ID = 2


def _term_ids(client) -> list[int]:
    """Return every term_id in chronological order, via the real GET /terms endpoint."""
    response = client.get("/terms")
    assert response.status_code == 200
    return [term["term_id"] for term in response.json()]


def test_full_journey_produces_a_feasible_persisted_plan(client):
    """POST /scenarios -> POST /scenarios/{id}/generate -> GET /plans/{id} for a real
    Aerospace BS scenario should reproduce Scenario A: a feasible plan covering the
    requirement tree."""
    start_term_id = _term_ids(client)[0]
    create_response = client.post(
        "/scenarios",
        json={
            "student_display_name": "HTTP Test Student",
            "start_term_id": start_term_id,
            "programs": [{"academic_program_id": AERO_BS_PROGRAM_ID, "program_role": "PRIMARY_MAJOR"}],
        },
    )
    assert create_response.status_code == 200
    planning_scenario_id = create_response.json()["planning_scenario_id"]

    generate_response = client.post(f"/scenarios/{planning_scenario_id}/generate")

    assert generate_response.status_code == 200
    plans = generate_response.json()
    assert len(plans) >= 2
    feasible_plan = plans[0]
    assert feasible_plan["status"] != "INFEASIBLE"
    assert len(feasible_plan["courses"]) > 0
    plan_response = client.get(f"/plans/{feasible_plan['degree_plan_id']}")
    assert plan_response.status_code == 200
    assert plan_response.json()["degree_plan_id"] == feasible_plan["degree_plan_id"]


def test_generate_for_unreachable_target_returns_200_with_infeasible_status(client):
    """An unreachably-early target_graduation_term_id should come back as a normal
    200 response with status "INFEASIBLE" and an explanatory message, not a 500."""
    term_ids = _term_ids(client)
    create_response = client.post(
        "/scenarios",
        json={
            "start_term_id": term_ids[0],
            "target_graduation_term_id": term_ids[1],
            "programs": [{"academic_program_id": AERO_BS_PROGRAM_ID, "program_role": "PRIMARY_MAJOR"}],
        },
    )
    assert create_response.status_code == 200
    planning_scenario_id = create_response.json()["planning_scenario_id"]

    generate_response = client.post(f"/scenarios/{planning_scenario_id}/generate")

    assert generate_response.status_code == 200
    plans = generate_response.json()
    assert len(plans) == 1
    assert plans[0]["status"] == "INFEASIBLE"
    assert len(plans[0]["messages"]) > 0


def test_generate_404_for_unknown_scenario(client):
    response = client.post("/scenarios/999999/generate")

    assert response.status_code == 404


def test_create_scenario_422_for_no_primary_major(client):
    start_term_id = _term_ids(client)[0]
    response = client.post(
        "/scenarios",
        json={
            "start_term_id": start_term_id,
            "programs": [{"academic_program_id": AERO_MINOR_PROGRAM_ID, "program_role": "MINOR"}],
        },
    )

    assert response.status_code == 422


def test_create_scenario_404_for_unknown_program(client):
    start_term_id = _term_ids(client)[0]
    response = client.post(
        "/scenarios",
        json={
            "start_term_id": start_term_id,
            "programs": [{"academic_program_id": 999999, "program_role": "PRIMARY_MAJOR"}],
        },
    )

    assert response.status_code == 404
