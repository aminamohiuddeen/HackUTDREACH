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
    robot_id: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    location: Location
    temperature_c: float
    water_detected: bool
    infrared_triggered: bool
    anomaly_size_cm2: float | None = Field(default=None, ge=0)
    motion_detected: bool
    location_zone: LocationZone
    accelerometer: Vec3
    gyroscope: Vec3
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


class SurveyIn(BaseModel):
    robot_id: str = Field(min_length=1)
    sector: str = Field(min_length=1)
    answers: SurveyAnswers
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
    location: Location
    temperature_c: float
    water_detected: bool
    infrared_triggered: bool
    anomaly_size_cm2: float | None
    motion_detected: bool
    location_zone: LocationZone
    accelerometer: Vec3
    gyroscope: Vec3
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


class CaseDetail(CaseOut):
    telemetry: list[TelemetryOut]
    surveys: list[SurveyOut]


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


class UnitOut(ORMModel):
    id: str
    name: str
    unit_type: Literal["EMS", "FIRE", "SAR"]
    status: str
    sector_id: str | None
