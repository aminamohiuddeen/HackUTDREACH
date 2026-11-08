"""Pydantic v2 request/response schemas.

Telemetry/Survey field names are a contract with the ESP32 firmware and the
dashboard. Coordinate before renaming anything.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Source = Literal["simulator", "hardware"]
YesNoUnknown = Literal["yes", "no", "unknown"]
LocationZone = Literal["residential", "industrial", "road", "unknown"]
CaseStatus = Literal["verify", "ranked", "unverified", "cleared", "dispatched", "resolved"]
Classification = Literal["likely_person", "possible_person", "object", "unknown"]


# --- Inbound ---------------------------------------------------------------

class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    source: Literal["gps", "operator"]


class Vec3(BaseModel):
    x: float
    y: float
    z: float


class TelemetryIn(BaseModel):
    # Hardware pods may lack GPS or an IMU, and a DHT read can fail:
    # those fields are optional and stored as null (never fabricated).
    robot_id: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    location: Location | None = None
    temperature_c: float | None = None
    infrared_triggered: bool
    anomaly_size_cm2: float | None = Field(default=None, ge=0)
    motion_detected: bool
    location_zone: LocationZone = "unknown"
    accelerometer: Vec3 | None = None
    gyroscope: Vec3 | None = None
    heart_rate_bpm: float | None = None
    spo2_percent: float | None = None
    timestamp: datetime | None = None  # server-set if absent


class SurveyAnswers(BaseModel):
    # Unanswered questions stay "unknown"; they are never assumed "no".
    injured: YesNoUnknown = "unknown"
    trapped: YesNoUnknown = "unknown"
    breathing_difficulty: YesNoUnknown = "unknown"
    others_present: YesNoUnknown = "unknown"
    immediate_help: YesNoUnknown = "unknown"


class SurveyDetails(BaseModel):
    """What the survivor actually entered, where the yes/no answers lose detail (rescue pod).
    Shown to responders and the coordinator; classification uses `answers` only."""
    people_count: int | None = Field(None, ge=0)  # "How many people are with you?"
    can_move: bool | None = None  # "Can you move on your own?" (trapped = not can_move)
    needs_water_or_medication: bool | None = None  # pod's question behind immediate_help


class SurveyIn(BaseModel):
    robot_id: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    answers: SurveyAnswers
    details: SurveyDetails | None = None
    timestamp: datetime | None = None


class CasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CaseStatus | None = None
    assigned_unit_id: str | None = None  # human-entered only
    notes: str | None = None


# --- Outbound --------------------------------------------------------------

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TelemetryOut(ORMModel):
    id: int
    case_id: int | None
    robot_id: str
    sector: str
    location: Location | None
    temperature_c: float | None
    infrared_triggered: bool
    anomaly_size_cm2: float | None
    motion_detected: bool
    location_zone: LocationZone
    accelerometer: Vec3 | None
    gyroscope: Vec3 | None
    heart_rate_bpm: float | None
    spo2_percent: float | None
    timestamp: datetime
    source: Source
    received_at: datetime


class SurveyOut(ORMModel):
    id: int
    case_id: int | None
    robot_id: str
    sector: str
    answers: SurveyAnswers
    details: SurveyDetails | None = None
    timestamp: datetime
    source: Source


class CaseLocation(BaseModel):
    lat: float
    lng: float


class CaseOut(ORMModel):
    id: int
    robot_id: str
    sector: str
    classification: Classification
    confidence: float
    status: CaseStatus
    missing_signals: list[str]
    signals: list[str]
    urgent: bool
    urgent_reasons: list[str]
    assigned_unit_id: str | None
    notes: str | None
    location: CaseLocation | None
    source: Source
    rank: int | None = None
    created_at: datetime
    updated_at: datetime


class LatestReport(BaseModel):
    """Newest IncidentReport for a case, enough to render "latest analysis said X"."""
    report_id: int
    rationale: str
    rationale_conflict: list[str]
    classification: str | None
    status: str | None  # status the analysis used; None for reports stored before it was kept
    created_at: datetime


class CaseDetail(CaseOut):
    telemetry: list[TelemetryOut]
    surveys: list[SurveyOut]
    latest_report: LatestReport | None = None


class TelemetryAck(BaseModel):
    id: int
    case_id: int
    source: Source
    timestamp: datetime
    case: CaseOut


class SurveyAck(BaseModel):
    id: int
    case_id: int
    source: Source
    timestamp: datetime
    case: CaseOut


class RobotOut(ORMModel):
    id: str
    sector: str | None
    source: Source
    last_seen: datetime | None
    last_lat: float | None
    last_lng: float | None
    last_location_source: str | None


class SectorOut(ORMModel):
    id: str
    name: str
    zone_type: str


SectorState = Literal["unsearched", "urgent", "active", "cleared"]


class SectorStateOut(BaseModel):
    """GET /api/sectors: a sector plus its coverage state, derived at request time.

    state: see tools.sector_state() (urgent -> active -> unsearched -> cleared).
    case_count_by_status: every CaseStatus key, zero-filled.
    urgent_cases: cases that are currently ranked AND urgent only (a resolved or
        dispatched urgent case is not counted). This differs on purpose from
        tools.get_sector_status()'s urgent_cases, which keeps its existing
        all-urgent-including-resolved semantics for audit.
    robot_count: robots whose current sector is this one.
    last_telemetry_at: newest Telemetry.received_at for readings taken in this sector;
        null if none (never searched).
    """
    id: str
    name: str
    zone_type: str
    state: SectorState
    case_count_by_status: dict[str, int]
    urgent_cases: int
    robot_count: int
    last_telemetry_at: datetime | None


class UnitOut(ORMModel):
    id: str
    name: str
    unit_type: Literal["EMS", "FIRE", "SAR"]
    status: str
    sector_id: str | None
    lat: float | None = None
    lng: float | None = None
