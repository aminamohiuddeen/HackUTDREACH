import os

os.environ["DATABASE_URL"] = "sqlite://"  # in-memory; must be set before importing the app

import pytest
from fastapi.testclient import TestClient

import main
from database import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def no_live_nvidia(monkeypatch):
    """Mock mode by default, whatever .env says. Live-path tests install a fake client."""
    import nemotron

    monkeypatch.setenv("NVIDIA_API_KEY", "")

    def _refuse():
        raise AssertionError("test attempted a live NVIDIA call")

    monkeypatch.setattr(nemotron, "get_client", _refuse)


@pytest.fixture
def seed_scenarios():
    """Post simulator scenarios 1-4 through the API so case ids 1-4 match the scenarios."""
    import simulator

    def run(c):
        for n in (1, 2, 3, 4):
            sc = simulator.SCENARIOS[n]
            for t in sc["telemetry"]:
                assert c.post("/api/telemetry", json=t).status_code == 201
            if sc["survey"]:
                assert c.post("/api/surveys", json=sc["survey"]).status_code == 201
    return run


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    with SessionLocal() as db:
        main.init_db(db)
    with TestClient(main.app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine)
    with SessionLocal() as s:
        main.init_db(s)
        yield s
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def telemetry_payload():
    def make(**overrides):
        body = {
            "robot_id": "r1",
            "sector": "S1",
            "location": {"lat": 32.98, "lng": -96.75, "source": "gps"},
            "temperature_c": 30.0,
            "water_detected": False,
            "infrared_triggered": False,
            "anomaly_size_cm2": None,
            "motion_detected": False,
            "location_zone": "industrial",
            "accelerometer": {"x": 0.0, "y": 0.0, "z": 9.81},
            "gyroscope": {"x": 0.0, "y": 0.0, "z": 0.0},
            "heart_rate_bpm": None,
            "spo2_percent": None,
        }
        body.update(overrides)
        return body
    return make
