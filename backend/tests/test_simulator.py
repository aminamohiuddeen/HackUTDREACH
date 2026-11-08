import pytest

import simulator


@pytest.mark.parametrize("num", sorted(simulator.SCENARIOS))
def test_scenario_through_api(client, num):
    ok, line = simulator.run_scenario(client, num)
    assert ok, line


def test_simulator_tags_source(client):
    simulator.run_scenario(client, 2)
    cases = client.get("/api/cases").json()
    detail = client.get(f"/api/cases/{cases[0]['id']}").json()
    assert all(t["source"] == "simulator" for t in detail["telemetry"])
    assert all(s["source"] == "simulator" for s in detail["surveys"])
    assert cases[0]["rank"] == 1
