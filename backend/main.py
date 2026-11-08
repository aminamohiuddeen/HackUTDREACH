"""REACH backend: FastAPI app.

Run:  uvicorn main:app --reload   (from backend/)
Docs: http://localhost:8000/docs

Data source labelling: every telemetry/survey record is tagged "simulator" or
"hardware". The default is "simulator"; real hardware MUST opt in by sending
the header `X-Reach-Source: hardware` or the query param `?source=hardware`.

Auth: every rescue-data endpoint requires a Supabase access token
(`Authorization: Bearer <jwt>`, verified in middleware/auth.py). Public:
GET /health, /docs, and the device ingest endpoints POST /api/telemetry and
POST /api/surveys (the ESP32 robot cannot log in).
"""
from __future__ import annotations

import json
import os
import random
import sys
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
import hardware_sync
import models
import tools
from agents.classifier import classify_case, survey_responded
from agents.orchestrator import run_analysis
from database import Base, SessionLocal, engine, get_db, utcnow
from middleware.auth import verify_supabase_token
from schemas import (
    CaseDetail,
    CaseOut,
    CasePatch,
    CaseStatus,
    LatestReport,
    RobotOut,
    SectorStateOut,
    SurveyAck,
    SurveyIn,
    SurveyOut,
    TelemetryAck,
    TelemetryIn,
    TelemetryOut,
    UnitOut,
)

SourceParam = Literal["simulator", "hardware"]

# Statuses set by responders that the classifier must not overwrite.
STICKY_STATUSES = {"dispatched", "resolved"}
STATUS_ORDER = {"ranked": 0, "verify": 1, "unverified": 2, "dispatched": 3, "cleared": 4,
                "resolved": 5}

SEED_SECTORS = [
    ("S1", "North Residential", "residential"),
    ("S2", "East Industrial", "industrial"),
    ("S3", "Central Corridor", "road"),
    ("S4", "South Residential", "residential"),
]
# (id, name, type, sector, lat, lng). Placed relative to simulator scenarios:
# EMS-1 nearest scenario 2 (ranked survivor, 32.9855,-96.7502), FIRE-1 nearest
# scenario 3 (residential verify, 32.9710,-96.7555), SAR-1 farther out.
SEED_UNITS = [
    ("EMS-1", "Medic 1", "EMS", "S1", 32.9840, -96.7515),
    ("EMS-2", "Medic 2", "EMS", "S4", 32.9765, -96.7420),
    ("FIRE-1", "Engine 1", "FIRE", "S2", 32.9700, -96.7540),
    ("SAR-1", "Search & Rescue 1", "SAR", "S1", 33.0060, -96.7330),
    ("SAR-2", "Search & Rescue 2", "SAR", "S3", 32.9950, -96.7620),
]


def init_db(db: Session) -> None:
    Base.metadata.create_all(bind=db.get_bind())
    if db.scalar(select(models.Sector).limit(1)) is None:
        db.add_all(models.Sector(id=i, name=n, zone_type=z) for i, n, z in SEED_SECTORS)
    if db.scalar(select(models.Unit).limit(1)) is None:
        db.add_all(models.Unit(id=i, name=n, unit_type=t, sector_id=s, lat=la, lng=ln)
                   for i, n, t, s, la, ln in SEED_UNITS)
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        init_db(db)
    yield


class UTF8JSONResponse(JSONResponse):
    """JSON with an explicit charset and ASCII-escaped non-ASCII characters.

    Data is stored as UTF-8 (SQLite TEXT). Without a charset some clients
    (e.g. Windows PowerShell 5.1 Invoke-RestMethod) decode the body as Latin-1,
    turning "cm²" into "cmÂ²". Declaring utf-8 and escaping (² -> \\u00b2) makes
    every client decode it the same way.
    """
    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")


app = FastAPI(title="REACH Backend", version="0.1.0", lifespan=lifespan,
              default_response_class=UTF8JSONResponse)

_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
            if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Helpers -----------------------------------------------------------------

def get_source(
    source: SourceParam | None = Query(None, description="simulator (default) or hardware"),
    x_reach_source: SourceParam | None = Header(None, description="simulator (default) or hardware"),
) -> str:
    return source or x_reach_source or "simulator"


def telemetry_out(t: models.Telemetry) -> TelemetryOut:
    return TelemetryOut.model_validate({
        **{c: getattr(t, c) for c in TelemetryOut.model_fields if c != "location"},
        "location": ({"lat": t.lat, "lng": t.lng, "source": t.location_source}
                     if t.lat is not None and t.lng is not None else None),
    })


def case_out(c: models.Case, rank: int | None = None, cls=CaseOut, **extra):
    fields = {k: getattr(c, k) for k in cls.model_fields
              if k not in ("location", "rank", "telemetry", "surveys", "latest_report")}
    loc = {"lat": c.lat, "lng": c.lng} if c.lat is not None and c.lng is not None else None
    return cls.model_validate({**fields, "location": loc, "rank": rank, **extra})


def ensure_sector(db: Session, sector_id: str) -> None:
    if db.get(models.Sector, sector_id) is None:
        db.add(models.Sector(id=sector_id, name=sector_id, zone_type="unknown"))


def touch_robot(db: Session, robot_id: str, sector: str, source: str, location=None) -> None:
    robot = db.get(models.Robot, robot_id)
    if robot is None:
        robot = models.Robot(id=robot_id)
        db.add(robot)
    robot.sector = sector
    robot.source = source
    robot.last_seen = utcnow()
    if location is not None:
        robot.last_lat, robot.last_lng = location.lat, location.lng
        robot.last_location_source = location.source


def open_case(db: Session, robot_id: str, sector: str, source: str) -> models.Case:
    """Most recent non-resolved case for this robot+sector, or a new one."""
    case = db.scalar(
        select(models.Case)
        .where(models.Case.robot_id == robot_id, models.Case.sector == sector,
               models.Case.status != "resolved")
        .order_by(models.Case.id.desc())
        .limit(1)
    )
    if case is None:
        case = models.Case(robot_id=robot_id, sector=sector, source=source)
        db.add(case)
        db.flush()
    return case


def reclassify(db: Session, case: models.Case) -> None:
    db.flush()
    db.refresh(case)
    surveys = list(case.surveys)
    responded = [s for s in surveys if survey_responded(s)]
    survey = responded[-1] if responded else (surveys[-1] if surveys else None)
    result = classify_case(case.telemetry, survey)

    case.classification = result["classification"]
    case.confidence = result["confidence"]
    case.missing_signals = result["missing_signals"]
    case.signals = result["signals"]
    case.urgent = result["urgent"]
    case.urgent_reasons = result["urgent_reasons"]
    if case.status not in STICKY_STATUSES:
        case.status = result["status"]
    case.updated_at = utcnow()


def _rank_key(c: models.Case):
    return (not c.urgent, -len(c.urgent_reasons or []), -c.confidence, c.created_at, c.id)


def compute_ranks(db: Session) -> dict[int, int]:
    ranked = db.scalars(select(models.Case).where(models.Case.status == "ranked")).all()
    return {c.id: i for i, c in enumerate(sorted(ranked, key=_rank_key), start=1)}


def latest_report_out(db: Session, case_id: int) -> LatestReport | None:
    row = db.scalars(select(models.IncidentReport)
                     .where(models.IncidentReport.case_id == case_id)
                     .order_by(models.IncidentReport.id.desc()).limit(1)).first()
    if row is None:
        return None
    d = row.details or {}
    return LatestReport(report_id=row.id, rationale=row.summary or "",
                        rationale_conflict=list(d.get("rationale_conflict") or []),
                        classification=d.get("classification"), status=d.get("status"),
                        created_at=row.created_at)


def get_case_or_404(db: Session, case_id: int) -> models.Case:
    case = db.get(models.Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


RequireUser = [Depends(verify_supabase_token)]

# Local testing only: REACH_AUTH_DISABLED=1 (backend/.env) skips Supabase verification on the
# dashboard routes and treats every request as a demo user. Never set it in a deployment.
if os.getenv("REACH_AUTH_DISABLED", "").strip().lower() in ("1", "true", "yes"):
    app.dependency_overrides[verify_supabase_token] = lambda: {
        "user_id": "demo", "email": None, "claims": {}}
    print("WARNING: REACH_AUTH_DISABLED is set - API auth is OFF (local testing only)",
          file=sys.stderr)


# --- Endpoints ---------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


CONFIG_NOTE = (
    "Thresholds are set by the responding agency's SOP. Defaults shown; production "
    "deployments override via config. zone_weighting and unit_type_mapping are shown for "
    "transparency; the current classifier and coordinator use hardcoded values that match "
    "these defaults."
)


@app.get("/api/config", dependencies=RequireUser)
def get_config():
    """Read-only view of the responder thresholds the classifier uses."""
    return {
        "anomaly_size_cm2": {**config.ANOMALY_SIZE_CM2, "source": "default"},
        "zone_weighting": {**config.ZONE_WEIGHTING, "source": "default"},
        "signals_required_for_likely_person": config.SIGNALS_REQUIRED_FOR_LIKELY_PERSON,
        "unit_type_mapping": {k: list(v) for k, v in config.UNIT_TYPE_MAPPING.items()},
        "verify_window_seconds": config.VERIFY_WINDOW_SECONDS,
        "note": CONFIG_NOTE,
    }


@app.post("/api/telemetry", response_model=TelemetryAck, status_code=201)
def post_telemetry(payload: TelemetryIn, source: str = Depends(get_source),
                   db: Session = Depends(get_db)):
    ensure_sector(db, payload.sector)
    touch_robot(db, payload.robot_id, payload.sector, source, payload.location)
    case = open_case(db, payload.robot_id, payload.sector, source)
    loc = payload.location  # None for pods without GPS

    t = models.Telemetry(
        case_id=case.id,
        robot_id=payload.robot_id,
        sector=payload.sector,
        lat=loc.lat if loc else None,
        lng=loc.lng if loc else None,
        location_source=loc.source if loc else None,
        temperature_c=payload.temperature_c,
        water_detected=payload.water_detected,
        infrared_triggered=payload.infrared_triggered,
        anomaly_size_cm2=payload.anomaly_size_cm2,
        motion_detected=payload.motion_detected,
        location_zone=payload.location_zone,
        accelerometer=payload.accelerometer.model_dump() if payload.accelerometer else None,
        gyroscope=payload.gyroscope.model_dump() if payload.gyroscope else None,
        heart_rate_bpm=payload.heart_rate_bpm,
        spo2_percent=payload.spo2_percent,
        timestamp=payload.timestamp or utcnow(),
        source=source,
    )
    db.add(t)
    case.source = source
    if loc is not None:
        # A reading without GPS keeps the case's last known location (None for a new case).
        case.lat, case.lng = loc.lat, loc.lng
    reclassify(db, case)
    db.commit()

    ranks = compute_ranks(db)
    return TelemetryAck(id=t.id, case_id=case.id, source=source, timestamp=t.timestamp,
                        case=case_out(case, ranks.get(case.id)))


@app.post("/api/surveys", response_model=SurveyAck, status_code=201)
def post_survey(payload: SurveyIn, source: str = Depends(get_source),
                db: Session = Depends(get_db)):
    ensure_sector(db, payload.sector)
    touch_robot(db, payload.robot_id, payload.sector, source)
    case = open_case(db, payload.robot_id, payload.sector, source)

    s = models.Survey(
        case_id=case.id,
        robot_id=payload.robot_id,
        sector=payload.sector,
        answers=payload.answers.model_dump(),
        timestamp=payload.timestamp or utcnow(),
        source=source,
    )
    db.add(s)
    case.source = source
    reclassify(db, case)
    db.commit()

    ranks = compute_ranks(db)
    return SurveyAck(id=s.id, case_id=case.id, source=source, timestamp=s.timestamp,
                     case=case_out(case, ranks.get(case.id)))


@app.get("/api/robots", response_model=list[RobotOut], dependencies=RequireUser)
def list_robots(db: Session = Depends(get_db)):
    return db.scalars(select(models.Robot).order_by(models.Robot.id)).all()


@app.get("/api/cases", response_model=list[CaseOut], dependencies=RequireUser)
def list_cases(status: CaseStatus | None = None, sector: str | None = None,
               db: Session = Depends(get_db)):
    ranks = compute_ranks(db)
    q = select(models.Case)
    if status:
        q = q.where(models.Case.status == status)
    if sector:
        q = q.where(models.Case.sector == sector)
    cases = db.scalars(q).all()
    cases = sorted(cases, key=lambda c: (STATUS_ORDER.get(c.status, 99),
                                         ranks.get(c.id, 0), *_rank_key(c)))
    return [case_out(c, ranks.get(c.id)) for c in cases]


@app.get("/api/cases/{case_id}", response_model=CaseDetail, dependencies=RequireUser)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id)
    ranks = compute_ranks(db)
    return case_out(
        case, ranks.get(case.id), cls=CaseDetail,
        telemetry=[telemetry_out(t) for t in case.telemetry],
        surveys=[SurveyOut.model_validate(s) for s in case.surveys],
        latest_report=latest_report_out(db, case.id),
    )


@app.patch("/api/cases/{case_id}", response_model=CaseOut, dependencies=RequireUser)
def patch_case(case_id: int, patch: CasePatch, db: Session = Depends(get_db)):
    case = get_case_or_404(db, case_id)
    changes = patch.model_dump(exclude_unset=True)
    if changes.get("assigned_unit_id") is not None and \
            db.get(models.Unit, changes["assigned_unit_id"]) is None:
        raise HTTPException(status_code=404, detail="Unit not found")
    if "status" in changes and changes["status"] is None:
        raise HTTPException(status_code=422, detail="status cannot be null")
    for k, v in changes.items():
        setattr(case, k, v)
    case.updated_at = utcnow()
    db.commit()
    return case_out(case, compute_ranks(db).get(case.id))


@app.post("/api/cases/{case_id}/analyze", dependencies=RequireUser)
def analyze_case(case_id: int, db: Session = Depends(get_db)):
    """Run classifier + coordinator agents. Returns {report, tool_log, agent_counts, mode,
    truncated}; same shape in live and mock mode. Never assigns a unit."""
    get_case_or_404(db, case_id)
    return run_analysis(case_id, db)


@app.get("/api/sectors", response_model=list[SectorStateOut], dependencies=RequireUser)
def list_sectors(db: Session = Depends(get_db)):
    """Sectors with coverage state ("which sectors have not been searched?").
    Derived at request time from cases, robots and telemetry; nothing is stored."""
    out = []
    for sec_id in db.scalars(select(models.Sector.id).order_by(models.Sector.id)):
        summ = tools.sector_summary(db, sec_id)
        out.append(SectorStateOut(
            id=summ["sector"], name=summ["name"], zone_type=summ["zone_type"],
            state=tools.sector_state(summ), case_count_by_status=summ["case_counts"],
            urgent_cases=summ["ranked_urgent"], robot_count=len(summ["robots"]),
            last_telemetry_at=summ["last_telemetry_at"]))
    return out


@app.get("/api/units", response_model=list[UnitOut], dependencies=RequireUser)
def list_units(db: Session = Depends(get_db)):
    return db.scalars(select(models.Unit).order_by(models.Unit.id)).all()


# --- Hardware bridge ---------------------------------------------------------

# Entries already ingested ("t:<unit>:<received_at>" / "s:<case_id>:<received_at>").
# In-memory: after a restart the pod server's latest entries are ingested once more.
_hardware_seen: set[str] = set()


@app.get("/api/sync-hardware", dependencies=RequireUser)
def sync_hardware(db: Session = Depends(get_db)):
    """Pull the rescue pod's latest data from the hardware test server (/state) and ingest it as
    source=hardware telemetry and surveys. Readings the pod cannot provide are simulated and
    listed in `simulated_fields`. Safe to call repeatedly: already-ingested entries are skipped."""
    try:
        state = hardware_sync.fetch_state()
    except (httpx.HTTPError, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Hardware server unreachable: {e}")

    rng = random.Random()
    out = {"telemetry_ingested": 0, "surveys_ingested": 0, "skipped_duplicates": 0,
           "case_ids": [], "simulated_fields": {}, "errors": []}

    telemetry = state.get("latest_telemetry")
    for unit_id, data in (telemetry.items() if isinstance(telemetry, dict) else []):
        if not isinstance(data, dict):
            continue
        key = f"t:{unit_id}:{data.get('received_at')}"
        if key in _hardware_seen:
            out["skipped_duplicates"] += 1
            continue
        try:
            payload, simulated = hardware_sync.pod_telemetry(str(unit_id), data, rng)
        except ValidationError as e:
            out["errors"].append(f"telemetry {unit_id}: {e.errors()[0]['msg']}")
            continue
        ack = post_telemetry(payload, source="hardware", db=db)
        _hardware_seen.add(key)
        out["telemetry_ingested"] += 1
        out["simulated_fields"][payload.robot_id] = simulated
        if ack.case_id not in out["case_ids"]:
            out["case_ids"].append(ack.case_id)

    cases = state.get("cases")
    for case in (cases if isinstance(cases, list) else []):
        if not isinstance(case, dict):
            continue
        key = f"s:{case.get('case_id')}:{case.get('received_at')}"
        if key in _hardware_seen:
            out["skipped_duplicates"] += 1
            continue
        try:
            payload = hardware_sync.pod_survey(case)
        except ValidationError as e:
            out["errors"].append(f"survey {case.get('case_id')}: {e.errors()[0]['msg']}")
            continue
        ack = post_survey(payload, source="hardware", db=db)
        _hardware_seen.add(key)
        out["surveys_ingested"] += 1
        if ack.case_id not in out["case_ids"]:
            out["case_ids"].append(ack.case_id)

    return out
