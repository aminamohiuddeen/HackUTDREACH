def survey_payload(robot_id="r1", sector="S1", **answers):
    return {"robot_id": robot_id, "sector": sector, "answers": answers}


# --- health / docs / CORS ----------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_and_openapi_load(client):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()
    spec = client.get("/openapi.json").json()
    for path in ("/health", "/api/telemetry", "/api/surveys", "/api/robots", "/api/cases",
                 "/api/cases/{case_id}", "/api/cases/{case_id}/analyze", "/api/sectors",
                 "/api/units"):
        assert path in spec["paths"]


def test_cors_allows_frontend_origin(client):
    r = client.options("/api/cases", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


# --- telemetry ---------------------------------------------------------------

def test_telemetry_default_source_is_simulator(client, telemetry_payload):
    r = client.post("/api/telemetry", json=telemetry_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "simulator"
    assert body["case"]["source"] == "simulator"


def test_telemetry_source_from_query(client, telemetry_payload):
    r = client.post("/api/telemetry?source=hardware", json=telemetry_payload())
    assert r.json()["source"] == "hardware"


def test_telemetry_source_from_header(client, telemetry_payload):
    r = client.post("/api/telemetry", json=telemetry_payload(),
                    headers={"X-Reach-Source": "hardware"})
    assert r.json()["source"] == "hardware"


def test_telemetry_invalid_source_rejected(client, telemetry_payload):
    r = client.post("/api/telemetry?source=bogus", json=telemetry_payload())
    assert r.status_code == 422


def test_telemetry_server_sets_timestamp(client, telemetry_payload):
    r = client.post("/api/telemetry", json=telemetry_payload())
    assert r.json()["timestamp"]


def test_telemetry_keeps_client_timestamp(client, telemetry_payload):
    r = client.post("/api/telemetry",
                    json=telemetry_payload(timestamp="2026-11-07T12:00:00Z"))
    assert r.json()["timestamp"].startswith("2026-11-07T12:00:00")


def test_telemetry_validation(client, telemetry_payload):
    bad = telemetry_payload(location={"lat": 1, "lng": 2, "source": "satellite"})
    assert client.post("/api/telemetry", json=bad).status_code == 422
    bad = telemetry_payload(location_zone="farm")
    assert client.post("/api/telemetry", json=bad).status_code == 422
    missing = telemetry_payload()
    del missing["infrared_triggered"]
    assert client.post("/api/telemetry", json=missing).status_code == 422


def test_telemetry_creates_robot_and_case(client, telemetry_payload):
    client.post("/api/telemetry", json=telemetry_payload(robot_id="rx", sector="S9"))
    robots = client.get("/api/robots").json()
    assert [r["id"] for r in robots] == ["rx"]
    assert robots[0]["last_lat"] == 32.98
    assert "S9" in [s["id"] for s in client.get("/api/sectors").json()]
    assert len(client.get("/api/cases").json()) == 1


def test_repeat_telemetry_same_case(client, telemetry_payload):
    a = client.post("/api/telemetry", json=telemetry_payload()).json()
    b = client.post("/api/telemetry", json=telemetry_payload(
        infrared_triggered=True, anomaly_size_cm2=1500, location_zone="residential")).json()
    assert a["case_id"] == b["case_id"]
    assert b["case"]["status"] == "verify"


# --- surveys -----------------------------------------------------------------

def test_survey_ranks_case_and_defaults_unknown(client):
    r = client.post("/api/surveys", json=survey_payload(trapped="yes"))
    assert r.status_code == 201
    case = r.json()["case"]
    assert case["classification"] == "likely_person"
    assert case["status"] == "ranked"
    assert case["rank"] == 1
    assert case["urgent_reasons"] == ["trapped"]
    detail = client.get(f"/api/cases/{case['id']}").json()
    assert detail["surveys"][0]["answers"]["injured"] == "unknown"


def test_survey_invalid_answer_rejected(client):
    r = client.post("/api/surveys", json=survey_payload(injured="maybe"))
    assert r.status_code == 422


def test_survey_source_header(client):
    r = client.post("/api/surveys", json=survey_payload(injured="no"),
                    headers={"X-Reach-Source": "hardware"})
    assert r.json()["source"] == "hardware"


def test_later_all_unknown_survey_does_not_unrank(client):
    client.post("/api/surveys", json=survey_payload(trapped="yes"))
    r = client.post("/api/surveys", json=survey_payload())
    assert r.json()["case"]["status"] == "ranked"


# --- cases -------------------------------------------------------------------

def test_cases_ordering_and_filters(client, telemetry_payload):
    client.post("/api/telemetry", json=telemetry_payload(robot_id="cleared"))
    client.post("/api/telemetry", json=telemetry_payload(
        robot_id="verify", infrared_triggered=True, anomaly_size_cm2=1500,
        location_zone="residential"))
    client.post("/api/surveys", json=survey_payload(robot_id="calm", injured="no"))
    client.post("/api/surveys", json=survey_payload(robot_id="urgent", trapped="yes",
                                                    injured="yes"))
    cases = client.get("/api/cases").json()
    assert [c["robot_id"] for c in cases] == ["urgent", "calm", "verify", "cleared"]
    assert [c["rank"] for c in cases] == [1, 2, None, None]

    only_verify = client.get("/api/cases?status=verify").json()
    assert [c["robot_id"] for c in only_verify] == ["verify"]
    assert client.get("/api/cases?sector=S2").json() == []
    assert client.get("/api/cases?status=nope").status_code == 422


def test_get_case_detail(client, telemetry_payload):
    cid = client.post("/api/telemetry", json=telemetry_payload()).json()["case_id"]
    d = client.get(f"/api/cases/{cid}").json()
    assert d["id"] == cid
    assert len(d["telemetry"]) == 1
    t = d["telemetry"][0]
    assert t["location"] == {"lat": 32.98, "lng": -96.75, "source": "gps"}
    assert t["source"] == "simulator"
    assert t["accelerometer"] == {"x": 0.0, "y": 0.0, "z": 9.81}
    assert d["surveys"] == []


def test_get_case_404(client):
    assert client.get("/api/cases/999").status_code == 404


def test_patch_case(client, telemetry_payload):
    cid = client.post("/api/telemetry", json=telemetry_payload()).json()["case_id"]
    r = client.patch(f"/api/cases/{cid}", json={"status": "dispatched",
                                                "assigned_unit_id": "SAR-1",
                                                "notes": "team en route"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "dispatched"
    assert body["assigned_unit_id"] == "SAR-1"
    assert body["notes"] == "team en route"


def test_patch_case_errors(client, telemetry_payload):
    cid = client.post("/api/telemetry", json=telemetry_payload()).json()["case_id"]
    assert client.patch("/api/cases/999", json={"notes": "x"}).status_code == 404
    assert client.patch(f"/api/cases/{cid}", json={"assigned_unit_id": "NOPE"}).status_code == 404
    assert client.patch(f"/api/cases/{cid}", json={"status": "bogus"}).status_code == 422
    assert client.patch(f"/api/cases/{cid}", json={"status": None}).status_code == 422
    assert client.patch(f"/api/cases/{cid}", json={"classification": "x"}).status_code == 422


def test_dispatched_is_sticky(client, telemetry_payload):
    cid = client.post("/api/telemetry", json=telemetry_payload()).json()["case_id"]
    client.patch(f"/api/cases/{cid}", json={"status": "dispatched"})
    r = client.post("/api/surveys", json=survey_payload(trapped="yes")).json()
    assert r["case_id"] == cid
    assert r["case"]["status"] == "dispatched"
    assert r["case"]["classification"] == "likely_person"


def test_resolved_opens_new_case(client, telemetry_payload):
    cid = client.post("/api/telemetry", json=telemetry_payload()).json()["case_id"]
    client.patch(f"/api/cases/{cid}", json={"status": "resolved"})
    new = client.post("/api/telemetry", json=telemetry_payload()).json()
    assert new["case_id"] != cid
    assert client.get(f"/api/cases/{cid}").json()["status"] == "resolved"


def test_analyze_stub(client, telemetry_payload):
    cid = client.post("/api/telemetry", json=telemetry_payload()).json()["case_id"]
    r = client.post(f"/api/cases/{cid}/analyze")
    assert r.status_code == 200
    assert r.json() == {"status": "not_implemented"}
    assert client.post("/api/cases/999/analyze").status_code == 404


# --- reference data ----------------------------------------------------------

def test_list_sectors(client):
    sectors = client.get("/api/sectors").json()
    assert {s["id"] for s in sectors} == {"S1", "S2", "S3", "S4"}


def test_list_units(client):
    units = client.get("/api/units").json()
    assert {u["unit_type"] for u in units} == {"EMS", "FIRE", "SAR"}
    assert all(u["status"] == "available" for u in units)


def test_list_robots_empty(client):
    assert client.get("/api/robots").json() == []
