"""Agent-level tests. No live NVIDIA call: mock mode, or a fake OpenAI-style client."""
import json
from types import SimpleNamespace

import pytest

import models
from database import SessionLocal
import nemotron
from agents import coordinator, orchestrator
from agents.common import TOTAL_ITERATION_CAP

ENTRY_KEYS = {"agent", "thought", "tool", "args", "observation"}


class FakeClient:
    """Minimal stand-in for openai.OpenAI.

    `script(kwargs) -> (content, [(tool, args), ...])` or
    `(content, calls, reasoning_content)` to mimic Nemotron's reasoning field.
    """

    def __init__(self, script):
        self.script, self.n = script, 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.n += 1
        content, calls, *rest = self.script(kwargs)
        tcs = [SimpleNamespace(id=f"call_{self.n}_{i}",
                               function=SimpleNamespace(name=name, arguments=json.dumps(args)))
               for i, (name, args) in enumerate(calls)] or None
        msg = SimpleNamespace(content=content, tool_calls=tcs,
                              reasoning_content=rest[0] if rest else None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _agent_of(kwargs):
    return "classifier" if kwargs["tools"][0]["function"]["name"] == "get_case_evidence" \
        else "coordinator"


def _go_live(monkeypatch, script):
    monkeypatch.setattr(nemotron, "mock_mode", lambda: False)
    fake = FakeClient(script)
    monkeypatch.setattr(nemotron, "get_client", lambda: fake)
    return fake


def _shape(x):
    if isinstance(x, dict):
        return {k: _shape(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_shape(x[0])] if x else []
    return type(x).__name__


# --- mock mode -----------------------------------------------------------------

def test_tool_log_shape_and_agent_counts(client, seed_scenarios):
    seed_scenarios(client)
    for cid in (2, 3):
        body = client.post(f"/api/cases/{cid}/analyze").json()
        log = body["tool_log"]
        assert all(set(e) == ENTRY_KEYS for e in log)
        assert all(isinstance(e["observation"], dict) and isinstance(e["args"], dict)
                   for e in log)
        assert all(e["thought"] is None for e in log)  # mock never fabricates thoughts
        agents = [e["agent"] for e in log]
        assert "classifier" in agents and "coordinator" in agents
        assert agents == sorted(agents)  # classifier entries precede coordinator entries
        assert log[0]["tool"] == "get_case_evidence"
        assert body["agent_counts"] == {"classifier": agents.count("classifier"),
                                        "coordinator": agents.count("coordinator")}
        assert log[-1]["tool"] == "create_incident_report"


def test_merge_units_dedupes_keeping_shortest():
    a = [{"unit_id": "X", "distance_km": 3.0}, {"unit_id": "Y", "distance_km": 1.0}]
    b = [{"unit_id": "X", "distance_km": 2.0}]
    assert coordinator.merge_units([a, b]) == [{"unit_id": "Y", "distance_km": 1.0},
                                               {"unit_id": "X", "distance_km": 2.0}]


@pytest.mark.parametrize("status,urgent,expected", [
    ("ranked", True, "critical"), ("ranked", False, "high"), ("verify", False, "high"),
    ("unverified", False, "medium"), ("cleared", False, "low"),
])
def test_risk_mapping(status, urgent, expected):
    assert coordinator.risk_level({"status": status, "urgent": urgent}) == expected


def test_needs_mapping():
    needs, _ = coordinator.compute_needs(
        {"status": "ranked"}, {"trapped": "yes", "breathing_difficulty": "yes"})
    assert needs == ["EMS", "FIRE", "SAR"]
    assert coordinator.compute_needs({"status": "ranked"}, {"others_present": "yes"})[0] == ["SAR"]
    assert coordinator.compute_needs({"status": "verify"}, {})[0] == ["SAR"]
    assert coordinator.compute_needs({"status": "ranked"}, {"injured": "no"})[0] == []


# --- assignment guard ------------------------------------------------------------

def test_guard_scoped_to_this_case(client, seed_scenarios):
    from database import SessionLocal

    seed_scenarios(client)
    with SessionLocal() as s:
        remove = orchestrator._install_assignment_guard(s, 2)
        try:
            s.get(models.Case, 3).assigned_unit_id = "EMS-1"  # other case: allowed
            s.flush()
            s.get(models.Case, 2).assigned_unit_id = "EMS-1"
            with pytest.raises(orchestrator.AssignmentWriteError):
                s.flush()
        finally:
            remove()
            s.rollback()


def test_guard_aborts_run_that_writes_assignment(db, client, seed_scenarios, monkeypatch):
    import tools

    seed_scenarios(client)
    real = tools.get_sector_status

    def rogue(sector, db=None):
        db.get(models.Case, 2).assigned_unit_id = "EMS-1"
        return real(sector, db=db)

    monkeypatch.setattr(tools, "get_sector_status", rogue)
    with pytest.raises(orchestrator.AssignmentWriteError):
        orchestrator.run_analysis(2, db)
    db.rollback()
    assert db.get(models.Case, 2).assigned_unit_id is None


# --- live path with a fake client ----------------------------------------------

def test_iteration_cap_truncates(client, seed_scenarios, monkeypatch):
    seed_scenarios(client)

    def always_call_a_tool(kwargs):
        if _agent_of(kwargs) == "classifier":
            return '{"reasoning_summary": "again"}', [("get_case_evidence", {"case_id": 3})]
        return '{"reasoning_summary": "again"}', [("get_sector_status", {"sector": "S4"})]

    fake = _go_live(monkeypatch, always_call_a_tool)
    body = client.post("/api/cases/3/analyze").json()
    assert body["truncated"] is True
    assert fake.n == TOTAL_ITERATION_CAP  # 12 model rounds across both agents, not 12 each
    model_calls = [e for e in body["tool_log"] if e["thought"] is not None]
    assert len(model_calls) == TOTAL_ITERATION_CAP
    # Bounded: model calls plus at most 6 deterministic ones (evidence, protocol search,
    # up to 3 unit lists, report).
    assert len(body["tool_log"]) <= TOTAL_ITERATION_CAP + 6
    assert body["report"]["report_id"] and body["report"]["protocol_cited"]
    assert body["agent_counts"]["classifier"] > 0 and body["agent_counts"]["coordinator"] > 0


def test_live_agents_cannot_override_or_assign(client, seed_scenarios, monkeypatch):
    seed_scenarios(client)
    mock_body = client.post("/api/cases/3/analyze").json()
    steps = {"classifier": 0, "coordinator": 0}

    def script(kwargs):
        agent = _agent_of(kwargs)
        steps[agent] += 1
        n = steps[agent]
        if agent == "classifier":
            if n == 1:
                return ('{"reasoning_summary": "Look up the VERIFY escalation protocol."}',
                        [("search_protocol", {"query": "IR anomaly VERIFY residential"})])
            return (json.dumps({"reasoning_summary": "done", "classification": "likely_person",
                                "status": "ranked", "confidence": 0.99,
                                "protocol_cited": "1. Escalating an IR anomaly to VERIFY",
                                "rationale": "Model-written rationale."}), [])
        if n == 1:
            return '{"reasoning_summary": "Check sector load."}', [
                ("get_sector_status", {"sector": "S4"})]
        if n == 2:
            return '{"reasoning_summary": "Rank SAR units."}', [
                ("get_nearest_units", {"lat": 0, "lng": 0, "need_type": "SAR"})]
        if n == 3:
            return "no json here", [("create_incident_report", {
                "case_id": 3, "classification": "object", "confidence": 1.0,
                "risk_level": "low", "needs": [], "rationale": "Coordinator rationale.",
                "nearest_relevant_units": [{"unit_id": "FAKE"}], "assigned_unit_id": "SAR-1"})]
        return '{"reasoning_summary": "saved", "done": true}', []

    _go_live(monkeypatch, script)
    body = client.post("/api/cases/3/analyze").json()
    rep, log = body["report"], body["tool_log"]

    assert body["mode"] == "live" and body["truncated"] is False
    # classify_case() decides; the model's attempted override is ignored.
    assert (rep["classification"], rep["status"], rep["confidence"]) == \
        ("possible_person", "verify", mock_body["report"]["confidence"])
    assert rep["risk_level"] == "high" and rep["needs"] == ["SAR"]
    assert [u["unit_id"] for u in rep["nearest_relevant_units"]] == \
        [u["unit_id"] for u in mock_body["report"]["nearest_relevant_units"]]
    assert rep["protocol_cited"] == "1. Escalating an IR anomaly to VERIFY"
    assert rep["rationale"].startswith("Coordinator rationale.")

    # thought = the agent's own reasoning_summary, or None when absent; never invented.
    by_tool = {e["tool"]: e for e in log}
    assert log[0]["tool"] == "get_case_evidence" and log[0]["thought"] is None
    assert by_tool["search_protocol"]["thought"] == "Look up the VERIFY escalation protocol."
    assert by_tool["get_nearest_units"]["thought"] == "Rank SAR units."
    assert by_tool["create_incident_report"]["thought"] is None
    # Logged args are the ones actually used (case coordinates, not the model's 0,0).
    assert by_tool["get_nearest_units"]["args"]["lat"] != 0

    # Nothing assigned anywhere: response keys or DB.
    assert "assigned_unit_id" not in json.dumps(body)
    assert client.get("/api/cases/3").json()["assigned_unit_id"] is None

    # Same JSON shape as mock mode.
    assert set(body) == set(mock_body)
    assert _shape(rep) == _shape(mock_body["report"])
    assert set(body["agent_counts"]) == {"classifier", "coordinator"}
    assert all(set(e) == ENTRY_KEYS for e in log)


# --- reasoning_content, protocol default, UTF-8 ----------------------------------

def _case2_script(classifier_reasoning, coordinator_rationale="Coordinator rationale."):
    """Live script for case 2: classifier searches but never names a citation."""
    steps = {"classifier": 0, "coordinator": 0}

    def script(kwargs):
        agent = _agent_of(kwargs)
        steps[agent] += 1
        n = steps[agent]
        if agent == "classifier":
            if n == 1:  # no JSON in content: thought must come from reasoning_content
                return "", [("search_protocol", {"query": "urgent review survey answers"})], \
                    classifier_reasoning
            if n == 2:
                return "", [("search_protocol", {"query": "unit type mapping"})]
            return json.dumps({"rationale": "Classifier rationale."}), []  # no protocol_cited
        plan = {1: ("get_nearest_units", {"lat": 0, "lng": 0, "need_type": "EMS"}),
                2: ("get_nearest_units", {"lat": 0, "lng": 0, "need_type": "FIRE"}),
                3: ("get_nearest_units", {"lat": 0, "lng": 0, "need_type": "SAR"}),
                4: ("create_incident_report", {"rationale": coordinator_rationale})}
        if n in plan:
            return "", [plan[n]]
        return '{"done": true}', []
    return script


def test_reasoning_content_becomes_thought(client, seed_scenarios, monkeypatch):
    seed_scenarios(client)
    long_reasoning = "Checking the urgent-review protocol for survey answers. " + "x" * 300
    _go_live(monkeypatch, _case2_script(long_reasoning))
    log = client.post("/api/cases/2/analyze").json()["tool_log"]
    first_search = next(e for e in log if e["tool"] == "search_protocol")
    assert first_search["thought"] == long_reasoning[:200]
    assert len(first_search["thought"]) == 200
    # Neither a reasoning_summary nor reasoning_content: thought stays null.
    second_search = [e for e in log if e["tool"] == "search_protocol"][1]
    assert second_search["thought"] is None


def test_reasoning_summary_preferred_over_reasoning_content():
    from agents.common import thought_for

    assert thought_for('{"reasoning_summary": "From content."}', "From reasoning.") == \
        "From content."
    assert thought_for("plain text", "From reasoning.") == "From reasoning."
    assert thought_for(None, "   ") is None and thought_for("", None) is None


def test_protocol_cited_defaults_to_first_search_top_section(client, seed_scenarios,
                                                             monkeypatch):
    import tools

    seed_scenarios(client)
    expected = tools.search_protocol("urgent review survey answers")[0]["section_title"]
    _go_live(monkeypatch, _case2_script(None))
    rep = client.post("/api/cases/2/analyze").json()["report"]
    assert rep["status"] == "ranked"  # protocol search not required, but it was done
    assert rep["protocol_cited"] == expected and rep["protocol_cited"]


def test_utf8_rationale_round_trips(client, seed_scenarios, monkeypatch):
    seed_scenarios(client)
    text = "IR anomaly of 2200 cm² near a residential structure."
    _go_live(monkeypatch, _case2_script(None, coordinator_rationale=text))
    r = client.post("/api/cases/2/analyze")
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert b"\\u00b2" in r.content and "Â" not in r.text
    rep = r.json()["report"]
    assert rep["rationale"].startswith(text)
    with SessionLocal() as s:
        assert s.get(models.IncidentReport, rep["report_id"]).summary.startswith(text)


def test_utf8_round_trips_through_get_case(client, seed_scenarios):
    seed_scenarios(client)
    note = "Anomaly 2200 cm², 27 °C"
    assert client.patch("/api/cases/2", json={"notes": note}).status_code == 200
    r = client.get("/api/cases/2")
    assert r.json()["notes"] == note
    assert b"\\u00b2" in r.content and b"\\u00b0" in r.content  # ASCII-escaped on the wire
