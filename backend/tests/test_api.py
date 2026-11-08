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


def _keys_anywhere(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys_anywhere(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys_anywhere(v)}
    return set()


def _assert_no_assignment(body):
    keys = _keys_anywhere(body)
    assert "assigned_unit_id" not in keys
    assert "assigned" not in keys


def test_analyze_404(client):
    assert client.post("/api/cases/999/analyze").status_code == 404


def test_analyze_mock_ranked_case(client, seed_scenarios):
    seed_scenarios(client)
    r = client.post("/api/cases/2/analyze")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"report", "tool_log", "agent_counts", "mode", "truncated"}
    assert body["mode"] == "mock" and body["truncated"] is False
    rep = body["report"]
    assert isinstance(rep["nearest_relevant_units"], list) and rep["nearest_relevant_units"]
    assert rep["classification"] == "likely_person"
    assert rep["status"] == "ranked"
    assert rep["risk_level"] == "critical"
    assert rep["needs"] == ["EMS", "FIRE", "SAR"]  # injured+immediate_help, trapped
    _assert_no_assignment(body)
    assert client.get("/api/cases/2").json()["assigned_unit_id"] is None


def test_analyze_mock_verify_case(client, seed_scenarios):
    seed_scenarios(client)
    body = client.post("/api/cases/3/analyze").json()
    rep = body["report"]
    assert rep["status"] == "verify"
    assert isinstance(rep["protocol_cited"], str) and rep["protocol_cited"]
    assert rep["needs"] == ["SAR"] and rep["risk_level"] == "high"
    assert any(e["tool"] == "search_protocol" for e in body["tool_log"])
    _assert_no_assignment(body)


def test_analyze_protocol_cited_always_string(client, seed_scenarios):
    seed_scenarios(client)
    for cid in (1, 2, 3, 4):
        cited = client.post(f"/api/cases/{cid}/analyze").json()["report"]["protocol_cited"]
        assert cited is not None
        assert not isinstance(cited, list)
        assert isinstance(cited, str)


def test_analyze_no_need_rationale(client, seed_scenarios):
    seed_scenarios(client)
    for cid in (1, 4):  # cleared, unverified: no survey, not verify
        rep = client.post(f"/api/cases/{cid}/analyze").json()["report"]
        assert rep["needs"] == [] and rep["nearest_relevant_units"] == []
        assert ("No specific need identified from survey answers; "
                "unit suggestion not generated.") in rep["rationale"]


def test_analyze_case_without_coordinates(client):
    # Survey-only case: no telemetry, so the case has no lat/lng.
    cid = client.post("/api/surveys", json=survey_payload(immediate_help="yes")).json()["case_id"]
    rep = client.post(f"/api/cases/{cid}/analyze").json()["report"]
    assert rep["needs"] == ["EMS"]
    assert rep["nearest_relevant_units"] == []
    assert "No coordinates recorded for this case" in rep["rationale"]


def test_analyze_twice_separates_tool_logs(client, seed_scenarios):
    import models
    from database import SessionLocal

    seed_scenarios(client)
    a = client.post("/api/cases/2/analyze").json()
    b = client.post("/api/cases/2/analyze").json()
    assert a["report"]["report_id"] != b["report"]["report_id"]
    with SessionLocal() as s:
        for body in (a, b):
            rows = s.query(models.ToolLog).filter_by(report_id=body["report"]["report_id"]) \
                .order_by(models.ToolLog.id).all()
            assert [(r.agent, r.tool, r.args_json, r.observation_json) for r in rows] == \
                [(e["agent"], e["tool"], e["args"], e["observation"]) for e in body["tool_log"]]
        assert s.query(models.ToolLog).filter(models.ToolLog.report_id.is_(None)).count() == 0


def test_patch_assignment_during_analysis(client, seed_scenarios, monkeypatch):
    """A human PATCH of assigned_unit_id mid-analysis succeeds; analysis never echoes it."""
    import tools

    seed_scenarios(client)
    real = tools.get_sector_status
    patch_status = []

    def sector_status_with_concurrent_patch(*args, **kwargs):
        r = client.patch("/api/cases/2", json={"assigned_unit_id": "EMS-1"})
        patch_status.append(r.status_code)
        return real(*args, **kwargs)

    monkeypatch.setattr(tools, "get_sector_status", sector_status_with_concurrent_patch)
    r = client.post("/api/cases/2/analyze")
    assert patch_status == [200]
    assert r.status_code == 200
    _assert_no_assignment(r.json())
    assert client.get("/api/cases/2").json()["assigned_unit_id"] == "EMS-1"


# --- reference data ----------------------------------------------------------

def test_list_sectors(client):
    sectors = client.get("/api/sectors").json()
    assert {s["id"] for s in sectors} == {"S1", "S2", "S3", "S4"}


# --- sector coverage state -----------------------------------------------------

ALL_CASE_STATUSES = {"verify", "ranked", "unverified", "cleared", "dispatched", "resolved"}


def _sector(client, sector_id):
    return next(s for s in client.get("/api/sectors").json() if s["id"] == sector_id)


def test_sector_fresh_is_unsearched(client):
    s = _sector(client, "S2")
    assert set(s) == {"id", "name", "zone_type", "state", "case_count_by_status",
                      "urgent_cases", "robot_count", "last_telemetry_at"}
    assert s["state"] == "unsearched" and s["last_telemetry_at"] is None
    assert s["case_count_by_status"] == {k: 0 for k in ALL_CASE_STATUSES}
    assert s["urgent_cases"] == 0 and s["robot_count"] == 0


def test_sector_telemetry_no_anomaly_is_cleared(client):
    """Real path: scenario 1 telemetry (S2, no anomaly) -> classifier marks the case
    cleared. A cleared case is closed but still counted in case_count_by_status."""
    import simulator

    for t in simulator.SCENARIOS[1]["telemetry"]:
        assert client.post("/api/telemetry", json=t).status_code == 201
    case = client.get("/api/cases").json()
    assert [c["status"] for c in case] == ["cleared"]  # produced by the classifier
    s = _sector(client, "S2")
    assert s["state"] == "cleared"
    assert s["case_count_by_status"]["cleared"] == 1
    assert sum(s["case_count_by_status"].values()) == 1
    assert s["last_telemetry_at"] is not None and s["robot_count"] == 1


def test_sector_ranked_urgent_is_urgent(client, seed_scenarios):
    seed_scenarios(client)  # scenario 2 -> case 2: likely_person/ranked urgent in S1
    s = _sector(client, "S1")
    assert s["state"] == "urgent"
    assert s["urgent_cases"] == 1 and s["case_count_by_status"]["ranked"] == 1


def test_sector_only_verify_is_active(client, telemetry_payload):
    client.post("/api/telemetry", json=telemetry_payload(
        sector="S3", location_zone="residential", infrared_triggered=True,
        anomaly_size_cm2=1500.0))
    s = _sector(client, "S3")
    assert s["case_count_by_status"]["verify"] == 1
    assert sum(s["case_count_by_status"].values()) == 1
    assert s["state"] == "active" and s["urgent_cases"] == 0


def test_sector_all_cases_resolved_is_cleared(client, telemetry_payload):
    r = client.post("/api/telemetry", json=telemetry_payload(
        sector="S3", location_zone="residential", infrared_triggered=True,
        anomaly_size_cm2=1500.0))
    case_id = r.json()["case_id"]
    assert _sector(client, "S3")["state"] == "active"
    assert client.patch(f"/api/cases/{case_id}", json={"status": "resolved"}).status_code == 200
    s = _sector(client, "S3")
    assert s["state"] == "cleared" and s["case_count_by_status"]["resolved"] == 1


def test_sector_dispatched_case_is_active(client, telemetry_payload):
    r = client.post("/api/telemetry", json=telemetry_payload(
        sector="S3", location_zone="residential", infrared_triggered=True,
        anomaly_size_cm2=1500.0))
    client.patch(f"/api/cases/{r.json()['case_id']}", json={"status": "dispatched"})
    assert _sector(client, "S3")["state"] == "active"


def test_sector_survey_only_urgent_is_urgent_not_unsearched(client):
    """Regression for the rule order: a survey-only survivor (no robot telemetry) in a
    fresh sector must surface as urgent, not unsearched."""
    r = client.post("/api/surveys", json=survey_payload(
        robot_id="s-only", sector="S3", injured="yes", trapped="yes", immediate_help="yes"))
    assert r.status_code == 201, r.text
    s = _sector(client, "S3")
    assert s["last_telemetry_at"] is None
    assert s["state"] == "urgent"
    assert s["urgent_cases"] == 1 and s["case_count_by_status"]["ranked"] == 1


def test_sector_urgent_cases_excludes_resolved_but_tool_keeps_audit_count(client,
                                                                          seed_scenarios):
    import tools

    seed_scenarios(client)
    client.patch("/api/cases/2", json={"status": "resolved"})  # the ranked urgent S1 case
    s = _sector(client, "S1")
    assert s["urgent_cases"] == 0 and s["state"] == "active"  # case 4 in S1 is unverified
    tool = tools.get_sector_status("S1")
    assert tool["urgent_cases"] == 1  # all-urgent-including-resolved, unchanged
    assert tool["case_counts"] == {"resolved": 1, "unverified": 1}  # zeros dropped


def test_list_units(client):
    units = client.get("/api/units").json()
    assert {u["unit_type"] for u in units} == {"EMS", "FIRE", "SAR"}
    assert all(u["status"] == "available" for u in units)


def test_list_robots_empty(client):
    assert client.get("/api/robots").json() == []
