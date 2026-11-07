"""Deterministic, rule-based case classifier for REACH.

Pure: no I/O, no database, no LLM. Accepts telemetry/survey as dicts, Pydantic
models, or ORM rows (anything with the right keys/attributes).

Safety rules (see protocol_kb/triage_protocols.md):
  * A survey response (any yes/no answer) => likely_person / ranked on its own.
  * Without a survey, >= 2 corroborating signals => possible_person / verify
    (never ranked); exactly 1 signal => object / unverified (never cleared).
  * infrared_triggered on its own can never yield likely_person or ranked.
  * Missing data is reported as missing, never treated as "safe".
  * Survey answers drive *review urgency* only. Nothing here diagnoses injuries.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

HUMAN_ANOMALY_MIN_CM2 = 400.0
HUMAN_ANOMALY_MAX_CM2 = 8000.0
SURVEY_WAIT_SECONDS = 300  # how long a VERIFY case waits for a survey response

SIGNAL_IR_HUMAN_SIZED = "ir_human_sized_anomaly"
SIGNAL_MOTION = "motion_detected"
SIGNAL_RESIDENTIAL = "residential_zone"
SIGNAL_SURVEY = "survey_response"
ALL_SIGNALS = (SIGNAL_IR_HUMAN_SIZED, SIGNAL_MOTION, SIGNAL_RESIDENTIAL, SIGNAL_SURVEY)

SURVEY_QUESTIONS = ("injured", "trapped", "breathing_difficulty", "others_present", "immediate_help")
URGENT_QUESTIONS = ("injured", "trapped", "breathing_difficulty", "immediate_help")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def is_human_sized(area_cm2: float | None) -> bool:
    return area_cm2 is not None and HUMAN_ANOMALY_MIN_CM2 <= area_cm2 <= HUMAN_ANOMALY_MAX_CM2


def survey_responded(survey: Any) -> bool:
    """True if someone actually answered: at least one answer is yes/no.

    A survey where every answer is "unknown" means nobody responded.
    """
    answers = _get(survey, "answers")
    if not answers:
        return False
    return any(_get(answers, q) in ("yes", "no") for q in SURVEY_QUESTIONS)


def urgent_review(survey: Any) -> dict:
    """Flag a case for urgent human review from survey answers. Not a diagnosis."""
    if not survey_responded(survey):
        return {"urgent": False, "urgent_reasons": []}
    answers = _get(survey, "answers")
    reasons = [q for q in URGENT_QUESTIONS if _get(answers, q) == "yes"]
    return {"urgent": bool(reasons), "urgent_reasons": reasons}


def classify_case(telemetry_list: Iterable[Any] | None, survey: Any = None) -> dict:
    """Classify a case from its telemetry history and (latest) survey.

    Returns a dict with classification, confidence, status, and missing_signals,
    plus the signals that were observed and survey-driven urgency flags.
    """
    telemetry = list(telemetry_list or [])
    has_survey = survey_responded(survey)

    signals: set[str] = set()
    ir_size_unknown = False
    zones_known = False
    for t in telemetry:
        if _get(t, "infrared_triggered") is True:
            area = _get(t, "anomaly_size_cm2")
            if area is None:
                ir_size_unknown = True
            elif is_human_sized(area):
                signals.add(SIGNAL_IR_HUMAN_SIZED)
        if _get(t, "motion_detected") is True:
            signals.add(SIGNAL_MOTION)
        zone = _get(t, "location_zone")
        if zone not in (None, "unknown"):
            zones_known = True
        if zone == "residential":
            signals.add(SIGNAL_RESIDENTIAL)
    if has_survey:
        signals.add(SIGNAL_SURVEY)

    missing = [s for s in ALL_SIGNALS if s not in signals]
    if not telemetry:
        missing.append("telemetry")
    if ir_size_unknown and SIGNAL_IR_HUMAN_SIZED not in signals:
        missing.append("anomaly_size_cm2")
    if telemetry and not zones_known:
        missing.append("location_zone")

    n = len(signals)
    if not telemetry and not has_survey:
        # Nothing to go on: stay unknown, never cleared.
        classification, status, confidence = "unknown", "verify", 0.0
    elif has_survey:
        # A real answer is direct evidence of a responsive person: ranks on its own.
        classification, status = "likely_person", "ranked"
        confidence = min(0.95, 0.65 + 0.1 * (n - 1))
    elif n >= 2:
        # e.g. IR + human-sized anomaly + residential, no survey yet. Never ranked.
        classification, status = "possible_person", "verify"
        confidence = min(0.6, 0.25 + 0.1 * n)
    elif ir_size_unknown:
        # IR fired but the anomaly size is missing: unknown, not safe.
        classification, status, confidence = "possible_person", "verify", 0.3
    elif n == 1:
        # One uncorroborated signal: probably an object, but nobody has confirmed it.
        classification, status, confidence = "object", "unverified", 0.5
    else:
        # No anomaly signals at all.
        classification, status, confidence = "object", "cleared", 0.6

    return {
        "classification": classification,
        "confidence": round(confidence, 2),
        "status": status,
        "missing_signals": missing,
        "signals": [s for s in ALL_SIGNALS if s in signals],
        **urgent_review(survey),
    }
