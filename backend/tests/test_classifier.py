from agents.classifier import classify_case


def tel(**overrides):
    base = {
        "robot_id": "r1",
        "sector": "S1",
        "location": {"lat": 32.98, "lng": -96.75, "source": "gps"},
        "temperature_c": 30.0,
        "water_detected": False,
        "infrared_triggered": False,
        "anomaly_size_cm2": None,
        "motion_detected": False,
        "location_zone": "industrial",
        "accelerometer": {"x": 0, "y": 0, "z": 9.81},
        "gyroscope": {"x": 0, "y": 0, "z": 0},
        "heart_rate_bpm": None,
        "spo2_percent": None,
    }
    base.update(overrides)
    return base


def survey(**answers):
    full = {q: "unknown" for q in
            ("injured", "trapped", "breathing_difficulty", "others_present", "immediate_help")}
    full.update(answers)
    return {"robot_id": "r1", "sector": "S1", "answers": full}


# --- The four required paths -------------------------------------------------

def test_path1_no_survivor_object_cleared():
    r = classify_case([tel(water_detected=True, temperature_c=34.0)], None)
    assert r["classification"] == "object"
    assert r["status"] == "cleared"
    assert "survey_response" in r["missing_signals"]


def test_path2_survey_response_likely_person_ranked_urgent():
    r = classify_case(
        [tel(location_zone="residential", motion_detected=True)],
        survey(injured="yes", trapped="yes", immediate_help="yes"),
    )
    assert r["classification"] == "likely_person"
    assert r["status"] == "ranked"
    assert r["urgent"] is True
    assert set(r["urgent_reasons"]) == {"injured", "trapped", "immediate_help"}


def test_path3_ir_human_sized_residential_no_survey_verify():
    r = classify_case(
        [tel(water_detected=True, infrared_triggered=True, anomaly_size_cm2=1500,
             location_zone="residential")],
        None,
    )
    assert r["classification"] == "possible_person"
    assert r["status"] == "verify"
    assert r["status"] != "ranked"
    assert "survey_response" in r["missing_signals"]


def test_path4_hot_small_object_residential_not_ranked():
    r = classify_case(
        [tel(infrared_triggered=True, anomaly_size_cm2=50, location_zone="residential")], None
    )
    assert r["classification"] == "object"
    # residential is one uncorroborated signal -> unverified, not cleared, not ranked
    assert r["status"] == "unverified"


def test_single_ir_signal_industrial_unverified_not_cleared():
    r = classify_case([tel(infrared_triggered=True, anomaly_size_cm2=1500,
                           location_zone="industrial")], None)
    assert r["classification"] == "object"
    assert r["status"] == "unverified"


def test_single_motion_signal_unverified():
    r = classify_case([tel(motion_detected=True, location_zone="road")], None)
    assert r["status"] == "unverified"


# --- Safety invariants -------------------------------------------------------

def test_ir_alone_never_likely_or_ranked():
    for area in (None, 50, 400, 1500, 8000, 20000):
        for zone in ("industrial", "road", "unknown", "residential"):
            r = classify_case([tel(infrared_triggered=True, anomaly_size_cm2=area,
                                   location_zone=zone)], None)
            assert r["classification"] != "likely_person"
            assert r["status"] != "ranked"


def test_two_signals_without_survey_not_ranked():
    r = classify_case([tel(infrared_triggered=True, anomaly_size_cm2=2000,
                           motion_detected=True, location_zone="residential")], None)
    assert r["classification"] == "possible_person"
    assert r["status"] == "verify"


def test_survey_alone_ranks():
    r = classify_case([], survey(trapped="yes"))
    assert r["classification"] == "likely_person"
    assert r["status"] == "ranked"
    assert r["urgent"] is True


def test_survey_alone_with_unremarkable_telemetry_ranks():
    r = classify_case([tel()], survey(injured="no"))
    assert r["classification"] == "likely_person"
    assert r["status"] == "ranked"
    assert r["urgent"] is False


def test_all_unknown_survey_is_not_a_response():
    r = classify_case([tel(location_zone="residential", motion_detected=True)], survey())
    assert "survey_response" not in r["signals"]
    assert r["status"] == "verify"  # two sensor signals, no response


def test_missing_anomaly_size_is_unknown_not_safe():
    r = classify_case([tel(infrared_triggered=True, anomaly_size_cm2=None)], None)
    assert r["status"] == "verify"
    assert "anomaly_size_cm2" in r["missing_signals"]


def test_no_data_is_unknown():
    r = classify_case([], None)
    assert r["classification"] == "unknown"
    assert r["status"] == "verify"
    assert "telemetry" in r["missing_signals"]


def test_unknown_zone_reported_missing():
    r = classify_case([tel(location_zone="unknown")], None)
    assert "location_zone" in r["missing_signals"]


def test_anomaly_size_bounds_inclusive():
    for area, expected in ((399.9, False), (400, True), (8000, True), (8000.1, False)):
        r = classify_case([tel(infrared_triggered=True, anomaly_size_cm2=area)], None)
        assert ("ir_human_sized_anomaly" in r["signals"]) is expected


def test_survey_no_answers_not_urgent():
    r = classify_case([tel(location_zone="residential")],
                      survey(injured="no", trapped="no", breathing_difficulty="no",
                             immediate_help="no", others_present="no"))
    assert r["status"] == "ranked"
    assert r["urgent"] is False


def test_output_has_no_diagnosis_fields():
    r = classify_case([tel(heart_rate_bpm=150, spo2_percent=80)], survey(injured="yes"))
    assert set(r) == {"classification", "confidence", "status", "missing_signals",
                      "signals", "urgent", "urgent_reasons"}
