import random

import httpx
import pytest

import hardware_sync
import main

# What hardware/server.py's GET /state returns for the rescue pod (old firmware shape).
POD_STATE = {
    "latest_telemetry": {
        "REACH-01": {
            "unit_id": "REACH-01", "uptime_ms": 12345, "received_at": "2026-11-08T08:00:00",
            "sensors": {"motion_detected": True, "sound_level": 412, "loud_sound": False,
                        "object_close_ir": True, "temp_c": None, "humidity": None,
                        "accel_mag": 0, "robot_tipped": False, "impact": False,
                        "accel": {"x": 0, "y": 0, "z": 0}, "gyro_dps": {"x": 0, "y": 0, "z": 0}},
        }
    },
    "cases": [{
        "case_id": "REACH-01-1", "unit_id": "REACH-01", "received_at": "2026-11-08T08:01:00",
        "survey": {"injured": True, "can_move": False, "people_with_you": 2,
                   "hard_to_breathe": False, "needs_water_or_medication": True},
        "sensors": {},
    }],
}


@pytest.fixture
def pod_state(monkeypatch):
    main._hardware_seen.clear()
    state = {"value": POD_STATE}
    monkeypatch.setattr(hardware_sync, "fetch_state", lambda *a, **k: state["value"])
    yield state
    main._hardware_seen.clear()


def test_sync_ingests_pod_telemetry_and_survey_as_hardware(client, pod_state):
    r = client.get("/api/sync-hardware")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["telemetry_ingested"] == 1 and body["surveys_ingested"] == 1
    assert body["errors"] == []
    case = client.get(f"/api/cases/{body['case_ids'][0]}").json()
    assert case["source"] == "hardware"
    assert case["location"] is not None  # simulated GPS fix
    assert case["classification"] == "likely_person"  # survey answered
    assert case["surveys"][-1]["answers"] == {
        "injured": "yes", "trapped": "yes", "others_present": "yes",
        "breathing_difficulty": "no", "immediate_help": "yes"}
    t = case["telemetry"][-1]
    assert t["motion_detected"] is True and t["infrared_triggered"] is True
    assert t["source"] == "hardware"


def test_sync_reports_every_simulated_field(client, pod_state):
    sim = client.get("/api/sync-hardware").json()["simulated_fields"]["REACH-01"]
    # DHT read failed and IMU sent zeros, so those are simulated too.
    assert set(sim) == {"temperature_c", "accelerometer", "gyroscope",
                        "location", "water_detected", "location_zone"}


def test_sync_skips_already_ingested_entries(client, pod_state):
    client.get("/api/sync-hardware")
    again = client.get("/api/sync-hardware").json()
    assert again["telemetry_ingested"] == 0 and again["surveys_ingested"] == 0
    assert again["skipped_duplicates"] == 2


def test_sync_unreachable_hardware_is_502(client, monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr(hardware_sync, "fetch_state", boom)
    r = client.get("/api/sync-hardware")
    assert r.status_code == 502


def test_sync_requires_auth(raw_client):
    assert raw_client.get("/api/sync-hardware").status_code == 401


def test_real_readings_are_not_overwritten_by_simulation():
    data = {"unit_id": "REACH-01", "sensors": {
        "motion_detected": False, "object_close_ir": False, "temp_c": 31.5,
        "accel": {"x": 0.1, "y": 0.2, "z": 9.7}, "gyro_dps": {"x": 1.0, "y": 0.0, "z": -1.0}}}
    payload, sim = hardware_sync.pod_telemetry("REACH-01", data, random.Random(0))
    assert payload.temperature_c == 31.5
    assert payload.accelerometer.z == 9.7 and payload.gyroscope.x == 1.0
    assert "temperature_c" not in sim and "accelerometer" not in sim and "gyroscope" not in sim
    # Survivor evidence is never invented.
    assert payload.anomaly_size_cm2 is None and payload.heart_rate_bpm is None


def test_survey_unanswered_questions_stay_unknown():
    s = hardware_sync.pod_survey({"unit_id": "REACH-01", "survey": {"injured": False}})
    assert s.answers.injured == "no"
    assert s.answers.trapped == "unknown" and s.answers.others_present == "unknown"
