"""Bridge from the hardware team's rescue-pod test server to the REACH ingest pipeline.

The pod (rescue_pod.ino) may still post to hardware/server.py, which exposes everything it
received at GET /state:

    {"latest_telemetry": {"<unit_id>": {"unit_id", "uptime_ms", "sensors": {...}, "received_at"}},
     "cases": [{"case_id", "unit_id", "survey": {...}, "sensors": {...}, "received_at"}]}

These helpers map that shape onto TelemetryIn / SurveyIn. Readings the pod cannot provide
(no GPS, no water sensor; DHT/IMU failures) are filled with simulated values so the dashboard
and analysis have a complete record; every simulated field is reported back to the caller.
Survivor evidence (anomaly size, vitals) is never simulated, since it would change how a case
is classified.
"""
from __future__ import annotations

import os
import random
from typing import Any

import httpx

from schemas import SurveyIn, TelemetryIn

STATE_URL = os.getenv("HARDWARE_STATE_URL", "https://anthology-reheat-mystified.ngrok-free.dev/state")
SECTOR = os.getenv("HARDWARE_SECTOR", "S1")
ZONE = os.getenv("HARDWARE_ZONE", "residential")
# Simulated GPS fix for a pod without GPS: near the S1 simulator scenarios and seeded units.
BASE_LAT = float(os.getenv("HARDWARE_LAT", "32.9855"))
BASE_LNG = float(os.getenv("HARDWARE_LNG", "-96.7502"))

STILL_ACCEL = {"x": 0.02, "y": -0.01, "z": 9.81}  # pod at rest, matches simulator.py
STILL_GYRO = {"x": 0.0, "y": 0.0, "z": 0.01}


def fetch_state(url: str | None = None, timeout: float = 8.0) -> dict:
    """GET the pod server's /state. Raises httpx.HTTPError or ValueError on failure."""
    r = httpx.get(url or STATE_URL, timeout=timeout,
                  headers={"ngrok-skip-browser-warning": "true", "Accept": "application/json"})
    r.raise_for_status()
    body = r.json()
    if not isinstance(body, dict):
        raise ValueError("hardware /state did not return a JSON object")
    return body


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _vec(v: Any) -> dict | None:
    """{"x","y","z"} numbers, or None when absent or all zero (the pod sends zeros without an IMU)."""
    if not isinstance(v, dict):
        return None
    xyz = {k: _num(v.get(k)) for k in ("x", "y", "z")}
    if any(n is None for n in xyz.values()) or all(n == 0 for n in xyz.values()):
        return None
    return xyz


def pod_telemetry(unit_id: str, data: dict, rng: random.Random) -> tuple[TelemetryIn, list[str]]:
    """Map one /state telemetry entry to TelemetryIn; returns (payload, simulated field names)."""
    s = data.get("sensors") if isinstance(data.get("sensors"), dict) else {}
    simulated: list[str] = []

    temp = _num(s.get("temp_c"))
    if temp is None:
        temp = round(rng.uniform(22.0, 30.0), 1)
        simulated.append("temperature_c")
    accel = _vec(s.get("accel"))
    if accel is None:
        accel = dict(STILL_ACCEL)
        simulated.append("accelerometer")
    gyro = _vec(s.get("gyro_dps"))
    if gyro is None:
        gyro = dict(STILL_GYRO)
        simulated.append("gyroscope")
    # No GPS, water sensor or zone knowledge on the pod.
    location = {"lat": round(BASE_LAT + rng.uniform(-0.0005, 0.0005), 6),
                "lng": round(BASE_LNG + rng.uniform(-0.0005, 0.0005), 6), "source": "gps"}
    simulated += ["location", "water_detected", "location_zone"]

    payload = TelemetryIn(
        robot_id=str(data.get("unit_id") or unit_id),
        sector=SECTOR,
        location=location,
        temperature_c=temp,
        water_detected=False,
        # IR *proximity* sensor on the pod (object close), not thermal.
        infrared_triggered=bool(s.get("object_close_ir")),
        motion_detected=bool(s.get("motion_detected")),
        location_zone=ZONE,
        accelerometer=accel,
        gyroscope=gyro,
    )
    return payload, simulated


def _yes_no(v: Any) -> str:
    return "unknown" if v is None else ("yes" if bool(v) else "no")


def pod_survey(case: dict, default_unit: str = "REACH-01") -> SurveyIn:
    """Map one /state case (the pod's 5-question OLED survey) to SurveyIn."""
    sv = case.get("survey") if isinstance(case.get("survey"), dict) else {}
    can_move = sv.get("can_move")
    people = _num(sv.get("people_with_you"))
    return SurveyIn(
        robot_id=str(case.get("unit_id") or default_unit),
        sector=SECTOR,
        answers={
            "injured": _yes_no(sv.get("injured")),
            "trapped": "unknown" if can_move is None else ("no" if can_move else "yes"),
            "others_present": "unknown" if people is None else ("yes" if people > 0 else "no"),
            "breathing_difficulty": _yes_no(sv.get("hard_to_breathe")),
            "immediate_help": _yes_no(sv.get("needs_water_or_medication")),
        },
    )
