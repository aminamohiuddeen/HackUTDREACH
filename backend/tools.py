"""Tool functions for the REACH agents (Nemotron function calling).

Every tool returns JSON-serializable data and raises ValueError on bad args.
Each accepts an optional `db` Session; when omitted it opens its own, so the
model never sees sessions and tests can inject one.

Nothing here assigns units: get_nearest_units returns a ranked list only, and
`assigned_unit_id` stays human-entered.
"""
from __future__ import annotations

import math
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, get_args

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models
from database import SessionLocal, utcnow
from schemas import CaseStatus, Classification

PROTOCOL_PATH = Path(__file__).parent / "protocol_kb" / "triage_protocols.md"
NEED_TYPES = {"EMS", "FIRE", "SAR"}
RISK_LEVELS = {"low", "medium", "high", "critical"}
CLASSIFICATIONS = set(get_args(Classification))
MAX_WINDOW_MINUTES = 1440
EXCERPT_CHARS = 600
REPORT_DETAIL_KEYS = ("classification", "confidence", "risk_level", "needs",
                      "nearest_relevant_units", "protocol_cited", "missing_signals")


@contextmanager
def _session(db: Session | None):
    if db is not None:
        yield db
        return
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _require_str(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _require_case_id(case_id: Any) -> int:
    if isinstance(case_id, bool) or not isinstance(case_id, int) or case_id < 1:
        raise ValueError("case_id must be a positive integer")
    return case_id


def _require_number(name: str, value: Any, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
        raise ValueError(f"{name} must be a number")
    if not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return float(value)


def _telemetry_dict(t: models.Telemetry) -> dict:
    return {
        "id": t.id, "robot_id": t.robot_id, "sector": t.sector,
        "location": {"lat": t.lat, "lng": t.lng, "source": t.location_source},
        "temperature_c": t.temperature_c, "water_detected": t.water_detected,
        "infrared_triggered": t.infrared_triggered, "anomaly_size_cm2": t.anomaly_size_cm2,
        "motion_detected": t.motion_detected, "location_zone": t.location_zone,
        "accelerometer": t.accelerometer, "gyroscope": t.gyroscope,
        "heart_rate_bpm": t.heart_rate_bpm, "spo2_percent": t.spo2_percent,
        "timestamp": _iso(t.timestamp), "source": t.source,
    }


def _survey_dict(s: models.Survey) -> dict:
    return {"id": s.id, "robot_id": s.robot_id, "sector": s.sector, "answers": s.answers,
            "timestamp": _iso(s.timestamp), "source": s.source}


# --- Tools -----------------------------------------------------------------

def get_case_evidence(case_id: int, db: Session | None = None) -> dict:
    """Case fields plus all telemetry and surveys."""
    case_id = _require_case_id(case_id)
    with _session(db) as s:
        case = s.get(models.Case, case_id)
        if case is None:
            raise ValueError(f"case {case_id} not found")
        surveys = [_survey_dict(x) for x in case.surveys]
        return {
            "case_id": case.id, "robot_id": case.robot_id, "sector": case.sector,
            "classification": case.classification, "confidence": case.confidence,
            "status": case.status, "signals": list(case.signals or []),
            "missing_signals": list(case.missing_signals or []),
            "urgent": case.urgent, "urgent_reasons": list(case.urgent_reasons or []),
            "location": ({"lat": case.lat, "lng": case.lng}
                         if case.lat is not None and case.lng is not None else None),
            "source": case.source,
            "created_at": _iso(case.created_at), "updated_at": _iso(case.updated_at),
            "telemetry": [_telemetry_dict(t) for t in case.telemetry],
            "surveys": surveys,
            "latest_survey_answers": surveys[-1]["answers"] if surveys else None,
        }


def get_sensor_history(robot_id: str, sector: str, window_minutes: int = 30,
                       db: Session | None = None) -> dict:
    """Telemetry for robot+sector within the last `window_minutes` (oldest first)."""
    robot_id = _require_str("robot_id", robot_id)
    sector = _require_str("sector", sector)
    if isinstance(window_minutes, bool) or not isinstance(window_minutes, int) \
            or not 1 <= window_minutes <= MAX_WINDOW_MINUTES:
        raise ValueError(f"window_minutes must be an integer between 1 and {MAX_WINDOW_MINUTES}")
    since = utcnow() - timedelta(minutes=window_minutes)
    with _session(db) as s:
        rows = s.scalars(
            select(models.Telemetry)
            .where(models.Telemetry.robot_id == robot_id,
                   models.Telemetry.sector == sector,
                   models.Telemetry.timestamp >= since)
            .order_by(models.Telemetry.timestamp)
        ).all()
        return {"robot_id": robot_id, "sector": sector, "window_minutes": window_minutes,
                "since": _iso(since), "count": len(rows),
                "readings": [_telemetry_dict(t) for t in rows]}


CASE_STATUSES = get_args(CaseStatus)  # verify, ranked, unverified, cleared, dispatched, resolved
OPEN_CASE_STATUSES = ("ranked", "verify", "unverified", "dispatched")  # cleared/resolved = closed


def sector_summary(s: Session, sector_id: str) -> dict | None:
    """Per-sector aggregation shared by get_sector_status() and GET /api/sectors.

    None if the sector does not exist. case_counts is zero-filled over every CaseStatus.
      urgent_cases   every urgent case, any status (get_sector_status's audit semantics)
      ranked_urgent  cases currently ranked AND urgent (what /api/sectors reports)
      last_telemetry_at  MAX(Telemetry.received_at) for readings taken in this sector
                         (Telemetry.sector, not the robot's current sector)
    """
    sec = s.get(models.Sector, sector_id)
    if sec is None:
        return None
    cases = s.scalars(select(models.Case).where(models.Case.sector == sector_id)).all()
    counts = {st: 0 for st in CASE_STATUSES}
    for c in cases:
        counts[c.status] = counts.get(c.status, 0) + 1
    robots = s.scalars(select(models.Robot).where(models.Robot.sector == sector_id)
                       .order_by(models.Robot.id)).all()
    last_tel = s.scalar(select(func.max(models.Telemetry.received_at))
                        .where(models.Telemetry.sector == sector_id))
    return {
        "sector": sec.id, "name": sec.name, "zone_type": sec.zone_type,
        "case_counts": counts, "total_cases": len(cases),
        "urgent_cases": sum(1 for c in cases if c.urgent),
        "ranked_urgent": sum(1 for c in cases if c.status == "ranked" and c.urgent),
        "robots": list(robots),
        "last_telemetry_at": last_tel,
    }


def sector_state(summary: dict) -> str:
    """Coverage state for one sector_summary(). Pure; first match wins.

    Order is urgent -> active -> unsearched -> cleared on purpose. A sector can have
    open cases with no telemetry at all (survey-only survivors: POST /api/surveys opens
    a case without any robot reading). An unsearched-and-urgent sector must surface as
    urgent, not unsearched, so case-based states are checked before telemetry coverage.
    "cleared" is the catch-all: telemetry exists and no case is open (cleared/resolved
    cases are closed but still counted in case_counts).
    """
    counts = summary["case_counts"]
    if summary["ranked_urgent"] > 0:
        return "urgent"
    if any(counts.get(st, 0) > 0 for st in OPEN_CASE_STATUSES):
        return "active"
    if summary["last_telemetry_at"] is None:
        return "unsearched"
    return "cleared"


def get_sector_status(sector: str, db: Session | None = None) -> dict:
    """Sector info, case counts by status, robots and units in the sector.

    Output shape is unchanged by the sector_summary() refactor: case_counts lists only
    statuses that occur, and urgent_cases counts every urgent case including resolved.
    """
    sector = _require_str("sector", sector)
    with _session(db) as s:
        summ = sector_summary(s, sector)
        if summ is None:
            raise ValueError(f"sector {sector!r} not found")
        units = s.scalars(select(models.Unit).where(models.Unit.sector_id == sector)
                          .order_by(models.Unit.id)).all()
        return {
            "sector": summ["sector"], "name": summ["name"], "zone_type": summ["zone_type"],
            "case_counts": {k: v for k, v in summ["case_counts"].items() if v},
            "total_cases": summ["total_cases"],
            "urgent_cases": summ["urgent_cases"],
            "robots": [{"robot_id": r.id, "source": r.source, "last_seen": _iso(r.last_seen)}
                       for r in summ["robots"]],
            "units": [{"unit_id": u.id, "name": u.name, "unit_type": u.unit_type,
                       "status": u.status} for u in units],
        }


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def get_nearest_units(lat: float, lng: float, need_type: str,
                      db: Session | None = None) -> list[dict]:
    """Available units ranked nearest first. A list for humans to choose from, never a pick."""
    lat = _require_number("lat", lat, -90, 90)
    lng = _require_number("lng", lng, -180, 180)
    if not isinstance(need_type, str):
        raise ValueError("need_type must be one of EMS, FIRE, SAR, any")
    nt = need_type.strip().upper()
    if nt != "ANY" and nt not in NEED_TYPES:
        raise ValueError("need_type must be one of EMS, FIRE, SAR, any")
    with _session(db) as s:
        q = select(models.Unit).where(models.Unit.status == "available",
                                      models.Unit.lat.is_not(None),
                                      models.Unit.lng.is_not(None))
        if nt != "ANY":
            q = q.where(models.Unit.unit_type == nt)
        ranked = [
            {"unit_id": u.id, "name": u.name, "unit_type": u.unit_type,
             "distance_km": round(haversine_km(lat, lng, u.lat, u.lng), 3)}
            for u in s.scalars(q).all()
        ]
    ranked.sort(key=lambda u: (u["distance_km"], u["unit_id"]))
    return ranked


# --- Protocol search ---------------------------------------------------------

_STOPWORDS = frozenset("""
a an and are as at be by can do does for from has have how i if in into is it its
of on or should that the their then there this to was what when where which who
why will with without
""".split())


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _terms(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS]


@lru_cache(maxsize=1)
def _protocol_sections() -> tuple[tuple[str, str], ...]:
    text = PROTOCOL_PATH.read_text(encoding="utf-8")
    sections = []
    for chunk in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        title, _, body = chunk.partition("\n")
        sections.append((title.strip(), body.strip()))
    return tuple(sections)


def _excerpt(body: str, terms: set[str]) -> str:
    if len(body) <= EXCERPT_CHARS:
        return body
    first = None
    for m in re.finditer(r"[a-z0-9]+", body.lower()):
        if _stem(m.group()) in terms:
            first = m.start()
            break
    start = max(0, (first or 0) - 150)
    end = min(len(body), start + EXCERPT_CHARS)
    start = max(0, end - EXCERPT_CHARS)
    out = body[start:end].strip()
    return ("…" if start > 0 else "") + out + ("…" if end < len(body) else "")


def search_protocol(query: str) -> list[dict]:
    """Keyword search over triage_protocols.md. Returns top 1-3 {section_title, excerpt}."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    q = set(_terms(query))
    if not q:
        raise ValueError("query has no searchable keywords")
    scored = []
    for idx, (title, body) in enumerate(_protocol_sections()):
        title_terms = set(_terms(title))
        body_terms = _terms(body)
        score = sum(3 for t in q if t in title_terms) + sum(1 for t in body_terms if t in q)
        if score > 0:
            scored.append((score, idx, title, body))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"section_title": title, "excerpt": _excerpt(body, q)}
            for _, _, title, body in scored[:3]]


# --- Reports -----------------------------------------------------------------

def create_incident_report(case_id: int, classification: str, confidence: float,
                           risk_level: str, needs: list[str], rationale: str,
                           nearest_relevant_units: list, protocol_cited: list[str] | None = None,
                           missing_signals: list[str] | None = None,
                           db: Session | None = None) -> dict:
    """Insert an IncidentReport. summary = rationale; details holds exactly REPORT_DETAIL_KEYS.

    missing_signals defaults to the case's own missing_signals.
    """
    case_id = _require_case_id(case_id)
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"classification must be one of {sorted(CLASSIFICATIONS)}")
    confidence = _require_number("confidence", confidence, 0.0, 1.0)
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"risk_level must be one of {sorted(RISK_LEVELS)}")
    if not isinstance(needs, list) or not all(isinstance(n, str) for n in needs) \
            or not set(needs) <= NEED_TYPES:
        raise ValueError("needs must be a list drawn from EMS, FIRE, SAR")
    rationale = _require_str("rationale", rationale)
    if not isinstance(nearest_relevant_units, list):
        raise ValueError("nearest_relevant_units must be a list")
    if protocol_cited is None:
        protocol_cited = []
    if not isinstance(protocol_cited, list) or not all(isinstance(p, str) for p in protocol_cited):
        raise ValueError("protocol_cited must be a list of strings")
    if missing_signals is not None and (
            not isinstance(missing_signals, list)
            or not all(isinstance(m, str) for m in missing_signals)):
        raise ValueError("missing_signals must be a list of strings")

    with _session(db) as s:
        case = s.get(models.Case, case_id)
        if case is None:
            raise ValueError(f"case {case_id} not found")
        details = {
            "classification": classification,
            "confidence": confidence,
            "risk_level": risk_level,
            "needs": list(needs),
            "nearest_relevant_units": nearest_relevant_units,
            "protocol_cited": list(protocol_cited),
            "missing_signals": (list(missing_signals) if missing_signals is not None
                                else list(case.missing_signals or [])),
        }
        report = models.IncidentReport(case_id=case_id, summary=rationale, details=details)
        s.add(report)
        s.commit()
        return {"report_id": report.id}


# --- Registry for Nemotron -------------------------------------------------------

TOOL_FUNCTIONS = {
    "get_case_evidence": get_case_evidence,
    "get_sensor_history": get_sensor_history,
    "get_sector_status": get_sector_status,
    "get_nearest_units": get_nearest_units,
    "search_protocol": search_protocol,
    "create_incident_report": create_incident_report,
}


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required,
                       "additionalProperties": False}}}


_STR_LIST = {"type": "array", "items": {"type": "string"}}

TOOL_SCHEMAS = [
    _fn("get_case_evidence", "Get a case with all its telemetry readings and survey responses.",
        {"case_id": {"type": "integer"}}, ["case_id"]),
    _fn("get_sensor_history",
        "Get recent telemetry for one robot in one sector, oldest first.",
        {"robot_id": {"type": "string"}, "sector": {"type": "string"},
         "window_minutes": {"type": "integer", "minimum": 1, "maximum": MAX_WINDOW_MINUTES,
                            "default": 30}},
        ["robot_id", "sector"]),
    _fn("get_sector_status",
        "Get a sector's case counts by status, robots, and units stationed there.",
        {"sector": {"type": "string"}}, ["sector"]),
    _fn("get_nearest_units",
        "List available response units nearest a location, ranked by distance. "
        "Returns options for a human to choose; never assigns a unit.",
        {"lat": {"type": "number"}, "lng": {"type": "number"},
         "need_type": {"type": "string", "enum": ["EMS", "FIRE", "SAR", "any"]}},
        ["lat", "lng", "need_type"]),
    _fn("search_protocol",
        "Keyword search of the REACH triage protocols. Returns up to 3 matching sections.",
        {"query": {"type": "string"}}, ["query"]),
    _fn("create_incident_report",
        "Save the incident report for a case. Flags for human review; does not dispatch.",
        {"case_id": {"type": "integer"},
         "classification": {"type": "string", "enum": sorted(CLASSIFICATIONS)},
         "confidence": {"type": "number", "minimum": 0, "maximum": 1},
         "risk_level": {"type": "string", "enum": sorted(RISK_LEVELS)},
         "needs": {"type": "array", "items": {"type": "string", "enum": sorted(NEED_TYPES)}},
         "rationale": {"type": "string"},
         "nearest_relevant_units": {"type": "array", "items": {"type": "object"}},
         "protocol_cited": _STR_LIST,
         "missing_signals": _STR_LIST},
        ["case_id", "classification", "confidence", "risk_level", "needs", "rationale",
         "nearest_relevant_units"]),
]
