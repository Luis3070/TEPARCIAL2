from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (UniqueConstraint("equipment", "date", name="uq_inspection_equipment_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment: Mapped[str] = mapped_column(ForeignKey("equipment.id"), index=True)
    zone: Mapped[str] = mapped_column(String(120))
    date: Mapped[date] = mapped_column(Date, index=True)
    hours: Mapped[float] = mapped_column(Float)
    inspector: Mapped[str] = mapped_column(String(80))
    imported: Mapped[bool] = mapped_column(Boolean, default=False)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    maintenance_event: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="inspection", cascade="all, delete-orphan")


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (UniqueConstraint("inspection_id", "point", name="uq_measurement_inspection_point"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspection_id: Mapped[int] = mapped_column(ForeignKey("inspections.id", ondelete="CASCADE"), index=True)
    point: Mapped[str] = mapped_column(ForeignKey("inspection_points.code"), index=True)
    description: Mapped[str] = mapped_column(String(180))
    length_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    caution_mm: Mapped[float] = mapped_column(Float)
    danger_mm: Mapped[float] = mapped_column(Float)
    structural_state: Mapped[str] = mapped_column(String(16))
    severity_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_l_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_l_effective: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_l_bridged_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bridged_from_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    bridged_elapsed_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bridge_null_count: Mapped[int] = mapped_column(Integer, default=0)
    gap_spanning_change: Mapped[bool] = mapped_column(Boolean, default=False)
    change_class: Mapped[str] = mapped_column(String(40), default="N_I")
    raw_growth_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    effective_growth_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maintenance_segment: Mapped[int] = mapped_column(Integer, default=0)
    maintenance_action: Mapped[str] = mapped_column(String(40), default="REINSPECTION_REQUIRED")
    maintenance_priority: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    maintenance_mode: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    data_warning: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    inspection: Mapped[Inspection] = relationship(back_populates="measurements")


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    point: Mapped[str] = mapped_column(ForeignKey("inspection_points.code"), index=True)
    comment: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[str] = mapped_column(String(24))
    source_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="historical")


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment: Mapped[str] = mapped_column(ForeignKey("equipment.id"), default="EH4-01")
    point: Mapped[str] = mapped_column(ForeignKey("inspection_points.code"), index=True)
    intervention_type: Mapped[str] = mapped_column(String(80))
    priority: Mapped[str] = mapped_column(String(8))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    scheduled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    responsible: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_measurement_id: Mapped[Optional[int]] = mapped_column(ForeignKey("measurements.id"), nullable=True)
    status_history: Mapped[list["WorkOrderStatusHistory"]] = relationship(back_populates="work_order", cascade="all, delete-orphan")


class WorkOrderStatusHistory(Base):
    __tablename__ = "work_order_status_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_order: Mapped[WorkOrder] = relationship(back_populates="status_history")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(600))
    media_type: Mapped[str] = mapped_column(String(120))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    inspection_id: Mapped[Optional[int]] = mapped_column(ForeignKey("inspections.id"), nullable=True)
    work_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("work_orders.id"), nullable=True)
    point: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class HotspotCalibration(Base):
    __tablename__ = "hotspot_calibrations"
    point: Mapped[str] = mapped_column(String(16), primary_key=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    z: Mapped[float] = mapped_column(Float)
    nx: Mapped[float] = mapped_column(Float, default=0)
    ny: Mapped[float] = mapped_column(Float, default=1)
    nz: Mapped[float] = mapped_column(Float, default=0)
    calibrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    calibrated_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_asset: Mapped[str] = mapped_column(String(255), default="EH4000_front_suspension_V7_final.stl")
    model_local_coordinates: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Equipment(Base):
    __tablename__ = "equipment"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    manufacturer: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StructuralZone(Base):
    __tablename__ = "structural_zones"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    subsystem: Mapped[str] = mapped_column(String(100))


class InspectionPoint(Base):
    __tablename__ = "inspection_points"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("structural_zones.id"), index=True)
    description: Mapped[str] = mapped_column(String(180))
    caution_mm: Mapped[float] = mapped_column(Float)
    danger_mm: Mapped[float] = mapped_column(Float)


class Model3DAsset(Base):
    __tablename__ = "model_3d_assets"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[str] = mapped_column(String(20))
    stored_path: Mapped[str] = mapped_column(String(600))
    units: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    mesh_count: Mapped[int] = mapped_column(Integer, default=1)
    vertex_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    face_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_watertight: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_winding_consistent: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dimensions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    source_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    coordinate_transform: Mapped[str] = mapped_column(String(200), default="none")
