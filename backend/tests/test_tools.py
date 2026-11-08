import itertools

import pytest

import models
import nemotron
from main import SEED_UNITS
from tools import (
    REPORT_DETAIL_KEYS,
    TOOL_FUNCTIONS,
    TOOL_SCHEMAS,
    create_incident_report,
    get_nearest_units,
    haversine_km,
    search_protocol,
)

SCENARIO_2 = (32.9855, -96.7502)  # ranked survivor (simulator.py)
SCENARIO_3 = (32.9710, -96.7555)  # residential verify (simulator.py)
UNIT_KEYS = {"unit_id", "name", "unit_type", "distance_mi"}


# --- get_nearest_units ---------------------------------------------------------

def test_nearest_units_sorted_ascending_with_exact_keys(db):
    units = get_nearest_units(*SCENARIO_2, "any", db=db)
    assert isinstance(units, list)
    assert len(units) == len(SEED_UNITS)
    assert all(set(u) == UNIT_KEYS for u in units)
    dists = [u["distance_mi"] for u in units]
    assert dists == sorted(dists)


@pytest.mark.parametrize("need", ["EMS", "FIRE", "SAR"])
def test_nearest_units_filters_by_type(db, need):
    units = get_nearest_units(*SCENARIO_2, need, db=db)
    expected = {u[0] for u in SEED_UNITS if u[2] == need}
    assert {u["unit_id"] for u in units} == expected
    assert all(u["unit_type"] == need for u in units)


def test_nearest_units_need_type_case_insensitive(db):
    assert get_nearest_units(*SCENARIO_2, "ems", db=db) == get_nearest_units(*SCENARIO_2, "EMS", db=db)
    assert get_nearest_units(*SCENARIO_2, "ANY", db=db) == get_nearest_units(*SCENARIO_2, "any", db=db)


def test_nearest_units_excludes_unavailable(db):
    db.get(models.Unit, "EMS-1").status = "busy"
    db.commit()
    ids = [u["unit_id"] for u in get_nearest_units(*SCENARIO_2, "EMS", db=db)]
    assert ids == ["EMS-2"]


def test_seed_placement_matches_scenarios(db):
    assert get_nearest_units(*SCENARIO_2, "any", db=db)[0]["unit_id"] == "EMS-1"
    assert get_nearest_units(*SCENARIO_3, "any", db=db)[0]["unit_id"] == "FIRE-1"
    for point in (SCENARIO_2, SCENARIO_3):
        ranked = [u["unit_id"] for u in get_nearest_units(*point, "any", db=db)]
        assert ranked[-1] == "SAR-1"  # farther out


def test_seed_units_at_least_300m_apart():
    for a, b in itertools.combinations(SEED_UNITS, 2):
        assert haversine_km(a[4], a[5], b[4], b[5]) >= 0.3, (a[0], b[0])


@pytest.mark.parametrize("args", [
    (91, -96.75, "EMS"), (32.98, -181, "EMS"), ("32.98", -96.75, "EMS"),
    (32.98, -96.75, "POLICE"), (32.98, -96.75, ""), (32.98, -96.75, None),
])
def test_nearest_units_bad_args(db, args):
    with pytest.raises(ValueError):
        get_nearest_units(*args, db=db)


# --- search_protocol -----------------------------------------------------------

@pytest.mark.parametrize("query,expected_first", [
    ("IR anomaly verify", "1. Escalating an IR anomaly to VERIFY"),
    ("industrial zone weighting", "2. Residential vs. industrial zone weighting"),
    ("likely_person signals required", "3. Signals required for likely_person"),
    ("unit type SAR EMS", "4. Unit type mapping"),
    ("urgent survey trapped", "5. Urgent review triggers from survey answers"),
    ("missing data unknown", "6. When data is missing"),
    ("operator override resolved", "7. Operator overrides"),
])
def test_search_protocol_top_hit(query, expected_first):
    results = search_protocol(query)
    assert 1 <= len(results) <= 3
    assert results[0]["section_title"] == expected_first
    assert all(set(r) == {"section_title", "excerpt"} for r in results)
    assert all(r["excerpt"] for r in results)


def test_search_protocol_no_match_returns_empty():
    assert search_protocol("xyzzy plugh") == []


@pytest.mark.parametrize("query", ["", "   ", "the and of", None, 42])
def test_search_protocol_bad_query(query):
    with pytest.raises(ValueError):
        search_protocol(query)


# --- create_incident_report ----------------------------------------------------

def _make_case(db):
    db.add(models.Robot(id="r1", sector="S1"))
    case = models.Case(robot_id="r1", sector="S1", missing_signals=["survey_response"])
    db.add(case)
    db.commit()
    return case


def test_incident_report_details_keys(db):
    case = _make_case(db)
    ranked = get_nearest_units(*SCENARIO_2, "EMS", db=db)
    out = create_incident_report(case.id, "possible_person", 0.45, "high", ["SAR", "EMS"],
                                 "IR + residential, no survey yet.", ranked,
                                 protocol_cited=["1. Escalating an IR anomaly to VERIFY"], db=db)
    report = db.get(models.IncidentReport, out["report_id"])
    assert report.case_id == case.id
    assert report.summary == "IR + residential, no survey yet."
    assert set(report.details) == set(REPORT_DETAIL_KEYS)
    assert len(REPORT_DETAIL_KEYS) == 7
    assert isinstance(report.details["nearest_relevant_units"], list)
    assert report.details["nearest_relevant_units"] == ranked
    assert report.details["missing_signals"] == ["survey_response"]  # defaults from case


@pytest.mark.parametrize("override", [
    {"case_id": 9999}, {"case_id": 0}, {"classification": "dead"}, {"confidence": 1.5},
    {"risk_level": "extreme"}, {"needs": ["POLICE"]}, {"needs": "EMS"}, {"rationale": " "},
    {"nearest_relevant_units": "EMS-1"},
])
def test_incident_report_bad_args(db, override):
    case = _make_case(db)
    kwargs = dict(case_id=case.id, classification="object", confidence=0.5, risk_level="low",
                  needs=[], rationale="ok", nearest_relevant_units=[])
    kwargs.update(override)
    with pytest.raises(ValueError):
        create_incident_report(**kwargs, db=db)
    assert db.query(models.IncidentReport).count() == 0


# --- registry + nemotron mock ------------------------------------------------------

def test_schemas_match_functions():
    assert {s["function"]["name"] for s in TOOL_SCHEMAS} == set(TOOL_FUNCTIONS)


def test_mock_mode_stub_shape(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    assert nemotron.mock_mode()
    msgs = [{"role": "user", "content": "hi"}]
    out = nemotron.chat_with_tools(msgs, TOOL_SCHEMAS)
    assert out == {"content": "mock: no tool calls executed", "messages": msgs,
                   "tool_calls": [], "iterations": 0, "truncated": False}


def test_mock_mode_placeholder_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "your_key_here")
    assert nemotron.mock_mode()
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-real")
    assert not nemotron.mock_mode()


class _FakeClient:
    """Scripted OpenAI-style client: replays a list of assistant messages."""

    def __init__(self, replies):
        from types import SimpleNamespace as NS
        self._replies = iter(replies)
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        from types import SimpleNamespace as NS
        return NS(choices=[NS(message=next(self._replies))])


def _msg(content=None, calls=()):
    from types import SimpleNamespace as NS
    return NS(content=content, tool_calls=[
        NS(id=f"c{i}", function=NS(name=n, arguments=a)) for i, (n, a) in enumerate(calls)
    ] or None)


def test_live_loop_dispatches_and_reports_errors(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr(nemotron, "get_client", lambda: _FakeClient([
        _msg(calls=[("search_protocol", '{"query": "unit type"}'),
                    ("search_protocol", '{"query": ""}'),
                    ("nope", "{}")]),
        _msg(content="done"),
    ]))
    out = nemotron.chat_with_tools([{"role": "user", "content": "go"}], TOOL_SCHEMAS)
    assert out["content"] == "done" and out["iterations"] == 2 and not out["truncated"]
    ok, bad, unknown = out["tool_calls"]
    assert ok["result"][0]["section_title"] == "4. Unit type mapping"
    assert "error" in bad["result"] and "error" in unknown["result"]
    assert [m["role"] for m in out["messages"]] == ["user", "assistant", "tool", "tool", "tool",
                                                     "assistant"]


def test_live_loop_truncates(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    loop = [_msg(calls=[("search_protocol", '{"query": "urgent"}')])] * 3
    monkeypatch.setattr(nemotron, "get_client", lambda: _FakeClient(loop))
    out = nemotron.chat_with_tools([], TOOL_SCHEMAS, max_iterations=3)
    assert out["truncated"] and out["iterations"] == 3 and len(out["tool_calls"]) == 3
    assert set(out) == {"content", "messages", "tool_calls", "iterations", "truncated"}


def test_nearest_units_distance_is_miles_rounded_to_tenth(db):
    """distance_mi = haversine km x 0.621371, rounded to 0.1 mi."""
    by_id = {u[0]: u for u in SEED_UNITS}
    for unit in get_nearest_units(*SCENARIO_2, "any", db=db):
        seed = by_id[unit["unit_id"]]
        km = haversine_km(SCENARIO_2[0], SCENARIO_2[1], seed[4], seed[5])
        assert unit["distance_mi"] == round(km * 0.621371, 1)
