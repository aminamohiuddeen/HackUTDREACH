"""Coordinator agent: turns the classifier's output into an incident report.

It consumes the classifier output and never reclassifies. It maps needs, lists
nearby units, and saves the report through create_incident_report.

Hard limits, enforced in code and not only in the prompt:
  * It never writes Case.assigned_unit_id and never names a single unit as "the
    assignment". nearest_relevant_units is the ranked list from get_nearest_units,
    passed through unmodified, for humans to choose from.
  * It never dispatches, closes cases, or declares areas safe.
  * The model supplies only the rationale text. needs, risk_level, the unit list,
    protocol_cited and missing_signals are computed here and override whatever
    the model passes to create_incident_report.
"""
from __future__ import annotations

import json
from typing import Any

from agents.common import (bound_tool, call_tool, entries_from_chat, log_entry,
                           pick_survey, tool_schemas)

COORDINATOR_TOOLS = ("get_sector_status", "get_nearest_units", "create_incident_report")
NEED_ORDER = ("EMS", "FIRE", "SAR")

NO_COORDS_NOTE = "No coordinates recorded for this case; nearest units were not computed."
NO_NEED_NOTE = ("No specific need identified from survey answers; "
                "unit suggestion not generated.")
UNITS_NOTE = ("Units listed are ranked suggestions for responders to choose from; "
              "none has been assigned or dispatched.")


def survey_answers(case) -> dict:
    s = pick_survey(case)
    return dict(s.answers or {}) if s is not None else {}


def compute_needs(cls_out: dict, answers: dict) -> tuple[list[str], dict[str, list[str]]]:
    """Needs from the classifier's status plus survey answers. A case can have several.

    trapped -> FIRE + SAR (forcible entry + rescue; protocol section 4)
    injured / breathing_difficulty / immediate_help -> EMS
    others_present -> SAR (possible missing persons)
    status verify -> SAR (eyes on to confirm)
    """
    reasons: dict[str, list[str]] = {}

    def add(need: str, why: str) -> None:
        reasons.setdefault(need, []).append(why)

    if answers.get("trapped") == "yes":
        add("FIRE", "trapped=yes")
        add("SAR", "trapped=yes")
    for q in ("injured", "breathing_difficulty", "immediate_help"):
        if answers.get(q) == "yes":
            add("EMS", f"{q}=yes")
    if answers.get("others_present") == "yes":
        add("SAR", "others_present=yes")
    if cls_out["status"] == "verify":
        add("SAR", "status=verify")
    needs = [n for n in NEED_ORDER if n in reasons]
    return needs, {n: reasons[n] for n in needs}


def risk_level(cls_out: dict) -> str:
    """Risk level from the classifier's status and urgent flag.

        ranked + urgent  -> critical   (responsive person whose survey flags urgent review)
        ranked           -> high       (responsive person, no urgent flags)
        verify           -> high       (possible person, unconfirmed: needs eyes on)
        unverified       -> medium     (one uncorroborated signal, not cleared)
        cleared          -> low        (no anomaly signals; NOT a declaration of safety)
    Any other status falls back to "high" so unknown states are never downgraded.
    """
    status = cls_out["status"]
    if status == "ranked":
        return "critical" if cls_out.get("urgent") else "high"
    return {"verify": "high", "unverified": "medium", "cleared": "low"}.get(status, "high")


def merge_units(lists: list[list[dict]]) -> list[dict]:
    """Merge ranked lists: dedupe by unit_id keeping the shortest distance, nearest first."""
    best: dict[str, dict] = {}
    for ranked in lists:
        for u in ranked:
            uid = u.get("unit_id")
            if uid is not None and (uid not in best or u["distance_km"] < best[uid]["distance_km"]):
                best[uid] = u
    return sorted(best.values(), key=lambda u: (u["distance_km"], u["unit_id"]))


class _Run:
    """State for one coordinator run, shared by the live and mock paths."""

    def __init__(self, case, db, cls_out: dict):
        self.case, self.db, self.cls = case, db, cls_out
        self.answers = survey_answers(case)
        self.needs, self.need_reasons = compute_needs(cls_out, self.answers)
        self.risk = risk_level(cls_out)
        self.has_coords = case.lat is not None and case.lng is not None
        self.unit_lists: dict[str, list[dict]] = {}
        self.report_id: int | None = None
        self.effective: list[tuple[Any, dict]] = []  # (result object, args actually used)

    # --- deterministic text ------------------------------------------------
    def notes(self) -> list[str]:
        out = []
        if not self.needs:
            out.append(NO_NEED_NOTE)
        elif not self.has_coords:
            out.append(NO_COORDS_NOTE)
        else:
            out.append(UNITS_NOTE)
        return out

    def template_rationale(self) -> str:
        parts = [self.cls["rationale"]]
        if self.needs:
            parts.append("Suggested response capabilities for human review: " + "; ".join(
                f"{n} ({', '.join(self.need_reasons[n])})" for n in self.needs) + ".")
        parts.append(f"Risk level {self.risk} (from classifier status {self.cls['status']}"
                     f"{', urgent' if self.cls.get('urgent') else ''}).")
        return " ".join(parts + self.notes())

    def missing_needs(self) -> list[str]:
        return [n for n in self.needs if n not in self.unit_lists] if self.has_coords else []

    def nearest_units(self) -> list[dict]:
        return merge_units([self.unit_lists[n] for n in self.needs if n in self.unit_lists])

    # --- guarded tools -----------------------------------------------------
    def get_nearest_units(self, need_type: Any = None, **_ignored) -> Any:
        if not self.has_coords:
            result: Any = {"error": NO_COORDS_NOTE}
            self.effective.append((result, {"need_type": need_type}))
            return result
        nt = need_type.strip().upper() if isinstance(need_type, str) else need_type
        args = {"lat": self.case.lat, "lng": self.case.lng, "need_type": nt}
        if nt not in self.needs:
            result = {"error": f"need_type must be one of the identified needs {self.needs}"}
        else:
            result = call_tool("get_nearest_units", self.db, **args)
            if isinstance(result, list) and nt not in self.unit_lists:
                self.unit_lists[nt] = result
        self.effective.append((result, args))
        return result

    def create_incident_report(self, rationale: Any = None, **_ignored) -> Any:
        if self.report_id is not None:
            result: Any = {"error": f"incident report {self.report_id} already created"}
            self.effective.append((result, {}))
            return result
        if self.missing_needs():
            result = {"error": "call get_nearest_units first for: "
                               + ", ".join(self.missing_needs())}
            self.effective.append((result, {}))
            return result
        if isinstance(rationale, str) and rationale.strip():
            text = " ".join([rationale.strip()] + [n for n in self.notes()
                                                   if n not in rationale])
        else:
            text = self.template_rationale()
        args = {
            "case_id": self.case.id,
            "classification": self.cls["classification"],
            "confidence": self.cls["confidence"],
            "risk_level": self.risk,
            "needs": list(self.needs),
            "rationale": text,
            "nearest_relevant_units": self.nearest_units(),
            "protocol_cited": [self.cls["protocol_cited"]] if self.cls["protocol_cited"] else [],
            "missing_signals": list(self.cls["missing_signals"]),
        }
        result = call_tool("create_incident_report", self.db, **args)
        if isinstance(result, dict) and "report_id" in result:
            self.report_id = result["report_id"]
        self.effective.append((result, args))
        return result

    def args_for(self, result: Any) -> dict:
        for obj, args in self.effective:
            if obj is result:
                return args
        return {}

    def finish(self, entries: list[dict]) -> None:
        """Make any calls the model skipped so a complete report always exists. thought=None."""
        for need in self.missing_needs():
            r = self.get_nearest_units(need_type=need)
            entries.append(log_entry("coordinator", "get_nearest_units", self.args_for(r), r))
        if self.report_id is None:
            r = self.create_incident_report()
            entries.append(log_entry("coordinator", "create_incident_report",
                                     self.args_for(r), r))


def run_coordinator_mock(case, db, cls_out: dict) -> tuple[int | None, list[dict], int, bool]:
    """Deterministic path (no LLM): real local tools, same guarded logic as live."""
    run = _Run(case, db, cls_out)
    args = {"sector": case.sector}
    entries = [log_entry("coordinator", "get_sector_status", args,
                         call_tool("get_sector_status", db, **args))]
    run.finish(entries)
    return run.report_id, entries, 0, False


def _system_prompt() -> str:
    return (
        "You are the REACH coordinator agent supporting human disaster responders. You receive "
        "the classifier agent's output; do not reclassify. Needs and risk level have been "
        "computed for you from the classification and survey answers.\n"
        "Steps: call get_sector_status for the case's sector; call get_nearest_units once for "
        "EACH listed need using the given coordinates; then call create_incident_report with "
        "a short rationale (2-4 sentences) for a responder.\n"
        "Rules: never diagnose injuries; never declare an area safe; never dispatch, assign "
        "or close anything; never name a single unit as the assignment. The unit list is a "
        "ranked set of options for humans to choose from.\n"
        "Before EVERY tool call, set your message content to a JSON object "
        '{"reasoning_summary": "<one short sentence on why you are calling this tool>"}.\n'
        "When the report is saved, reply with only a JSON object "
        '{"reasoning_summary": "...", "done": true}.'
    )


def run_coordinator_agent(case, db, cls_out: dict,
                          max_iterations: int) -> tuple[int | None, list[dict], int, bool]:
    """Live agent loop. Returns (report_id, tool_log_entries, model_iterations, truncated)."""
    import nemotron

    run = _Run(case, db, cls_out)
    context = {
        "case_id": case.id, "sector": case.sector,
        "location": {"lat": case.lat, "lng": case.lng} if run.has_coords else None,
        "classifier_output": cls_out, "needs": run.needs, "need_reasons": run.need_reasons,
        "risk_level": run.risk,
    }
    if not run.has_coords:
        context["note"] = NO_COORDS_NOTE + " Do not call get_nearest_units."
    if not run.needs:
        context["note"] = NO_NEED_NOTE + " Do not call get_nearest_units."
    seed = [{"role": "system", "content": _system_prompt()},
            {"role": "user", "content": json.dumps(context, default=str)}]

    entries: list[dict] = []
    iterations, truncated = 0, False
    if max_iterations > 0:
        fns = {"get_sector_status": bound_tool("get_sector_status", db),
               "get_nearest_units": run.get_nearest_units,
               "create_incident_report": run.create_incident_report}
        chat = nemotron.chat_with_tools(seed, tool_schemas(COORDINATOR_TOOLS),
                                        max_iterations=max_iterations, tool_functions=fns)
        entries = entries_from_chat("coordinator", chat, len(seed), run.effective)
        iterations, truncated = chat["iterations"], chat["truncated"]
    else:
        truncated = True
    run.finish(entries)
    return run.report_id, entries, iterations, truncated
