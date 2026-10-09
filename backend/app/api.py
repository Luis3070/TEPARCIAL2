from __future__ import annotations

import json
import math
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .maintenance.rules import decision
from .models import (AuditLog, Evidence, HotspotCalibration, Inspection, MaintenanceEvent, Model3DAsset,
                     Measurement, WorkOrder, WorkOrderStatusHistory)
from .schemas import (EvidenceOut, HotspotInput, InspectionCreate, InspectionOut,
                      MeasurementOut, WorkOrderCreate, WorkOrderOut, WorkOrderPatch)
from .services.bootstrap import OUT, ROOT, load_snapshot_rows, source_hash

router = APIRouter(prefix="/api")
POINTS = ("SD-01", "SD-02", "SD-03", "SD-04")
DESCRIPTIONS = {"SD-01": "Metal base de tijeras, lado derecho", "SD-02": "Metal base de tijeras, lado izquierdo",
                "SD-03": "Metal base de spindle, lado derecho", "SD-04": "Metal base de spindle, lado izquierdo"}
ZONE = "Tijeras y spindle (suspensión delantera)"
STATUSES = {"Normal": "NORMAL", "Alerta": "ALERT", "Crítico": "CRITICAL", "N/I": "INCOMPLETE"}
VALID_TRANSITIONS = {"PENDING": {"APPROVED", "CANCELED"}, "APPROVED": {"SCHEDULED", "CANCELED"},
                     "SCHEDULED": {"IN_PROGRESS", "CANCELED"}, "IN_PROGRESS": {"COMPLETED", "CANCELED"},
                     "COMPLETED": set(), "CANCELED": set()}
STATE_COLORS = {"Normal": "#38874a", "Alerta": "#d29b1c", "Crítico": "#c53b32", "N/I": "#88919d"}


def to_measurement(m: Measurement) -> dict:
    return MeasurementOut.model_validate(m).model_dump(mode="json")


def to_inspection(i: Inspection) -> dict:
    return InspectionOut(id=i.id, equipment=i.equipment, zone=i.zone, date=i.date, hours=i.hours,
        inspector=i.inspector, imported=i.imported, maintenance_event=i.maintenance_event,
        measurements=sorted(i.measurements, key=lambda m: m.point)).model_dump(mode="json")


def get_inspection_or_404(db: Session, inspection_id: int) -> Inspection:
    obj = db.scalar(select(Inspection).options(selectinload(Inspection.measurements)).where(Inspection.id == inspection_id))
    if not obj: raise HTTPException(404, "Inspección no encontrada.")
    return obj


def json_summary() -> dict:
    return json.loads((OUT / "maintenance" / "maintenance_summary.json").read_text(encoding="utf-8"))


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "database": "connected", "inspection_dates": db.query(Inspection).count(),
            "historical_mode": "last recorded inspection; no live telemetry"}


@router.get("/equipment")
def equipment(db: Session = Depends(get_db)):
    latest = db.scalar(select(Inspection).options(selectinload(Inspection.measurements))
        .where(Inspection.equipment == "EH4-01").order_by(Inspection.date.desc()).limit(1))
    if latest is None: raise HTTPException(404, "No hay inspecciones importadas.")
    return [{"id": "EH4-01", "name": "EH4000 Mining Truck", "serial": "EH4-01", "zone": ZONE,
        "latest_date": latest.date.isoformat(), "latest_hours": latest.hours, "inspector": latest.inspector,
        "live_telemetry": False, "latest_condition_is_historical": True}]


@router.get("/equipment/{equipment_id}")
def equipment_detail(equipment_id: str, db: Session = Depends(get_db)):
    if equipment_id != "EH4-01": raise HTTPException(404, "Equipo fuera del alcance actual.")
    return equipment(db)[0]


@router.get("/points")
def points(inspection_id: int | None = None, db: Session = Depends(get_db)):
    if inspection_id is not None:
        ins = get_inspection_or_404(db, inspection_id)
        measurements = sorted(ins.measurements, key=lambda m: m.point)
    else:
        latest = db.scalar(select(Inspection).order_by(Inspection.date.desc()).limit(1))
        measurements = [] if latest is None else db.scalars(select(Measurement).where(Measurement.inspection_id == latest.id).order_by(Measurement.point)).all()
    if not measurements:
        return [{"code": p, "description": DESCRIPTIONS[p], "structural_state": "N/I", "length_mm": None,
                 "caution_mm": None, "danger_mm": None, "calibration": None} for p in POINTS]
    calibrations = {c.point: c for c in db.scalars(select(HotspotCalibration)).all()}
    return [{"code": m.point, "description": m.description, "structural_state": m.structural_state,
        "length_mm": m.length_mm, "caution_mm": m.caution_mm, "danger_mm": m.danger_mm,
        "severity_ratio": m.severity_ratio, "maintenance_action": m.maintenance_action,
        "maintenance_priority": m.maintenance_priority, "decision_reason": m.decision_reason,
        "delta_l_raw":m.delta_l_raw,"delta_l_effective":m.delta_l_effective,
        "raw_growth_rate":m.raw_growth_rate,"effective_growth_rate":m.effective_growth_rate,
        "change_class":m.change_class,"maintenance_segment":m.maintenance_segment,
        "delta_l_bridged_raw":m.delta_l_bridged_raw,"bridged_from_date":m.bridged_from_date,
        "bridged_elapsed_hours":m.bridged_elapsed_hours,"bridge_null_count":m.bridge_null_count,
        "gap_spanning_change":m.gap_spanning_change,
        "calibration": calibration_out(calibrations.get(m.point))} for m in measurements]


def calibration_out(c):
    if c is None: return None
    return {"x": c.x, "y": c.y, "z": c.z, "normal": [c.nx, c.ny, c.nz],
            "calibrated_at": c.calibrated_at.isoformat(), "calibrated_by": c.calibrated_by,
            "confirmed": c.confirmed, "model_asset": c.model_asset}


@router.get("/points/{code}")
def point_detail(code: str, db: Session = Depends(get_db)):
    if code not in POINTS: raise HTTPException(404, "Punto fuera del alcance actual.")
    history = db.scalars(select(Measurement).join(Inspection).options(selectinload(Measurement.inspection))
        .where(Measurement.point == code).order_by(Inspection.date.desc()).limit(1)).first()
    if history is None: raise HTTPException(404, "Sin lecturas para el punto.")
    return {**to_measurement(history), "equipment": history.inspection.equipment, "zone": history.inspection.zone,
            "date": history.inspection.date.isoformat(), "hours": history.inspection.hours,
            "inspector": history.inspection.inspector, "localization_status": "requires manual verification"}


@router.get("/points/{code}/history")
def point_history(code: str, db: Session = Depends(get_db)):
    if code not in POINTS: raise HTTPException(404, "Punto fuera del alcance actual.")
    rows = db.scalars(select(Measurement).join(Inspection).options(selectinload(Measurement.inspection))
        .where(Measurement.point == code).order_by(Inspection.date)).all()
    return [{**to_measurement(m), "date": m.inspection.date.isoformat(), "hours": m.inspection.hours,
             "inspector": m.inspection.inspector, "equipment": m.inspection.equipment,
             "maintenance_event_at_date": m.inspection.maintenance_event} for m in rows]


@router.get("/inspections")
def inspections(start: date | None = None, end: date | None = None, point: str | None = None,
                limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0),
                db: Session = Depends(get_db)):
    query = select(Inspection).options(selectinload(Inspection.measurements)).where(Inspection.equipment == "EH4-01")
    if start: query = query.where(Inspection.date >= start)
    if end: query = query.where(Inspection.date <= end)
    if point:
        if point not in POINTS: raise HTTPException(422, "Punto inválido.")
        query = query.join(Inspection.measurements).where(Measurement.point == point)
    rows = db.scalars(query.order_by(Inspection.date.desc()).limit(limit).offset(offset)).unique().all()
    return [to_inspection(i) for i in rows]


@router.get("/inspections/{inspection_id}")
def inspection_detail(inspection_id: int, db: Session = Depends(get_db)):
    return to_inspection(get_inspection_or_404(db, inspection_id))


@router.post("/inspections", status_code=201)
def create_inspection(payload: InspectionCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(Inspection.id).where(Inspection.equipment == payload.equipment, Inspection.date == payload.date))
    if existing: raise HTTPException(409, "Ya existe una inspección para este equipo y fecha; no se sobrescriben históricos.")
    previous = db.scalar(select(Inspection).options(selectinload(Inspection.measurements))
        .where(Inspection.equipment == payload.equipment).order_by(Inspection.date.desc()).limit(1))
    if previous and payload.date <= previous.date:
        raise HTTPException(422, f"La nueva inspección debe ser posterior a la última fecha ({previous.date.isoformat()}).")
    if previous and payload.hours < previous.hours:
        raise HTTPException(422, f"El horómetro ({payload.hours:g}) es menor al último registrado ({previous.hours:g}).")
    qa_config=json.loads((OUT / "qa_summary.json").read_text(encoding="utf-8"))
    limits = qa_config["points"]
    tolerance = float(qa_config["measurement_uncertainty"]["tolerance_mm"])
    inspection = Inspection(equipment=payload.equipment, zone=ZONE, date=payload.date, hours=payload.hours,
                            inspector=payload.inspector, imported=False)
    db.add(inspection); db.flush()
    previous_by_point = {m.point: m for m in previous.measurements} if previous else {}
    any_event = False
    for item in payload.measurements:
        cfg = limits[item.point]
        caution, danger = float(cfg["caution_mm"]), float(cfg["danger_mm"])
        before = previous_by_point.get(item.point)
        comment = item.comment.strip() if item.comment else None
        text_event = bool(comment and re.search(r"repar|soldad|interven|cambio|reparaci[oó]n general", comment, re.I))
        maintenance_event = bool(item.maintenance_event or text_event)
        any_event = any_event or maintenance_event
        raw = item.length_mm
        state = "N/I" if raw is None else ("Normal" if raw < caution else "Alerta" if raw < danger else "Crítico")
        ratio = None if raw is None else raw / danger
        delta = None
        delta_eff = None
        delta_bridge = None
        bridged_from = None
        bridged_hours = None
        bridge_null_count = 0
        gap_spanning_change = False
        change = "N_I"
        raw_rate = None
        effective_rate = None
        warning = None if raw is not None else "CURRENT_MEASUREMENT_NULL"
        boundary = maintenance_event
        if raw is not None and before is not None:
            if before.length_mm is None:
                change = "N_I"
                warning = "PREVIOUS_MEASUREMENT_NULL"
                prior_valid = db.scalar(select(Measurement).join(Inspection).where(Measurement.point==item.point,
                    Measurement.length_mm.is_not(None), Inspection.date < previous.date).order_by(Inspection.date.desc()).limit(1))
                if prior_valid and not maintenance_event:
                    intervening_event = db.scalar(select(MaintenanceEvent.id).where(MaintenanceEvent.point==item.point,
                        MaintenanceEvent.date>prior_valid.inspection.date, MaintenanceEvent.date<=payload.date).limit(1))
                    if not intervening_event:
                        gap_spanning_change=True
                        delta_bridge=raw-prior_valid.length_mm
                        bridged_from=prior_valid.inspection.date
                        bridged_hours=payload.hours-prior_valid.inspection.hours
                        # Count NULL rows directly; elapsed time is never treated as a regular inspection interval.
                        bridge_null_count=db.query(Measurement).join(Inspection).filter(Measurement.point==item.point,
                            Measurement.length_mm.is_(None),Inspection.date>prior_valid.inspection.date,Inspection.date<payload.date).count()
                        warning="GAP_SPANNING_CHANGE"
            elif boundary:
                delta = raw - before.length_mm
                delta_eff = 0.0 if abs(delta) <= tolerance else delta
                change = "MAINTENANCE_RESET"
            else:
                delta = raw - before.length_mm
                delta_eff = 0.0 if abs(delta) <= tolerance else delta
                if abs(delta) <= tolerance: change = "STABLE_WITHIN_TOLERANCE"
                elif delta > tolerance: change = "SIGNIFICANT_GROWTH"
                else: change = "SIGNIFICANT_DECREASE_REVIEW"
                delta_hours = payload.hours - previous.hours
                if delta_hours > 0:
                    raw_rate = delta / delta_hours * 1000
                    effective_rate = 0.0 if abs(delta) <= tolerance else raw_rate
        elif raw is not None and previous is None:
            warning = "INITIAL_MEASURE"
        first_post_repair = maintenance_event or (before is not None and bool(previous and previous.maintenance_event))
        prior_measure_count=db.query(Measurement).join(Inspection).filter(Measurement.point==item.point,
            Measurement.length_mm.is_not(None),Inspection.date<payload.date).count()
        first_valid = raw is not None and prior_measure_count==0
        row = {"structural_state": state, "change_class": change, "L_raw_mm": raw, "caution_mm": caution,
               "danger_mm": danger, "delta_L_raw": delta, "gap_spanning_change": gap_spanning_change, "delta_L_bridged_raw": delta_bridge}
        action, priority, mode, reason = decision(row, first_post_repair, first_valid)
        measurement = Measurement(inspection_id=inspection.id, point=item.point, description=DESCRIPTIONS[item.point],
            length_mm=raw, caution_mm=caution, danger_mm=danger, structural_state=state, severity_ratio=ratio,
            delta_l_raw=delta, delta_l_effective=delta_eff, change_class=change,
            delta_l_bridged_raw=delta_bridge,bridged_from_date=bridged_from,bridged_elapsed_hours=bridged_hours,
            bridge_null_count=bridge_null_count,gap_spanning_change=gap_spanning_change,
            raw_growth_rate=raw_rate, effective_growth_rate=effective_rate,
            maintenance_segment=(before.maintenance_segment + 1 if before and maintenance_event else before.maintenance_segment if before else 0),
            maintenance_action=action, maintenance_priority=priority, maintenance_mode=mode, decision_reason=reason,
            data_warning=warning, comment=comment, image_file=None, source_row=None)
        db.add(measurement); db.flush()
        if maintenance_event:
            db.add(MaintenanceEvent(date=payload.date, hours=payload.hours, point=item.point,
                comment=comment or "Evento de mantenimiento marcado por el usuario.",
                event_type="maintenance action", confidence="user documented", source="user"))
        db.add(AuditLog(entity="Inspection", entity_id=str(inspection.id), action="CREATED", actor=payload.inspector,
                        details={"point": item.point, "raw_length_mm": raw, "structural_state": state}))
    inspection.maintenance_event = any_event
    db.commit()
    return to_inspection(get_inspection_or_404(db, inspection.id))


@router.get("/snapshots")
def snapshots(db: Session = Depends(get_db)):
    all_rows = load_snapshot_rows()
    inspections = db.scalars(select(Inspection).options(selectinload(Inspection.measurements)).order_by(Inspection.date)).all()
    by_date = {i.date.isoformat(): i for i in inspections}
    result = []
    for row in all_rows:
        ins = by_date.get(row["date"])
        row["inspection_id"] = ins.id if ins else None
        result.append(row)
    for ins in inspections:
        if ins.imported: continue
        measurements = ins.measurements
        counts = {state: sum(m.structural_state == state for m in measurements) for state in ("Normal", "Alerta", "Crítico", "N/I")}
        if counts["Crítico"]: zone_state = "CRITICAL"
        elif counts["Alerta"]: zone_state = "ALERT"
        elif counts["N/I"]: zone_state = "INCOMPLETE"
        else: zone_state = "NORMAL"
        rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}
        worst = max(measurements, key=lambda m: (rank.get(m.maintenance_priority or "", -1), m.severity_ratio or 0, m.point))
        result.append({"date": ins.date.isoformat(), "hours": ins.hours, "zone_state": zone_state, "worst_point": worst.point,
            "max_severity_ratio": max((m.severity_ratio or 0 for m in measurements), default=None),
            "normal_count": counts["Normal"], "alert_count": counts["Alerta"], "critical_count": counts["Crítico"],
            "not_inspected_count": counts["N/I"], "significant_growth_count": sum(m.change_class == "SIGNIFICANT_GROWTH" for m in measurements),
            "highest_priority": worst.maintenance_priority, "recommended_action": worst.maintenance_action,
            "maintenance_event": ins.maintenance_event, "data_completeness_pct": sum(m.length_mm is not None for m in measurements)/4*100,
            "inspection_id": ins.id})
    return sorted(result, key=lambda r: r["date"])


@router.get("/snapshots/{inspection_id}")
def snapshot_detail(inspection_id: int, db: Session = Depends(get_db)):
    inspection = get_inspection_or_404(db, inspection_id)
    return next((r for r in snapshots(db) if r["date"] == inspection.date.isoformat()), None)


@router.get("/maintenance/recommendations")
def recommendations(inspection_id: int | None = None, db: Session = Depends(get_db)):
    if inspection_id:
        inspection = get_inspection_or_404(db, inspection_id)
        return [recommendation_out(m, inspection) for m in sorted(inspection.measurements, key=lambda x:x.point)]
    latest = db.scalar(select(Inspection).order_by(Inspection.date.desc()).limit(1))
    if latest is None: return []
    latest = get_inspection_or_404(db, latest.id)
    return [recommendation_out(m, latest) for m in sorted(latest.measurements, key=lambda x:x.point)]


def recommendation_out(m: Measurement, i: Inspection):
    return {"measurement_id": m.id, "inspection_id": i.id, "date": i.date.isoformat(), "hours": i.hours,
        "point": m.point, "description": m.description, "structural_state": m.structural_state,
        "length_mm": m.length_mm, "caution_mm": m.caution_mm, "danger_mm": m.danger_mm,
        "action": m.maintenance_action, "priority": m.maintenance_priority, "mode": m.maintenance_mode,
        "reason": m.decision_reason, "data_warning": m.data_warning, "status": "RECOMMENDED_NOT_ORDERED"}


@router.get("/maintenance/events")
def maintenance_events(db: Session = Depends(get_db)):
    rows = db.scalars(select(MaintenanceEvent).order_by(MaintenanceEvent.date, MaintenanceEvent.point)).all()
    return [{"id": e.id, "date": e.date.isoformat(), "hours": e.hours, "point": e.point,
        "comment": e.comment, "event_type": e.event_type, "confidence": e.confidence,
        "source_row": e.source_row, "source": e.source, "classification": "MAINTENANCE_EVENT"} for e in rows]


@router.get("/work-orders", response_model=list[WorkOrderOut])
def work_orders(status: str | None = None, point: str | None = None, db: Session = Depends(get_db)):
    query = select(WorkOrder)
    if status: query = query.where(WorkOrder.status == status)
    if point:
        if point not in POINTS: raise HTTPException(422, "Punto inválido.")
        query = query.where(WorkOrder.point == point)
    return db.scalars(query.order_by(WorkOrder.created_at.desc())).all()


@router.post("/work-orders", status_code=201, response_model=WorkOrderOut)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db)):
    source = None
    if payload.source_measurement_id is not None:
        source = db.get(Measurement, payload.source_measurement_id)
        if source is None: raise HTTPException(404, "La medición de origen no existe.")
        if source.point != payload.point: raise HTTPException(422, "La medición de origen pertenece a otro punto.")
    wo = WorkOrder(**payload.model_dump(), status="PENDING")
    db.add(wo); db.flush()
    db.add(WorkOrderStatusHistory(work_order_id=wo.id, from_status=None, to_status="PENDING", notes="Orden creada; recomendación no equivale a aprobación."))
    db.add(AuditLog(entity="WorkOrder", entity_id=str(wo.id), action="CREATED", details={"status":"PENDING","point":wo.point}))
    db.commit(); db.refresh(wo)
    return wo


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderOut)
def patch_work_order(work_order_id: int, payload: WorkOrderPatch, db: Session = Depends(get_db)):
    wo = db.get(WorkOrder, work_order_id)
    if not wo: raise HTTPException(404, "Orden no encontrada.")
    updates = payload.model_dump(exclude_unset=True)
    target = updates.pop("status", None)
    note = updates.pop("status_note", None)
    if target and target != wo.status:
        if target not in VALID_TRANSITIONS[wo.status]: raise HTTPException(409, f"Transición inválida: {wo.status} → {target}.")
        if target == "SCHEDULED" and not (updates.get("scheduled_date") or wo.scheduled_date):
            raise HTTPException(422, "Una orden programada requiere fecha explícita.")
        old = wo.status; wo.status = target
        if target == "COMPLETED": wo.closed_at = datetime.now(timezone.utc)
        if target == "CANCELED": wo.closed_at = datetime.now(timezone.utc)
        db.add(WorkOrderStatusHistory(work_order_id=wo.id, from_status=old, to_status=target, notes=note))
        db.add(AuditLog(entity="WorkOrder", entity_id=str(wo.id), action="STATUS_CHANGED", details={"from":old,"to":target,"note":note}))
    for key, value in updates.items(): setattr(wo, key, value)
    db.commit(); db.refresh(wo)
    return wo


@router.get("/work-orders/{work_order_id}/history")
def work_order_history(work_order_id: int, db: Session = Depends(get_db)):
    if not db.get(WorkOrder, work_order_id): raise HTTPException(404, "Orden no encontrada.")
    rows = db.scalars(select(WorkOrderStatusHistory).where(WorkOrderStatusHistory.work_order_id == work_order_id).order_by(WorkOrderStatusHistory.changed_at)).all()
    return [{"from_status":h.from_status,"to_status":h.to_status,"changed_at":h.changed_at.isoformat(),"notes":h.notes} for h in rows]


@router.post("/evidence", status_code=201, response_model=EvidenceOut)
async def upload_evidence(file: UploadFile = File(...), point: str | None = Form(default=None),
                          inspection_id: int | None = Form(default=None), work_order_id: int | None = Form(default=None),
                          notes: str | None = Form(default=None), db: Session = Depends(get_db)):
    if point and point not in POINTS: raise HTTPException(422, "Punto inválido.")
    if inspection_id and not db.get(Inspection, inspection_id): raise HTTPException(404, "Inspección no encontrada.")
    if work_order_id and not db.get(WorkOrder, work_order_id): raise HTTPException(404, "Orden no encontrada.")
    if not (inspection_id or work_order_id): raise HTTPException(422, "Asocia la evidencia a una inspección o una orden.")
    allowed = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    if file.content_type not in allowed: raise HTTPException(415, "Adjunta JPG, PNG, WEBP o PDF.")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024: raise HTTPException(413, "Tamaño máximo: 20 MB.")
    suffix = Path(file.filename or "evidence").suffix[:10]
    target = ROOT / "backend" / "uploads" / f"{uuid.uuid4().hex}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    row = Evidence(filename=Path(file.filename or "evidence").name, stored_path=str(target), media_type=file.content_type,
        inspection_id=inspection_id, work_order_id=work_order_id, point=point, notes=notes)
    db.add(row); db.flush()
    db.add(AuditLog(entity="Evidence", entity_id=str(row.id), action="UPLOADED", details={"filename":row.filename,"point":point}))
    db.commit(); db.refresh(row)
    return row


@router.get("/evidence")
def list_evidence(point: str | None = None, inspection_id: int | None = None, work_order_id: int | None = None,
                  db: Session = Depends(get_db)):
    query = select(Evidence)
    if point: query = query.where(Evidence.point == point)
    if inspection_id: query = query.where(Evidence.inspection_id == inspection_id)
    if work_order_id: query = query.where(Evidence.work_order_id == work_order_id)
    return db.scalars(query.order_by(Evidence.uploaded_at.desc())).all()


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: int, db: Session = Depends(get_db)):
    row = db.get(Evidence, evidence_id)
    if not row or not Path(row.stored_path).is_file(): raise HTTPException(404, "Archivo de evidencia no encontrado.")
    return FileResponse(row.stored_path, media_type=row.media_type, filename=row.filename)


@router.get("/3d/models")
def models(db:Session=Depends(get_db)):
    asset=db.get(Model3DAsset,"front-suspension-v7")
    path=ROOT/asset.stored_path if asset else ROOT/"frontend"/"public"/"assets"/"EH4000_front_suspension_V7_final.stl"
    return [{"id":asset.id if asset else "front-suspension-v7","filename":asset.filename if asset else path.name,
        "format":asset.format if asset else "STL","available":path.exists(),"asset_url":"/assets/EH4000_front_suspension_V7_final.stl",
        "role":"technical inspection component","geometry_units":asset.units or "not documented in source STL",
        "mesh_count":asset.mesh_count if asset else 1,"vertex_count":asset.vertex_count if asset else 354072,
        "face_count":asset.face_count if asset else 118024,"byte_size":asset.byte_size if asset else path.stat().st_size if path.exists() else None,
        "dimensions_source_units":asset.dimensions if asset else {"x":4039.9277,"y":8834.0,"z":2619.9212},
        "is_watertight":asset.is_watertight if asset else False,"is_winding_consistent":asset.is_winding_consistent if asset else True,
        "coordinate_transform":asset.coordinate_transform if asset else "rotate X -90°, center, uniform fit scale",
        "coordinate_calibration":"manual, unconfirmed until engineering review"}]


@router.get("/3d/hotspots")
def hotspots(db: Session = Depends(get_db)):
    rows = {h.point:h for h in db.scalars(select(HotspotCalibration)).all()}
    return [{"code":p,"description":DESCRIPTIONS[p],"calibration":calibration_out(rows.get(p)),
             "calibration_status":"CONFIRMED" if rows.get(p) and rows[p].confirmed else "UNVERIFIED" if rows.get(p) else "NOT_CALIBRATED"}
            for p in POINTS]


@router.put("/3d/hotspots/{code}")
def put_hotspot(code: str, payload: HotspotInput, db: Session = Depends(get_db)):
    if code not in POINTS: raise HTTPException(404, "Punto fuera del alcance actual.")
    current = db.get(HotspotCalibration, code)
    details = {k:v for k,v in payload.model_dump().items()}
    if current:
        for k,v in details.items(): setattr(current,k,v)
        current.calibrated_at = datetime.now(timezone.utc)
    else:
        current = HotspotCalibration(point=code, **details)
        db.add(current)
    db.add(AuditLog(entity="HotspotCalibration", entity_id=code, action="CALIBRATED" if payload.confirmed else "POSITION_SAVED", actor=payload.calibrated_by,
        details={"position":[payload.x,payload.y,payload.z],"confirmed":payload.confirmed,"model":payload.model_asset}))
    db.commit(); db.refresh(current)
    return {"code":code,"description":DESCRIPTIONS[code],"calibration":calibration_out(current),
            "calibration_status":"CONFIRMED" if current.confirmed else "UNVERIFIED"}


@router.get("/analytics/overview")
def analytics_overview(inspection_id: int | None = None, db: Session = Depends(get_db)):
    if inspection_id:
        inspection = get_inspection_or_404(db, inspection_id)
    else:
        latest = db.scalar(select(Inspection).order_by(Inspection.date.desc()).limit(1))
        if latest is None: raise HTTPException(404,"No hay inspecciones.")
        inspection = get_inspection_or_404(db,latest.id)
    counts = {s:sum(m.structural_state==s for m in inspection.measurements) for s in ("Normal","Alerta","Crítico","N/I")}
    priority_rank={"P0":0,"P1":1,"P2":2,"P3":3,"P4":4}
    latest_recommendation=max(inspection.measurements,key=lambda m:(priority_rank.get(m.maintenance_priority or "",-1),m.severity_ratio or 0,m.point))
    inspections_all=db.scalars(select(Inspection).order_by(Inspection.date)).all()
    dates=[i.date for i in inspections_all]
    delta_days=[(dates[j]-dates[j-1]).days for j in range(1,len(dates))]
    hours=[i.hours for i in inspections_all]
    delta_hours=[hours[j]-hours[j-1] for j in range(1,len(hours))]
    import statistics
    def stats(values):
        if not values:return {"n":0,"mean":None,"median":None,"std":None,"min":None,"max":None}
        return {"n":len(values),"mean":statistics.mean(values),"median":statistics.median(values),"std":statistics.stdev(values) if len(values)>1 else 0,"min":min(values),"max":max(values)}
    return {"equipment":"EH4-01","zone":ZONE,"inspection_id":inspection.id,"date":inspection.date.isoformat(),
        "hours":inspection.hours,"inspector":inspection.inspector,"historical_only":True,"live_telemetry":False,
        "counts":counts,"zone_state":"CRITICAL" if counts["Crítico"] else "ALERT" if counts["Alerta"] else "INCOMPLETE" if counts["N/I"] else "NORMAL",
        "worst_point":latest_recommendation.point,"highest_priority":latest_recommendation.maintenance_priority,
        "recommended_action":latest_recommendation.maintenance_action,"data_completeness_pct":sum(m.length_mm is not None for m in inspection.measurements)/4*100,
        "temporal":{"delta_days":stats(delta_days),"delta_hours":stats(delta_hours)},
        "points":[{**recommendation_out(m,inspection),"margin_to_caution_mm":None if m.length_mm is None else m.caution_mm-m.length_mm,
                    "margin_to_danger_mm":None if m.length_mm is None else m.danger_mm-m.length_mm,
                    "severity_ratio":m.severity_ratio} for m in sorted(inspection.measurements,key=lambda m:m.point)]}


@router.get("/analytics/history")
def analytics_history(db: Session=Depends(get_db)):
    return {p:point_history(p,db) for p in POINTS}


@router.get("/analytics/qa")
def analytics_qa():
    path=OUT/"qa_summary.json"
    if not path.exists():raise HTTPException(404,"QA summary no está disponible.")
    payload=json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("validation",{})["source_unchanged"]=source_hash()==payload.get("source_sha256")
    tests_path=OUT/"qa_tests.csv"
    if tests_path.exists():
        import csv
        with tests_path.open(encoding="utf-8-sig",newline="") as handle:payload["tests"]=list(csv.DictReader(handle))
    return payload


@router.get("/analytics/maintenance-summary")
def maintenance_summary():
    path=OUT/"maintenance"/"maintenance_summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/analytics/inspectors")
def inspectors(db: Session=Depends(get_db)):
    rows=db.scalars(select(Inspection).order_by(Inspection.date)).all()
    return [{"date":r.date.isoformat(),"inspector":r.inspector,"hours":r.hours,"inspection_id":r.id} for r in rows]


@router.get("/audit")
def audit_log(limit:int=Query(default=100,ge=1,le=500),db:Session=Depends(get_db)):
    rows=db.scalars(select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit)).all()
    return [{"id":r.id,"entity":r.entity,"entity_id":r.entity_id,"action":r.action,
        "occurred_at":r.occurred_at.isoformat(),"actor":r.actor,"details":r.details} for r in rows]
