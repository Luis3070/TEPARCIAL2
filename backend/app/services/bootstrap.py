from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Equipment, Inspection, InspectionPoint, MaintenanceEvent, Measurement, Model3DAsset, StructuralZone

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs"
POINTS = ("SD-01", "SD-02", "SD-03", "SD-04")
EQUIPMENT = "EH4-01"
ZONE = "Tijeras y spindle (suspensión delantera)"


def source_hash() -> str:
    path = ROOT / "DATOSCRUDOS" / "EH4000_historial_grietas.xlsx"
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def nullable(value):
    return None if pd.isna(value) else value


def ensure_reference_entities(db: Session) -> None:
    if not db.get(Equipment, EQUIPMENT):
        db.add(Equipment(id=EQUIPMENT, name="EH4000 Mining Truck", manufacturer="Hitachi", model="EH4000", active=True))
        db.flush()
    if not db.get(StructuralZone, "EH4-01-SD"):
        db.add(StructuralZone(id="EH4-01-SD", equipment_id=EQUIPMENT, name=ZONE, subsystem="Front suspension"))
        db.flush()
    limits = json.loads((OUT / "qa_summary.json").read_text(encoding="utf-8"))["points"]
    descriptions = {"SD-01":"Metal base de tijeras, lado derecho", "SD-02":"Metal base de tijeras, lado izquierdo",
                    "SD-03":"Metal base de spindle, lado derecho", "SD-04":"Metal base de spindle, lado izquierdo"}
    for point in POINTS:
        if not db.get(InspectionPoint, point):
            db.add(InspectionPoint(code=point, zone_id="EH4-01-SD", description=descriptions[point],
                caution_mm=float(limits[point]["caution_mm"]), danger_mm=float(limits[point]["danger_mm"])))
    model_file=ROOT/"frontend"/"public"/"assets"/"EH4000_front_suspension_V7_final.stl"
    if model_file.exists():
        asset = db.get(Model3DAsset, "front-suspension-v7")
        if asset is None:
            asset = Model3DAsset(id="front-suspension-v7",filename=model_file.name,format="STL",
                stored_path="frontend/public/assets/EH4000_front_suspension_V7_final.stl",units=None,mesh_count=1,
                vertex_count=354072,face_count=118024,dimensions={"x":4039.9277,"y":8834.0,"z":2619.9212},
                byte_size=model_file.stat().st_size,is_watertight=False,is_winding_consistent=True,
                source_hash=hashlib.sha256(model_file.read_bytes()).hexdigest(),coordinate_transform="display copy: rotate X -90°, center, uniform fit scale")
            db.add(asset)
        else:
            # Backfill only metadata introduced after initial local bootstrap.
            asset.byte_size = asset.byte_size or model_file.stat().st_size
            if asset.is_watertight is None:
                asset.is_watertight = False
            if asset.is_winding_consistent is None:
                asset.is_winding_consistent = True
    db.commit()


def import_validated_history(db: Session) -> dict:
    """Idempotently import only absent historical inspection dates."""
    if not (OUT / "maintenance" / "maintenance_features.csv").exists():
        raise FileNotFoundError(f"Falta {OUT / 'maintenance' / 'maintenance_features.csv'}")
    ensure_reference_entities(db)
    features = pd.read_csv(OUT / "maintenance" / "maintenance_features.csv", parse_dates=["date"])
    comments = pd.read_csv(OUT / "sd_inspections_qa.csv", parse_dates=["Fecha"])
    events_path = OUT / "qa_maintenance_events.csv"
    events = pd.read_csv(events_path, parse_dates=["Fecha"]) if events_path.exists() else pd.DataFrame()
    digest = source_hash()
    imported = 0
    for (inspection_date, equipment), group in features.groupby(["date", "equipment"], sort=True):
        inspection_date = inspection_date.date()
        existing = db.scalar(select(Inspection).where(Inspection.equipment == equipment, Inspection.date == inspection_date))
        if existing:
            continue
        row0 = group.iloc[0]
        event_group = events[events["Fecha"].dt.date.eq(inspection_date)] if not events.empty else pd.DataFrame()
        header = Inspection(equipment=equipment, zone=str(row0["zone"]), date=inspection_date,
            hours=float(row0["hours"]), inspector=str(row0["inspector"]), imported=True,
            source_hash=digest, maintenance_event=not event_group.empty)
        db.add(header)
        db.flush()
        comment_rows = comments[comments["Fecha"].dt.date.eq(inspection_date)].set_index("Código")
        for _, r in group.iterrows():
            source = comment_rows.loc[r["point"]] if r["point"] in comment_rows.index else None
            comment = nullable(source["Comentario"]) if source is not None else None
            image = nullable(source["Imagen"]) if source is not None else None
            db.add(Measurement(inspection_id=header.id, point=str(r["point"]), description=str(r["description"]),
                length_mm=nullable(r["L_raw_mm"]), caution_mm=float(r["caution_mm"]), danger_mm=float(r["danger_mm"]),
                structural_state=str(r["structural_state"]), severity_ratio=nullable(r["severity_ratio"]),
                delta_l_raw=nullable(r["delta_L_raw"]), delta_l_effective=nullable(r["delta_L_effective"]),
                delta_l_bridged_raw=nullable(r["delta_L_bridged_raw"]),
                bridged_from_date=nullable(pd.to_datetime(r["bridged_from_date"]).date()) if pd.notna(r["bridged_from_date"]) else None,
                bridged_elapsed_hours=nullable(r["bridged_elapsed_hours"]), bridge_null_count=int(r["bridge_null_count"]),
                gap_spanning_change=bool(r["gap_spanning_change"]),
                change_class=str(r["change_class"]), raw_growth_rate=nullable(r["raw_growth_rate_mm_1000h"]),
                effective_growth_rate=nullable(r["effective_growth_rate_mm_1000h"]), maintenance_segment=int(r["maintenance_segment"]),
                maintenance_action=str(r["maintenance_action"]), maintenance_priority=nullable(r["maintenance_priority"]),
                maintenance_mode=nullable(r["maintenance_mode"]), decision_reason=str(r["decision_reason"]),
                data_warning=nullable(r["data_warning"]), comment=None if pd.isna(comment) else str(comment),
                image_file=None if pd.isna(image) else str(image), source_row=int(r["fila_excel_origen"])))
        imported += 1
    if not events.empty:
        for _, r in events.iterrows():
            exists = db.scalar(select(MaintenanceEvent.id).where(
                MaintenanceEvent.date == r["Fecha"].date(), MaintenanceEvent.point == str(r["punto"]),
                MaintenanceEvent.source_row == int(r["fila_excel"])))
            if exists:
                continue
            db.add(MaintenanceEvent(date=r["Fecha"].date(), hours=nullable(r["horas"]), point=str(r["punto"]),
                comment=str(r["Comentario"]), event_type=str(r["tipo_inferido"]), confidence=str(r["confianza"]),
                source_row=int(r["fila_excel"]), source="historical"))
    db.commit()
    return {"inspection_dates_added": imported, "measurements": db.query(Measurement).count(), "source_hash": digest}


def load_snapshot_rows() -> list[dict]:
    path = OUT / "maintenance" / "zone_snapshot.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    return [{**{k: nullable(v) for k, v in r.items()}, "date": r["date"].date().isoformat()}
            for r in df.to_dict("records")]
