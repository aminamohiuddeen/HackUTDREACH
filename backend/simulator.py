"""REACH robot simulator.

Posts to the same endpoints the ESP32 uses (/api/telemetry, /api/surveys),
tagged ?source=simulator so the dashboard can label the data.

Usage (server running on :8000):
    python simulator.py --scenario all
    python simulator.py --scenario 3 --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import sys

import httpx

STILL = {"accelerometer": {"x": 0.02, "y": -0.01, "z": 9.81},
         "gyroscope": {"x": 0.0, "y": 0.0, "z": 0.01}}


def telemetry(robot_id, sector, lat, lng, **fields):
    body = {
        "robot_id": robot_id,
        "sector": sector,
        "location": {"lat": lat, "lng": lng, "source": "gps"},
        "temperature_c": 29.0,
        "water_detected": False,
        "infrared_triggered": False,
        "anomaly_size_cm2": None,
        "motion_detected": False,
        "location_zone": "unknown",
        "heart_rate_bpm": None,
        "spo2_percent": None,
        **STILL,
    }
    body.update(fields)
    return body


SCENARIOS = {
    1: {
        "name": "No confirmed survivor",
        "telemetry": [
            telemetry("sim-rover-1", "S2", 32.9901, -96.7480, temperature_c=33.5,
                      water_detected=True, location_zone="industrial"),
            telemetry("sim-rover-1", "S2", 32.9903, -96.7478, temperature_c=34.1,
                      water_detected=True, location_zone="industrial"),
        ],
        "survey": None,
        "expect": {"classification": "object", "status": "cleared"},
    },
    2: {
        "name": "Survivor responds: injured + trapped + needs help",
        "telemetry": [
            telemetry("sim-rover-2", "S1", 32.9855, -96.7502, temperature_c=27.0,
                      infrared_triggered=True, anomaly_size_cm2=2200,
                      motion_detected=True, location_zone="residential"),
        ],
        "survey": {"robot_id": "sim-rover-2", "sector": "S1",
                   "answers": {"injured": "yes", "trapped": "yes",
                               "breathing_difficulty": "unknown",
                               "others_present": "no", "immediate_help": "yes"}},
        "expect": {"classification": "likely_person", "status": "ranked", "urgent": True},
    },
    3: {
        "name": "Water + human-sized IR in residential, no survey",
        "telemetry": [
            telemetry("sim-rover-3", "S4", 32.9710, -96.7555, temperature_c=24.5,
                      water_detected=True, infrared_triggered=True, anomaly_size_cm2=1500,
                      location_zone="residential"),
        ],
        "survey": None,
        "expect": {"classification": "possible_person", "status": "verify"},
    },
    4: {
        "name": "Hot small object in residential",
        "telemetry": [
            telemetry("sim-rover-4", "S1", 32.9860, -96.7490, temperature_c=41.0,
                      infrared_triggered=True, anomaly_size_cm2=50,
                      location_zone="residential"),
        ],
        "survey": None,
        # One uncorroborated signal (residential): object, unverified, never ranked.
        "expect": {"classification": "object", "status": "unverified"},
    },
}


def run_scenario(client: httpx.Client, num: int) -> tuple[bool, str]:
    sc = SCENARIOS[num]
    params = {"source": "simulator"}
    case = None
    for body in sc["telemetry"]:
        r = client.post("/api/telemetry", json=body, params=params)
        r.raise_for_status()
        case = r.json()["case"]
    if sc["survey"]:
        r = client.post("/api/surveys", json=sc["survey"], params=params)
        r.raise_for_status()
        case = r.json()["case"]

    exp = sc["expect"]
    actual = {k: case[k] for k in exp}
    ok = actual == exp
    fmt = lambda d: "/".join(str(d[k]) for k in ("classification", "status")) + \
        (" urgent" if d.get("urgent") else "")
    line = (f"[{'PASS' if ok else 'FAIL'}] Scenario {num} ({sc['name']}): "
            f"expected {fmt(exp)} | actual {fmt(case)} (rank={case['rank']}, case #{case['id']})")
    return ok, line


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--scenario", default="all", help="1-4 or 'all'")
    args = ap.parse_args(argv)

    nums = list(SCENARIOS) if args.scenario == "all" else [int(args.scenario)]
    all_ok = True
    with httpx.Client(base_url=args.base_url, timeout=10) as client:
        for n in nums:
            ok, line = run_scenario(client, n)
            all_ok &= ok
            print(line)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
