"""Runs the two-agent analysis for one case: classifier, then coordinator.

run_analysis(case_id, db) returns
    {report, tool_log, agent_counts, mode, truncated}
with exactly the same keys, nesting and types in live and mock mode, so the
dashboard never branches on `mode`.

  * mode "mock" (no NVIDIA_API_KEY): both LLM loops are skipped. The calls the
    agents would make are executed against the real local tools, and the
    report comes from classify_case() + get_nearest_units(). thought is None.
  * Iteration cap: TOTAL_ITERATION_CAP (12) model rounds across BOTH agents.
    The classifier gets at most CLASSIFIER_ITERATION_BUDGET (8) and the
    coordinator gets the rest. Hitting a limit sets truncated=True. The
    deterministic follow-up calls each agent makes for steps the model skipped
    (evidence first, a required protocol search, missing unit lists, the report
    itself) are not model rounds, so a report is always produced.
  * protocol_cited: IncidentReport.details.protocol_cited is a list (the
    tools.py contract). The /analyze response surfaces a single string: the
    first entry if there are several, or "" if there are none. It is never null.
  * Case.assigned_unit_id is never written. A before_flush guard on this run's
    session aborts the run if this case's assigned_unit_id changes in it. It is
    scoped to this session and this case_id only, so a concurrent PATCH (which
    uses its own session) is unaffected.
"""
from __future__ import annotations

from sqlalchemy import event, inspect, select, update
from sqlalchemy.orm import Session

import models
import nemotron
from agents import classifier, coordinator
from agents.common import CLASSIFIER_ITERATION_BUDGET, TOTAL_ITERATION_CAP

AGENTS = ("classifier", "coordinator")
REPORT_KEYS = ("report_id", "case_id", "classification", "confidence", "status", "urgent",
               "urgent_reasons", "missing_signals", "risk_level", "needs",
               "nearest_relevant_units", "protocol_cited", "rationale")


class CaseNotFound(LookupError):
    pass


class AssignmentWriteError(RuntimeError):
    """Raised if anything in an analysis run tries to write Case.assigned_unit_id."""


def _install_assignment_guard(db: Session, case_id: int):
    def guard(session, flush_context, instances):
        for obj in list(session.dirty) + list(session.new):
            if isinstance(obj, models.Case) and obj.id == case_id \
                    and inspect(obj).attrs.assigned_unit_id.history.has_changes():
                raise AssignmentWriteError(
                    f"analysis attempted to write assigned_unit_id on case {case_id}")

    event.listen(db, "before_flush", guard)
    return lambda: event.remove(db, "before_flush", guard)


def _persist_log(db: Session, case_id: int, entries: list[dict]) -> list[int]:
    rows = [models.ToolLog(case_id=case_id, agent=e["agent"], thought=e["thought"],
                           tool=e["tool"], args_json=e["args"],
                           observation_json=e["observation"]) for e in entries]
    db.add_all(rows)
    db.commit()
    return [r.id for r in rows]


def build_report(row: models.IncidentReport, cls_out: dict) -> dict:
    """The /analyze report, built from what was persisted. Fixed keys and types."""
    d = row.details or {}
    cited = d.get("protocol_cited") or []
    report = {
        "report_id": row.id,
        "case_id": row.case_id,
        "classification": d.get("classification", cls_out["classification"]),
        "confidence": float(d.get("confidence", cls_out["confidence"])),
        "status": cls_out["status"],
        "urgent": bool(cls_out.get("urgent")),
        "urgent_reasons": list(cls_out.get("urgent_reasons") or []),
        "missing_signals": list(d.get("missing_signals") or []),
        "risk_level": d.get("risk_level"),
        "needs": list(d.get("needs") or []),
        "nearest_relevant_units": list(d.get("nearest_relevant_units") or []),
        "protocol_cited": cited[0] if isinstance(cited, list) and cited else "",
        "rationale": row.summary or "",
    }
    assert tuple(report) == REPORT_KEYS
    return report


def run_analysis(case_id: int, db: Session) -> dict:
    case = db.get(models.Case, case_id)
    if case is None:
        raise CaseNotFound(f"case {case_id} not found")

    remove_guard = _install_assignment_guard(db, case_id)
    try:
        mock = nemotron.mock_mode()
        if mock:
            cls_out, cls_log, cls_iter, cls_trunc = classifier.run_classifier_mock(case, db)
        else:
            cls_out, cls_log, cls_iter, cls_trunc = classifier.run_classifier_agent(
                case, db, max_iterations=min(CLASSIFIER_ITERATION_BUDGET, TOTAL_ITERATION_CAP))
        log_ids = _persist_log(db, case_id, cls_log)

        remaining = max(0, TOTAL_ITERATION_CAP - cls_iter)
        if mock:
            report_id, co_log, _, co_trunc = coordinator.run_coordinator_mock(case, db, cls_out)
        else:
            report_id, co_log, _, co_trunc = coordinator.run_coordinator_agent(
                case, db, cls_out, max_iterations=remaining)
        log_ids += _persist_log(db, case_id, co_log)

        row = db.get(models.IncidentReport, report_id) if report_id is not None else None
        if row is None:
            raise RuntimeError(f"no incident report was produced for case {case_id}")
        # Tie every ToolLog row written during this run to its report.
        db.execute(update(models.ToolLog).where(models.ToolLog.id.in_(log_ids))
                   .values(report_id=row.id))
        db.commit()
    finally:
        remove_guard()

    tool_log = cls_log + co_log
    return {
        "report": build_report(row, cls_out),
        "tool_log": tool_log,
        "agent_counts": {a: sum(1 for e in tool_log if e["agent"] == a) for a in AGENTS},
        "mode": "mock" if mock else "live",
        "truncated": bool(cls_trunc or co_trunc),
    }


def tool_log_for_report(db: Session, report_id: int) -> list[models.ToolLog]:
    return list(db.scalars(select(models.ToolLog).where(models.ToolLog.report_id == report_id)
                           .order_by(models.ToolLog.id)))
