from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

POINTS = ("SD-01", "SD-02", "SD-03", "SD-04")
WO_STATUSES = ("PENDING", "APPROVED", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELED")


class MeasurementInput(BaseModel):
    point: Literal["SD-01", "SD-02", "SD-03", "SD-04"]
    length_mm: Optional[float] = Field(default=None, ge=0, le=10000, description="NULL significa no inspeccionado; 0 significa inspeccionado sin grieta detectable.")
    comment: Optional[str] = Field(default=None, max_length=4000)
    maintenance_event: bool = False


class InspectionCreate(BaseModel):
    equipment: Literal["EH4-01"] = "EH4-01"
    date: date
    hours: float = Field(ge=0)
    inspector: str = Field(min_length=1, max_length=80)
    measurements: list[MeasurementInput] = Field(min_length=4, max_length=4)

    @field_validator("inspector")
    @classmethod
    def clean_inspector(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_four_distinct_points(self):
        seen = [m.point for m in self.measurements]
        if len(set(seen)) != 4 or set(seen) != set(POINTS):
            raise ValueError("La inspección debe incluir exactamente una medición o N/I para SD-01...SD-04.")
        return self


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    point: str
    description: str
    length_mm: Optional[float]
    caution_mm: float
    danger_mm: float
    structural_state: str
    severity_ratio: Optional[float]
    delta_l_raw: Optional[float]
    delta_l_effective: Optional[float]
    delta_l_bridged_raw: Optional[float]
    bridged_from_date: Optional[date]
    bridged_elapsed_hours: Optional[float]
    bridge_null_count: int
    gap_spanning_change: bool
    change_class: str
    raw_growth_rate: Optional[float]
    effective_growth_rate: Optional[float]
    maintenance_segment: int
    maintenance_action: str
    maintenance_priority: Optional[str]
    maintenance_mode: Optional[str]
    decision_reason: str
    data_warning: Optional[str]
    comment: Optional[str]
    image_file: Optional[str]
    source_row: Optional[int]


class InspectionOut(BaseModel):
    id: int
    equipment: str
    zone: str
    date: date
    hours: float
    inspector: str
    imported: bool
    maintenance_event: bool
    measurements: list[MeasurementOut]


class WorkOrderCreate(BaseModel):
    equipment: Literal["EH4-01"] = "EH4-01"
    point: Literal["SD-01", "SD-02", "SD-03", "SD-04"]
    intervention_type: str = Field(min_length=2, max_length=80)
    priority: Literal["P0", "P1", "P2", "P3", "P4"]
    description: str = Field(min_length=3, max_length=4000)
    scheduled_date: Optional[date] = None
    responsible: Optional[str] = Field(default=None, max_length=120)
    observations: Optional[str] = Field(default=None, max_length=4000)
    source_measurement_id: Optional[int] = None


class WorkOrderPatch(BaseModel):
    status: Optional[Literal["PENDING", "APPROVED", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELED"]] = None
    scheduled_date: Optional[date] = None
    responsible: Optional[str] = Field(default=None, max_length=120)
    observations: Optional[str] = Field(default=None, max_length=4000)
    status_note: Optional[str] = Field(default=None, max_length=1000)


class WorkOrderOut(BaseModel):
    id: int
    equipment: str
    point: str
    intervention_type: str
    priority: str
    description: str
    status: str
    created_at: datetime
    scheduled_date: Optional[date]
    responsible: Optional[str]
    observations: Optional[str]
    closed_at: Optional[datetime]
    source_measurement_id: Optional[int]


class HotspotInput(BaseModel):
    x: float
    y: float
    z: float
    nx: float = 0
    ny: float = 1
    nz: float = 0
    calibrated_by: Optional[str] = Field(default=None, max_length=120)
    confirmed: bool = False
    model_asset: str = "EH4000_front_suspension_V7_final.stl"


class EvidenceOut(BaseModel):
    id: int
    filename: str
    media_type: str
    uploaded_at: datetime
    inspection_id: Optional[int]
    work_order_id: Optional[int]
    point: Optional[str]
    notes: Optional[str]
