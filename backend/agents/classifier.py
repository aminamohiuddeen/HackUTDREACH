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


# ---------------------------------------------------------------------------
# Classifier AGENT (Phase 3b). Everything above this line is the pure,
# deterministic classifier and is unchanged. The agent below does I/O, but it
# never decides: classification/confidence/status/missing_signals always come
# from classify_case(). The agent only justifies, cites protocol, and
# summarizes. Imports are lazy so `from agents.classifier import classify_case`
# stays free of DB/LLM side effects.
# ---------------------------------------------------------------------------

CLASSIFIER_TOOLS = ("get_case_evidence", "get_sensor_history", "search_protocol")
_SAFETY_TAIL = ("This summary does not diagnose injuries, declare any area safe, "
                "or select response units.")


def protocol_required(base: dict) -> bool:
    return base["status"] == "verify" or base["classification"] == "possible_person"


def protocol_query(base: dict) -> str:
    parts = ["escalating IR anomaly to VERIFY", base["classification"].replace("_", " ")]
    parts += [s.replace("_", " ") for s in base.get("signals", [])]
    if base["classification"] == "unknown" or "telemetry" in base["missing_signals"] \
            or "anomaly_size_cm2" in base["missing_signals"]:
        parts.append("when data is missing")
    return " ".join(parts)


def _base_rationale(base: dict, protocol_cited: str) -> str:
    signals = ", ".join(base.get("signals") or []) or "none"
    missing = ", ".join(base["missing_signals"]) or "none"
    text = (f"Deterministic classifier result: {base['classification']} "
            f"(confidence {base['confidence']}), status {base['status']}. "
            f"Observed signals: {signals}. Missing signals: {missing}.")
    if base.get("urgent"):
        text += (" Survey answers flag this case for urgent human review: "
                 f"{', '.join(base['urgent_reasons'])}.")
    if protocol_cited:
        text += f" Protocol cited: {protocol_cited}."
    return f"{text} {_SAFETY_TAIL}"


def _output(base: dict, protocol_cited: str, rationale: str) -> dict:
    # The six contract keys, plus classify_case() pass-throughs the coordinator needs.
    return {
        "classification": base["classification"], "confidence": base["confidence"],
        "status": base["status"], "missing_signals": list(base["missing_signals"]),
        "protocol_cited": protocol_cited, "rationale": rationale,
        "signals": list(base.get("signals") or []), "urgent": bool(base.get("urgent")),
        "urgent_reasons": list(base.get("urgent_reasons") or []),
    }


def _titles(entries: list[dict]) -> list[str]:
    return [r["section_title"] for e in entries if e["tool"] == "search_protocol"
            for r in e["observation"].get("results", []) if r.get("section_title")]


def base_classification(case) -> dict:
    from agents.common import pick_survey

    return classify_case(case.telemetry, pick_survey(case))


def run_classifier_mock(case, db) -> tuple[dict, list[dict], int, bool]:
    """Deterministic path (no LLM): the calls the agent would make, via the real local tools."""
    from agents.common import call_tool, log_entry

    base = base_classification(case)
    entries = [log_entry("classifier", "get_case_evidence", {"case_id": case.id},
                         call_tool("get_case_evidence", db, case_id=case.id))]
    protocol_cited = ""
    if protocol_required(base):
        q = {"query": protocol_query(base)}
        entries.append(log_entry("classifier", "search_protocol", q,
                                 call_tool("search_protocol", db, **q)))
        titles = _titles(entries)
        protocol_cited = titles[0] if titles else ""
    return _output(base, protocol_cited, _base_rationale(base, protocol_cited)), entries, 0, False


def _system_prompt(must_search: bool) -> str:
    search_rule = (
        "This case is VERIFY or possible_person: you MUST call search_protocol and set "
        "protocol_cited to the exact section_title you relied on."
        if must_search else
        "You may call search_protocol if a protocol section supports your summary; otherwise "
        "set protocol_cited to an empty string."
    )
    return (
        "You are the REACH classifier agent supporting human disaster responders. A "
        "deterministic rule-based classifier has already produced the authoritative "
        "classification, confidence, status and missing_signals given below. Do not change "
        "them. Your job is to justify, cite protocol, and summarize, not to decide.\n"
        "Rules: never diagnose injuries; never declare an area safe or clear; never suggest, "
        "rank or pick response units.\n"
        "Before EVERY tool call, set your message content to a JSON object "
        '{"reasoning_summary": "<one short sentence on why you are calling this tool>"}.\n'
        f"{search_rule}\n"
        "When finished, reply with ONLY a JSON object with keys: reasoning_summary, "
        "classification, confidence, status, missing_signals, protocol_cited, rationale "
        "(2-4 plain sentences for a responder)."
    )


def run_classifier_agent(case, db, max_iterations: int) -> tuple[dict, list[dict], int, bool]:
    """Live agent loop. Returns (output, tool_log_entries, model_iterations, truncated)."""
    import json

    import nemotron
    from agents.common import (bound_tool, call_tool, entries_from_chat, log_entry,
                               parse_json_object, tool_schemas)

    base = base_classification(case)
    must_search = protocol_required(base)

    # get_case_evidence always runs first: the agent code issues it before the model's
    # first turn and hands it to the model as a completed tool call. thought=None,
    # because no model output preceded it.
    evidence = call_tool("get_case_evidence", db, case_id=case.id)
    entries = [log_entry("classifier", "get_case_evidence", {"case_id": case.id}, evidence)]
    seed = [
        {"role": "system", "content": _system_prompt(must_search)},
        {"role": "user", "content": f"Case {case.id}. Authoritative classifier output: "
                                    f"{json.dumps(base)}"},
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "seed_evidence", "type": "function",
            "function": {"name": "get_case_evidence",
                         "arguments": json.dumps({"case_id": case.id})}}]},
        {"role": "tool", "tool_call_id": "seed_evidence",
         "content": json.dumps(evidence, default=str)},
    ]

    iterations, truncated, final = 0, False, {}
    if max_iterations > 0:
        chat = nemotron.chat_with_tools(
            seed, tool_schemas(CLASSIFIER_TOOLS), max_iterations=max_iterations,
            tool_functions={n: bound_tool(n, db) for n in CLASSIFIER_TOOLS})
        entries += entries_from_chat("classifier", chat, len(seed))
        iterations, truncated = chat["iterations"], chat["truncated"]
        final = (parse_json_object(chat["content"]) or {}) if not truncated else {}

    titles = _titles(entries)
    if must_search and not titles:
        # A required search the model did not make: the agent code makes it. thought=None.
        q = {"query": protocol_query(base)}
        entries.append(log_entry("classifier", "search_protocol", q,
                                 call_tool("search_protocol", db, **q)))
        titles = _titles(entries)

    # Cite what the model named if search_protocol actually returned it. If sections were
    # retrieved but no valid citation was given, default to the top section of the first
    # search (titles is in retrieval order). Required or not, a retrieval is cited.
    cited = final.get("protocol_cited")
    if isinstance(cited, str) and cited in titles:
        protocol_cited = cited
    else:
        protocol_cited = titles[0] if titles else ""
    rationale = final.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        rationale = _base_rationale(base, protocol_cited)
    return _output(base, protocol_cited, rationale.strip()), entries, iterations, truncated
