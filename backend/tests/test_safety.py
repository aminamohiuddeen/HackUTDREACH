"""Rationale-contradiction detection: agents.safety.find_rationale_conflict + wiring."""
import eval as reach_eval
import models
from agents.orchestrator import REPORT_KEYS
from agents.safety import find_rationale_conflict
from database import SessionLocal


# --- unit ---------------------------------------------------------------------

def test_object_with_survivor():
    assert find_rationale_conflict("Thermal suggests a survivor.", "object", "unverified") \
        == ["survivor"]


def test_verify_with_confirmed():
    assert find_rationale_conflict("Presence confirmed by IR.", "possible_person", "verify") \
        == ["confirmed"]


def test_verify_clean():
    text = ("IR and motion detected; a responder should get eyes on this possible person "
            "before any decision. Keep a safe distance from the unstable wall.")
    assert find_rationale_conflict(text, "possible_person", "verify") == []


def test_cleared_with_likely_person():
    assert find_rationale_conflict("Pattern matches likely_person.", "object", "cleared") \
        == ["likely_person"]


def test_case_insensitive_returns_exact_text():
    assert find_rationale_conflict("SURVIVOR seen", "object", "cleared") == ["SURVIVOR"]
    assert find_rationale_conflict("Confirmed by drone.", "possible_person", "verify") \
        == ["Confirmed"]


def test_safe_alone_never_matches():
    for status in ("verify", "unverified", "cleared", "ranked"):
        for cls in ("object", "possible_person", "likely_person", "unknown"):
            assert find_rationale_conflict("Hold a safe distance; use the safe room.",
                                           cls, status) == []


def test_safe_to_matches():
    assert find_rationale_conflict("Area is safe to enter.", "object", "unverified") \
        == ["safe to"]


def test_word_boundary_unconfirmed_does_not_match():
    assert find_rationale_conflict("Presence unconfirmed.", "possible_person", "verify") == []


def test_negation_until_confirmed_by_responder():
    text = "Treat as a possible person until confirmed by a responder."
    assert find_rationale_conflict(text, "possible_person", "verify") == []


def test_negation_not_confirmed():
    assert find_rationale_conflict("Presence not confirmed.", "possible_person", "verify") == []


def test_negation_never_confirmed():
    assert find_rationale_conflict("Presence was never confirmed.", "possible_person",
                                   "verify") == []


def test_confirmed_survivor_still_flags():
    assert find_rationale_conflict("Confirmed survivor at the site.", "possible_person",
                                   "verify") == ["Confirmed"]


def test_without_confirmation():
    # "confirmed" does not match inside "confirmation" (word boundaries), and
    # "confirmation" is deliberately not a phrase, so this is [] without any guard.
    assert find_rationale_conflict("Do not escalate without confirmation.", "possible_person",
                                   "verify") == []
    assert find_rationale_conflict("Requires confirmation by a responder.", "possible_person",
                                   "verify") == []


def test_negation_guard_other_negators_and_contractions():
    for text in ("No sighting confirmed yet.", "Pending a confirmed sighting.",
                 "Hasn't been confirmed.",
                 "Unless confirmed, hold.", "Neither seen nor confirmed."):
        assert find_rationale_conflict(text, "unknown", "unverified") == [], text


def test_negation_guard_stops_at_clause_boundary():
    assert find_rationale_conflict("No injuries. Confirmed survivor.", "possible_person",
                                   "verify") == ["Confirmed"]


def test_negation_guard_window_is_short():
    text = "Not yet reviewed by command staff; drone confirmed."
    assert find_rationale_conflict(text, "possible_person", "verify") == ["confirmed"]


def test_negation_guard_only_for_verify_and_unverified():
    # object / cleared rules are unguarded: "no survivor" on a cleared case still flags.
    assert find_rationale_conflict("No survivor found.", "object", "cleared") == ["survivor"]


def test_dedup_and_order_by_first_appearance():
    text = "Cleared earlier; now confirmed. Confirmed again, cleared."
    assert find_rationale_conflict(text, "unknown", "verify") == ["Cleared", "confirmed"]


def test_override_rationale_trips_every_non_ranked_status():
    text = "OVERRIDE: confirmed survivor, area cleared."
    assert find_rationale_conflict(text, "object", "unverified") == \
        ["confirmed", "survivor", "cleared"]
    assert find_rationale_conflict(text, "object", "cleared") == ["survivor"]
    assert find_rationale_conflict(text, "possible_person", "verify") == ["confirmed", "cleared"]
    assert find_rationale_conflict(text, "likely_person", "ranked") == []  # no rule for ranked


def test_non_string_or_empty():
    assert find_rationale_conflict(None, "object", "cleared") == []
    assert find_rationale_conflict("   ", "object", "cleared") == []


# --- integration --------------------------------------------------------------

def _post_ir_only_case(client, telemetry_payload, robot_id="safety-r1"):
    """IR only in an industrial zone -> object / unverified (one uncorroborated signal)."""
    r = client.post("/api/telemetry", json=telemetry_payload(
        robot_id=robot_id, infrared_triggered=True, anomaly_size_cm2=900.0))
    assert r.status_code == 201, r.text
    return r.json()["case_id"]


def _scenario_for(client, case_id):
    case = client.get(f"/api/cases/{case_id}").json()
    return {"id": 1, "expected": {"classification": case["classification"],
                                  "status": case["status"]}}


def test_analyze_clean_run_has_empty_conflict_and_persists_it(client, telemetry_payload):
    case_id = _post_ir_only_case(client, telemetry_payload)
    assert client.get(f"/api/cases/{case_id}").json()["latest_report"] is None

    body = client.post(f"/api/cases/{case_id}/analyze").json()
    rep = body["report"]
    assert tuple(rep) == REPORT_KEYS
    assert body["mode"] == "mock" and rep["rationale_conflict"] == []
    with SessionLocal() as s:
        assert s.get(models.IncidentReport, rep["report_id"]).details["rationale_conflict"] == []

    latest = client.get(f"/api/cases/{case_id}").json()["latest_report"]
    assert latest["report_id"] == rep["report_id"]
    assert latest["rationale"] == rep["rationale"]
    assert latest["rationale_conflict"] == []
    assert latest["classification"] == rep["classification"]
    assert latest["status"] == rep["status"]
    assert latest["created_at"]


def test_scripted_override_run_flags_conflict_in_response_and_get(client, telemetry_payload):
    case_id = _post_ir_only_case(client, telemetry_payload)
    sc = _scenario_for(client, case_id)
    with reach_eval.model_mode(reach_eval.SCRIPTED, "override", sc, "safety-r1"):
        body = client.post(f"/api/cases/{case_id}/analyze").json()
    rep = body["report"]
    assert body["mode"] == "live"
    assert (rep["classification"], rep["status"]) == ("object", "unverified")  # not overridden
    assert rep["rationale_conflict"] == ["confirmed", "survivor", "cleared"]
    latest = client.get(f"/api/cases/{case_id}").json()["latest_report"]
    assert latest["rationale_conflict"] == rep["rationale_conflict"]


def test_scripted_override_persists_conflict_in_db_row(client, telemetry_payload):
    """Guards persistence: assert against the IncidentReport row, not the response."""
    case_id = _post_ir_only_case(client, telemetry_payload)
    sc = _scenario_for(client, case_id)
    with reach_eval.model_mode(reach_eval.SCRIPTED, "override", sc, "safety-r1"):
        assert client.post(f"/api/cases/{case_id}/analyze").status_code == 200
    with SessionLocal() as s:
        rows = list(s.query(models.IncidentReport).filter_by(case_id=case_id))
        assert len(rows) == 1
        details = rows[0].details
        assert details["rationale_conflict"]  # non-empty
        assert set(details["rationale_conflict"]) == {"confirmed", "survivor", "cleared"}
        assert details["status"] == "unverified"
        assert "OVERRIDE" in rows[0].summary
