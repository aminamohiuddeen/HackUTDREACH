"""ORM tables for REACH."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base, UTCDateTime, utcnow


class Robot(Base):
    __tablename__ = "robots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="simulator")
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_location_source: Mapped[str | None] = mapped_column(String, nullable=True)


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    zone_type: Mapped[str] = mapped_column(String, default="unknown")


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    unit_type: Mapped[str] = mapped_column(String)  # EMS | FIRE | SAR
    status: Mapped[str] = mapped_column(String, default="available")
    sector_id: Mapped[str | None] = mapped_column(String, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    robot_id: Mapped[str] = mapped_column(ForeignKey("robots.id"), index=True)
    sector: Mapped[str] = mapped_column(String, index=True)
    classification: Mapped[str] = mapped_column(String, default="unknown")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="verify", index=True)
    missing_signals: Mapped[list] = mapped_column(JSON, default=list)
    signals: Mapped[list] = mapped_column(JSON, default=list)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    urgent_reasons: Mapped[list] = mapped_column(JSON, default=list)
    # Human-entered only. Nemotron and the dashboard must never populate this.
    assigned_unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String, default="simulator")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    telemetry: Mapped[list["Telemetry"]] = relationship(
        back_populates="case", order_by="Telemetry.timestamp"
    )
    surveys: Mapped[list["Survey"]] = relationship(
        back_populates="case", order_by="Survey.timestamp"
    )


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), index=True, nullable=True)
    robot_id: Mapped[str] = mapped_column(String, index=True)
    sector: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    location_source: Mapped[str] = mapped_column(String)  # gps | operator
    temperature_c: Mapped[float] = mapped_column(Float)
    water_detected: Mapped[bool] = mapped_column(Boolean)
    infrared_triggered: Mapped[bool] = mapped_column(Boolean)
    anomaly_size_cm2: Mapped[float | None] = mapped_column(Float, nullable=True)
    motion_detected: Mapped[bool] = mapped_column(Boolean)
    location_zone: Mapped[str] = mapped_column(String)
    accelerometer: Mapped[dict] = mapped_column(JSON)
    gyroscope: Mapped[dict] = mapped_column(JSON)
    heart_rate_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String)  # simulator | hardware
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case | None] = relationship(back_populates="telemetry")


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), index=True, nullable=True)
    robot_id: Mapped[str] = mapped_column(String, index=True)
    sector: Mapped[str] = mapped_column(String)
    answers: Mapped[dict] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    case: Mapped[Case | None] = relationship(back_populates="surveys")


class IncidentReport(Base):
    __tablename__ = "incident_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ToolLog(Base):
    """One agent tool call made during /analyze. report_id ties the row to its run."""
    __tablename__ = "tool_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("incident_reports.id"),
                                                  index=True, nullable=True)
    agent: Mapped[str] = mapped_column(String)  # classifier | coordinator
    thought: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool: Mapped[str] = mapped_column(String)
    args_json: Mapped[dict] = mapped_column(JSON, default=dict)
    observation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
