#!/usr/bin/env python3
"""Deterministic maintenance features and decisions from validated EH4000 QA outputs.

Run from the workspace root with Python, pandas, numpy, matplotlib and openpyxl
not required (this layer consumes the QA CSV/JSON files and never edits RAW).
"""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backend.app.maintenance.rules import decision

QA = ROOT / "outputs"
OUT = QA / "maintenance"
PLOTS = OUT / "plots"
POINTS = ["SD-01", "SD-02", "SD-03", "SD-04"]
PRIORITY_ORDER = {f"P{i}": i for i in range(5)}
STATE_COLORS = {"Normal": "#4daf4a", "Alerta": "#ffbf00", "Crítico": "#d62728", "N/I": "#9e9e9e"}
ZONE_COLORS = {"NORMAL": "#4daf4a", "INCOMPLETE": "#9e9e9e", "ALERT": "#ffbf00", "CRITICAL": "#d62728", "UNKNOWN": "#5b6573"}


def safe_json(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp,)): return value.strftime("%Y-%m-%d")
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    if pd.isna(value): return None
    return value


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); PLOTS.mkdir(parents=True, exist_ok=True)
    inspections = pd.read_csv(QA / "sd_inspections_qa.csv", parse_dates=["Fecha"])
    deltas = pd.read_csv(QA / "sd_delta_L.csv", parse_dates=["fecha"])
    growth = pd.read_csv(QA / "sd_growth_rates.csv", parse_dates=["fecha"])
    repairs = pd.read_csv(QA / "qa_maintenance_events.csv", parse_dates=["Fecha"])
    qa_summary = json.loads((QA / "qa_summary.json").read_text(encoding="utf-8"))
    dates = sorted(inspections["Fecha"].dropna().unique())

    # Restrict to the validated scope and retain the QA-derived RAW/state fields.
    inspections = inspections[inspections["Código"].isin(POINTS) & inspections["Equipo"].eq("EH4-01")].copy()
    inspections = inspections.sort_values(["Fecha", "Código"]).copy()
    if len(inspections) != 100 or set(inspections["Código"].unique()) != set(POINTS):
        raise ValueError(f"Alcance inesperado en sd_inspections_qa.csv: {len(inspections)} filas")
    inspections["point"] = inspections["Código"]
    inspections["date"] = inspections["Fecha"]
    inspections["hours"] = pd.to_numeric(inspections["Horas (h)"], errors="coerce")
    inspections["L_raw_mm"] = pd.to_numeric(inspections["L actual (mm)"], errors="coerce")
    inspections["caution_mm"] = inspections["Código"].map({p: qa_summary["points"][p]["caution_mm"] for p in POINTS})
    inspections["danger_mm"] = inspections["Código"].map({p: qa_summary["points"][p]["danger_mm"] for p in POINTS})
    inspections["structural_state"] = inspections["structural_state"].fillna("N/I")

    # Join prior QA intervals, retaining exact 10 mm change classes and rates.
    key = ["Fecha", "Código"]
    delta_source = deltas.rename(columns={"fecha":"Fecha", "codigo":"Código"})
    growth_source = growth.rename(columns={"fecha":"Fecha", "codigo":"Código"})
    delta_cols = ["Fecha", "Código", "delta_L_raw", "delta_L_effective", "change_class", "desde_fecha", "delta_horas", "maintenance_boundary"]
    rate_cols = ["Fecha", "Código", "raw_growth_rate_mm_1000h", "effective_growth_rate_mm_1000h", "rate_exclusion_reason"]
    delta_source = delta_source[delta_cols]
    growth_source = growth_source[rate_cols]
    features = inspections.merge(delta_source, on=key, how="left", validate="one_to_one")
    features = features.merge(growth_source, on=key, how="left", validate="one_to_one")

    # Official-limit derived quantities; NaN remains NaN when L is unavailable.
    measured = features["L_raw_mm"].notna()
    features["severity_ratio"] = features["L_raw_mm"] / features["danger_mm"]
    features["caution_utilization"] = features["L_raw_mm"] / features["caution_mm"]
    features["margin_to_caution_mm"] = features["caution_mm"] - features["L_raw_mm"]
    features["margin_to_danger_mm"] = features["danger_mm"] - features["L_raw_mm"]
    features["margin_to_caution_pct"] = features["margin_to_caution_mm"] / features["caution_mm"] * 100
    features["margin_to_danger_pct"] = features["margin_to_danger_mm"] / features["danger_mm"] * 100
    features.loc[~measured, ["severity_ratio", "caution_utilization", "margin_to_caution_mm", "margin_to_danger_mm", "margin_to_caution_pct", "margin_to_danger_pct"]] = np.nan

    # Cadence deltas come from the validated inspection-level interval table.
    inspection_intervals = pd.read_csv(QA / "sd_intervals.csv", parse_dates=["Fecha"])
    interval_by_date = inspection_intervals.drop_duplicates("Fecha").set_index("Fecha")
    features["days_since_last_inspection"] = features["date"].map(interval_by_date["delta_dias"])
    features["hours_since_last_inspection"] = features["date"].map(interval_by_date["delta_horas"])

    # Repair segments are assigned by distinct, chronologically ordered event dates.
    repairs["punto"] = repairs["punto"].astype(str)
    repair_dates = sorted(pd.to_datetime(repairs["Fecha"].dropna().unique()))
    repair_hours = {pd.Timestamp(d): float(repairs.loc[repairs["Fecha"].eq(d), "horas"].iloc[0]) for d in repair_dates}
    features["maintenance_event"] = features["date"].isin(repair_dates) & features["point"].isin(repairs["punto"].unique())
    features["maintenance_segment"] = features["date"].apply(lambda d: sum(pd.Timestamp(r) <= d for r in repair_dates)).astype(int)
    features["days_since_last_repair"] = np.nan
    features["hours_since_last_repair"] = np.nan
    features["inspections_since_last_repair"] = np.nan
    inspection_dates = sorted(features["date"].unique())
    date_index = {pd.Timestamp(d): i for i, d in enumerate(inspection_dates)}
    for repair_date in repair_dates:
        repair_date = pd.Timestamp(repair_date)
        first_date = next((pd.Timestamp(d) for d in inspection_dates if pd.Timestamp(d) >= repair_date), None)
        if first_date is None: continue
        mask = features["date"] >= first_date
        last_repair_hours = repair_hours[repair_date]
        features.loc[mask, "days_since_last_repair"] = (features.loc[mask, "date"] - repair_date).dt.days
        features.loc[mask, "hours_since_last_repair"] = features.loc[mask, "hours"] - last_repair_hours
        features.loc[mask, "inspections_since_last_repair"] = features.loc[mask, "date"].map(lambda d: date_index[pd.Timestamp(d)] - date_index[first_date] + 1)
    features["is_first_post_repair_inspection"] = False
    for repair_date in repair_dates:
        first_date = next((pd.Timestamp(d) for d in inspection_dates if pd.Timestamp(d) >= pd.Timestamp(repair_date)), None)
        if first_date is not None: features.loc[features["date"].eq(first_date), "is_first_post_repair_inspection"] = True

    # First valid measurement is an explicit series baseline. A missing reading
    # remains NULL; a later valid reading may be compared with the last valid
    # pre-gap reading, but that bridge is never called a consecutive delta/rate.
    # Keep the global inspection chronology used by zone-level rollups; each
    # point group is already chronological in the source ordering.
    features["is_initial_measure"] = False
    features["delta_L_bridged_raw"] = np.nan
    features["bridged_from_date"] = pd.NaT
    features["bridged_from_hours"] = np.nan
    features["bridged_elapsed_days"] = np.nan
    features["bridged_elapsed_hours"] = np.nan
    features["bridge_null_count"] = 0
    features["gap_spanning_change"] = False
    features["data_warning"] = ""
    bridge_rows: list[dict[str, Any]] = []
    for point, group in features.groupby("point", sort=False):
        last_valid: pd.Series | None = None
        missing_between: list[pd.Series] = []
        first_valid_seen = False
        for idx, row in group.iterrows():
            # Do not compare across a repair boundary. The post-repair reading
            # starts a new measurement baseline for subsequent observations.
            if bool(row["maintenance_event"]):
                missing_between = []
                last_valid = None
            if pd.isna(row["L_raw_mm"]):
                features.at[idx, "data_warning"] = "CURRENT_MEASUREMENT_NULL"
                if last_valid is not None:
                    missing_between.append(row)
                continue
            if not first_valid_seen:
                features.at[idx, "is_initial_measure"] = True
                first_valid_seen = True
            if missing_between and last_valid is not None and not bool(row["maintenance_event"]):
                null_count = len(missing_between)
                delta_bridge = float(row["L_raw_mm"] - last_valid["L_raw_mm"])
                from_date = pd.Timestamp(last_valid["date"])
                elapsed_days = int((pd.Timestamp(row["date"]) - from_date).days)
                elapsed_hours = float(row["hours"] - last_valid["hours"])
                features.at[idx, "delta_L_bridged_raw"] = delta_bridge
                features.at[idx, "bridged_from_date"] = from_date
                features.at[idx, "bridged_from_hours"] = float(last_valid["hours"])
                features.at[idx, "bridged_elapsed_days"] = elapsed_days
                features.at[idx, "bridged_elapsed_hours"] = elapsed_hours
                features.at[idx, "bridge_null_count"] = null_count
                features.at[idx, "gap_spanning_change"] = True
                features.at[idx, "data_warning"] = "GAP_SPANNING_CHANGE"
                bridge_rows.append({
                    "point": point, "from_date": from_date, "to_date": pd.Timestamp(row["date"]),
                    "from_hours": float(last_valid["hours"]), "to_hours": float(row["hours"]),
                    "from_L_raw_mm": float(last_valid["L_raw_mm"]), "to_L_raw_mm": float(row["L_raw_mm"]),
                    "delta_L_bridged_raw": delta_bridge, "elapsed_days": elapsed_days,
                    "elapsed_hours": elapsed_hours, "null_observations_spanned": null_count,
                    "warning": "GAP_SPANNING_CHANGE", "rate_calculated": False,
                    "source_row_from": last_valid["fila_excel_origen"], "source_row_to": row["fila_excel_origen"],
                })
            missing_between = []
            last_valid = row
    features["bridged_change_class"] = np.where(features["gap_spanning_change"], "GAP_SPANNING_CHANGE", "")

    decisions = features.apply(lambda row: decision(row, bool(row["is_first_post_repair_inspection"]), bool(row["is_initial_measure"])), axis=1, result_type="expand")
    decisions.columns = ["maintenance_action", "maintenance_priority", "maintenance_mode", "decision_reason"]
    features[decisions.columns] = decisions
    features["maintenance_priority_rank"] = features["maintenance_priority"].map(PRIORITY_ORDER)

    # One deterministic zone snapshot per inspection date.
    snapshots = []
    for date, group in features.groupby("date", sort=True):
        state_counts = group["structural_state"].value_counts()
        normal = int(state_counts.get("Normal", 0)); alert = int(state_counts.get("Alerta", 0))
        critical = int(state_counts.get("Crítico", 0)); ni = int(state_counts.get("N/I", 0))
        if ni == len(group): zone_state = "UNKNOWN"
        elif critical: zone_state = "CRITICAL"
        elif alert: zone_state = "ALERT"
        elif ni: zone_state = "INCOMPLETE"  # explicit state prevents missing points implying NORMAL
        else: zone_state = "NORMAL"
        ranks = group["maintenance_priority_rank"]
        max_rank = ranks.max()
        candidates = group[ranks.eq(max_rank)].copy() if pd.notna(max_rank) else group.copy()
        candidates["severity_sort"] = candidates["severity_ratio"].fillna(-np.inf)
        chosen = candidates.sort_values(["severity_sort", "point"], ascending=[False, True], kind="stable").iloc[0]
        priority_tie = bool(pd.notna(max_rank) and len(candidates) > 1)
        snapshots.append({"date":date, "hours":group["hours"].iloc[0], "zone_state":zone_state,
            "worst_point":chosen["point"], "max_severity_ratio":group["severity_ratio"].max(skipna=True),
            "normal_count":normal, "alert_count":alert, "critical_count":critical, "not_inspected_count":ni,
            "significant_growth_count":int(group["change_class"].eq("SIGNIFICANT_GROWTH").sum()),
            "highest_priority":chosen["maintenance_priority"], "recommended_action":chosen["maintenance_action"],
            "maintenance_event":bool(group["maintenance_event"].any()),
            "data_completeness_pct":float(group["L_raw_mm"].notna().mean()*100),
            "priority_tie":priority_tie,
            "priority_tie_note":f"{len(candidates)} puntos comparten prioridad; se eligió mayor severity_ratio y empate residual por código ascendente." if priority_tie else ""})
    zone = pd.DataFrame(snapshots).sort_values("date").reset_index(drop=True)

    feature_columns = ["date", "hours", "Equipo", "Zona", "inspector", "point", "Descripción", "L_raw_mm", "caution_mm", "danger_mm",
        "structural_state", "severity_ratio", "caution_utilization", "margin_to_caution_mm", "margin_to_danger_mm", "margin_to_caution_pct", "margin_to_danger_pct",
        "delta_L_raw", "delta_L_effective", "change_class", "delta_L_bridged_raw", "bridged_change_class",
        "bridged_from_date", "bridged_from_hours", "bridged_elapsed_days", "bridged_elapsed_hours", "bridge_null_count",
        "gap_spanning_change", "data_warning", "raw_growth_rate_mm_1000h", "effective_growth_rate_mm_1000h",
        "maintenance_event", "maintenance_segment", "days_since_last_inspection", "hours_since_last_inspection",
        "days_since_last_repair", "hours_since_last_repair", "inspections_since_last_repair", "maintenance_action", "maintenance_priority",
        "maintenance_mode", "decision_reason", "is_first_post_repair_inspection", "fila_excel_origen"]
    features = features.rename(columns={"Inspector":"inspector", "Descripción":"description", "Equipo":"equipment", "Zona":"zone"})
    feature_columns = ["date", "hours", "equipment", "zone", "inspector", "point", "description", "L_raw_mm", "caution_mm", "danger_mm",
        "structural_state", "severity_ratio", "caution_utilization", "margin_to_caution_mm", "margin_to_danger_mm", "margin_to_caution_pct", "margin_to_danger_pct",
        "delta_L_raw", "delta_L_effective", "change_class", "delta_L_bridged_raw", "bridged_change_class",
        "bridged_from_date", "bridged_from_hours", "bridged_elapsed_days", "bridged_elapsed_hours", "bridge_null_count",
        "gap_spanning_change", "data_warning", "raw_growth_rate_mm_1000h", "effective_growth_rate_mm_1000h",
        "maintenance_event", "maintenance_segment", "days_since_last_inspection", "hours_since_last_inspection",
        "days_since_last_repair", "hours_since_last_repair", "inspections_since_last_repair", "maintenance_action", "maintenance_priority",
        "maintenance_mode", "decision_reason", "is_first_post_repair_inspection", "is_initial_measure", "fila_excel_origen"]
    features_out = features[feature_columns].copy()
    zone_out = zone[["date", "hours", "zone_state", "worst_point", "max_severity_ratio", "normal_count", "alert_count", "critical_count", "not_inspected_count",
                     "significant_growth_count", "highest_priority", "recommended_action", "maintenance_event", "data_completeness_pct", "priority_tie", "priority_tie_note"]].copy()
    write_csv(features_out, OUT / "maintenance_features.csv")
    write_csv(zone_out, OUT / "zone_snapshot.csv")
    bridge_df = pd.DataFrame(bridge_rows, columns=["point", "from_date", "to_date", "from_hours", "to_hours", "from_L_raw_mm", "to_L_raw_mm",
        "delta_L_bridged_raw", "elapsed_days", "elapsed_hours", "null_observations_spanned", "warning", "rate_calculated", "source_row_from", "source_row_to"])
    write_csv(bridge_df, OUT / "gap_spanning_changes.csv")

    # Deterministic assertions with explicit PASS/WARNING/FAIL output.
    tests = []
    def check(name: str, condition: bool, detail: str) -> None:
        tests.append({"test":name, "status":"PASS" if condition else "FAIL", "detail":detail})
    raw_compare = features[["date", "point", "L_raw_mm"]].merge(
        inspections.assign(point=inspections["Código"], date=inspections["Fecha"])[["date", "point", "L actual (mm)"]],
        on=["date", "point"], how="outer", validate="one_to_one")
    source_l = pd.to_numeric(raw_compare["L actual (mm)"], errors="coerce")
    raw_same = (raw_compare["L_raw_mm"].isna().eq(source_l.isna()).all()
        and np.allclose(raw_compare["L_raw_mm"].fillna(-999999), source_l.fillna(-999999)))
    check("l_raw_unchanged", bool(raw_same), "L_raw_mm coincide por fecha y punto con los valores QA; sin transformaciones")
    check("null_not_zero", int(features["L_raw_mm"].isna().sum()) == int(inspections["L actual (mm)"].isna().sum()) and not ((features["L_raw_mm"].isna()) & features["L_raw_mm"].eq(0)).any(), "NULL preservados; no imputados a 0")
    qa_limits = qa_summary["points"]
    check("official_limits_unchanged", all(features.loc[features.point.eq(p), "caution_mm"].eq(qa_limits[p]["caution_mm"]).all() and features.loc[features.point.eq(p), "danger_mm"].eq(qa_limits[p]["danger_mm"]).all() for p in POINTS), "Caution/Danger coinciden exactamente con qa_summary.json")
    expected_structural = features.apply(lambda r: "N/I" if pd.isna(r.L_raw_mm) else "Normal" if r.L_raw_mm < r.caution_mm else "Alerta" if r.L_raw_mm < r.danger_mm else "Crítico", axis=1)
    check("structural_state_unchanged", features["structural_state"].eq(expected_structural).all(), "Estado recomputado desde L_raw_mm y límites oficiales")
    check("severity_ratio_formula", np.allclose(features["severity_ratio"].fillna(-999), (features["L_raw_mm"] / features["danger_mm"]).fillna(-999)), "severity_ratio = L_raw / Danger")
    margin_ok = np.allclose(features["margin_to_caution_mm"].fillna(-999), (features["caution_mm"] - features["L_raw_mm"]).fillna(-999)) and np.allclose(features["margin_to_danger_mm"].fillna(-999), (features["danger_mm"] - features["L_raw_mm"]).fillna(-999))
    pct_ok = np.allclose(features["margin_to_caution_pct"].fillna(-999), ((features["caution_mm"]-features["L_raw_mm"])/features["caution_mm"]*100).fillna(-999)) and np.allclose(features["margin_to_danger_pct"].fillna(-999), ((features["danger_mm"]-features["L_raw_mm"])/features["danger_mm"]*100).fillna(-999))
    check("margin_equations", bool(margin_ok and pct_ok), "Márgenes absolutos y porcentuales recalculados sin recortar negativos")
    reset_rows = features[features.change_class.eq("MAINTENANCE_RESET")]
    check("no_trend_crosses_repair", reset_rows["raw_growth_rate_mm_1000h"].isna().all() and reset_rows["effective_growth_rate_mm_1000h"].isna().all(), "Tasas RAW y efectivas NaN en intervalos de reinicio")
    segment_ok = all(int(features.loc[features.date.eq(d), "maintenance_segment"].max()) == i+1 for i,d in enumerate(repair_dates)) and features["maintenance_segment"].is_monotonic_increasing
    check("maintenance_segments_coherent", bool(segment_ok), f"Fechas de reparación: {[pd.Timestamp(x).strftime('%Y-%m-%d') for x in repair_dates]}")
    critical = features[features.structural_state.eq("Crítico")]
    check("critical_is_p4", critical["maintenance_priority"].eq("P4").all(), f"Críticos={len(critical)}")
    check("critical_repair_before_operation", critical["maintenance_action"].eq("REPAIR_BEFORE_OPERATION").all(), f"Críticos={len(critical)}")
    ni = features[features.structural_state.eq("N/I")]
    check("ni_reinspection", ni["maintenance_action"].eq("REINSPECTION_REQUIRED").all(), f"N/I={len(ni)}")
    check("priority_at_most_p4", features["maintenance_priority"].dropna().isin(PRIORITY_ORDER).all(), "Prioridades pertenecen a P0...P4")
    expected_zone_priority = features.groupby("date")["maintenance_priority_rank"].max().map({v:k for k,v in PRIORITY_ORDER.items()})
    priority_matches=[]
    for _, snapshot in zone_out.iterrows():
        expected_priority = expected_zone_priority.loc[snapshot["date"]]
        actual_priority = snapshot["highest_priority"]
        priority_matches.append((pd.isna(expected_priority) and pd.isna(actual_priority)) or expected_priority == actual_priority)
    max_priority = bool(all(priority_matches))
    check("zone_priority_is_point_max", bool(max_priority), "Prioridad de zona igual a prioridad máxima de sus puntos")
    worst_exists = all(((features.date.eq(r.date)) & features.point.eq(r.worst_point)).any() for r in zone_out.itertuples())
    check("worst_point_exists", bool(worst_exists), "Cada worst_point existe en la inspección correspondiente")
    check("zone_completeness_range", zone_out["data_completeness_pct"].between(0,100).all(), "Completitud entre 0 y 100 %")
    raw_source_path=ROOT / qa_summary["source_file"]
    source_hash_matches=raw_source_path.exists() and hashlib.sha256(raw_source_path.read_bytes()).hexdigest()==qa_summary["source_sha256"]
    check("raw_source_hash_unchanged", bool(source_hash_matches), "SHA-256 del Excel RAW coincide con el snapshot del QA")
    delta_compare=deltas.merge(growth[["fecha","codigo","delta_L_raw","delta_L_effective","change_class"]],on=["fecha","codigo"],suffixes=("_delta","_growth"),validate="one_to_one")
    source_change_consistent=(delta_compare["change_class_delta"].eq(delta_compare["change_class_growth"]).all()
        and delta_compare["delta_L_raw_delta"].isna().eq(delta_compare["delta_L_raw_growth"].isna()).all()
        and np.allclose(delta_compare["delta_L_raw_delta"].fillna(-999),delta_compare["delta_L_raw_growth"].fillna(-999))
        and np.allclose(delta_compare["delta_L_effective_delta"].fillna(-999),delta_compare["delta_L_effective_growth"].fillna(-999)))
    check("delta_growth_qa_sources_agree", bool(source_change_consistent), "sd_delta_L.csv y sd_growth_rates.csv coinciden por fecha y punto")
    check("initial_measure_labeled", features.loc[features["is_initial_measure"], "maintenance_action"].eq("INITIAL_MEASURE").all()
          and int(features["is_initial_measure"].sum()) == len(POINTS), "Una primera medición válida por punto se identifica INITIAL_MEASURE")
    check("bridged_changes_are_flagged", features.loc[features["gap_spanning_change"], "data_warning"].eq("GAP_SPANNING_CHANGE").all()
          and features.loc[features["gap_spanning_change"], "delta_L_bridged_raw"].notna().all(), "Todo cambio a través de NULL queda separado y advertido")
    check("bridges_do_not_replace_consecutive_delta", features.loc[features["gap_spanning_change"], "delta_L_raw"].isna().all()
          and features.loc[features["gap_spanning_change"], "change_class"].eq("N_I").all(), "El cambio puenteado no reemplaza ΔL ni su clase consecutiva")
    check("bridged_changes_have_no_growth_rate", not any("bridged_growth_rate" in c for c in features.columns)
          and (bridge_df.empty or not bridge_df["rate_calculated"].any()), "No se calcula tasa ordinaria para cambios puenteados")
    check("current_nulls_warned", features.loc[features["L_raw_mm"].isna(), "data_warning"].eq("CURRENT_MEASUREMENT_NULL").all(), "NULL actuales conservan advertencia propia y acción de reinspección")
    check("no_target_normal_n_i_undefined", not ((features["structural_state"].eq("Normal"))
          & features["change_class"].eq("N_I") & features["maintenance_action"].eq("RULE_NOT_DEFINED")).any(),
          "Inicio de serie y observaciones posteriores a NULL tienen tratamiento explícito")
    tests_df = pd.DataFrame(tests)
    write_csv(tests_df, OUT / "maintenance_tests.csv")

    # Validation plots. Lines retain NaNs; no interpolation or smoothing is applied.
    plt.rcParams.update({"figure.figsize":(11,5.5), "font.size":9, "axes.grid":True, "grid.alpha":.25})
    point_colors = dict(zip(POINTS,["#1f77b4","#ff7f0e","#2ca02c","#9467bd"]))
    def finish(ax: Any, title: str, xlabel: str, ylabel: str, date_axis: bool=True) -> None:
        ax.set_title(title); ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.grid(True,alpha=.25)
        if date_axis:
            loc=mdates.AutoDateLocator(minticks=5,maxticks=10); ax.xaxis.set_major_locator(loc); ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
        ax.legend(loc="best",fontsize=8,ncol=1); plt.tight_layout()
    event_dates=pd.to_datetime(repairs["Fecha"].dropna().unique())
    def mark_repairs(ax: Any) -> None:
        for i,d in enumerate(event_dates): ax.axvline(d,color="#b22222",linestyle="--",linewidth=1.3,label="Reparación documentada" if i==0 else None)

    # A: state timeline, one raw symbol per inspection-point including N/I.
    fig,ax=plt.subplots(figsize=(12,5.5))
    ymap={p:i for i,p in enumerate(POINTS)}
    for p in POINTS:
        g=features[features.point.eq(p)]
        for state,color in STATE_COLORS.items():
            z=g[g.structural_state.eq(state)]
            if len(z):
                marker = "x" if state == "N/I" else "o"
                ax.scatter(z.date,[ymap[p]]*len(z),c=color,edgecolors=None if marker=="x" else "#333333",s=65,marker=marker,label=f"{p} · {state}")
    ax.set_yticks(list(ymap.values())); ax.set_yticklabels(POINTS); mark_repairs(ax); finish(ax,"State timeline por punto","Fecha","Punto"); fig.savefig(PLOTS/"01_state_timeline.png",dpi=200); plt.close(fig)
    # B: severity ratio, with limits-derived caution ratios.
    fig,ax=plt.subplots()
    for p in POINTS:
        g=features[features.point.eq(p)].sort_values("date")
        ax.plot(g.date,g.severity_ratio,color=point_colors[p],marker="o",label=f"{p}; Caution/Danger={qa_summary['points'][p]['caution_ratio']:.2f}")
    ax.axhline(1,color="#b22222",linestyle="--",label="Danger ratio = 1"); mark_repairs(ax); finish(ax,"Severity ratio (L / Danger)","Fecha","Severity ratio"); fig.savefig(PLOTS/"02_severity_ratio.png",dpi=200); plt.close(fig)
    # C/D: margins, zero line means the corresponding official limit.
    for col,filename,title,ylabel in [("margin_to_caution_mm","03_margin_to_caution.png","Margen a Caution","Caution − L (mm)"),("margin_to_danger_mm","04_margin_to_danger.png","Margen a Danger","Danger − L (mm)")]:
        fig,ax=plt.subplots()
        for p in POINTS:
            g=features[features.point.eq(p)].sort_values("date"); ax.plot(g.date,g[col],color=point_colors[p],marker="o",label=p)
        ax.axhline(0,color="#222222",linestyle="--",label="Límite = 0"); mark_repairs(ax); finish(ax,title,"Fecha",ylabel); fig.savefig(PLOTS/filename,dpi=200); plt.close(fig)
    # E/F: actions and priorities by point over time.
    action_names=sorted(features["maintenance_action"].dropna().unique())
    action_map={v:i for i,v in enumerate(action_names)}
    fig,ax=plt.subplots(figsize=(12,6))
    action_markers = dict(zip(POINTS, ["o", "s", "^", "D"]))
    plot_y = features["maintenance_action"].map(action_map).astype(float)
    for (_, _), same_action in features.groupby(["date", "maintenance_action"], sort=False):
        if len(same_action) > 1:
            offsets = np.linspace(-.22, .22, len(same_action))
            for (row_idx, row), offset in zip(same_action.iterrows(), offsets):
                y_plot = action_map[row["maintenance_action"]] + float(offset)
                plot_y.loc[row_idx] = y_plot
                ax.plot([row["date"], row["date"]], [action_map[row["maintenance_action"]], y_plot],
                        color=point_colors[row["point"]], alpha=.65, linewidth=.8, zorder=1)
    for p in POINTS:
        g=features[features.point.eq(p)]
        ax.scatter(g["date"],plot_y.loc[g.index],c=[point_colors[p]]*len(g),
                   marker=action_markers[p],edgecolors="#222222",linewidths=.55,s=54,label=p,zorder=3)
    bridge_warnings=features[features["gap_spanning_change"]]
    if len(bridge_warnings):
        ax.scatter(bridge_warnings["date"],plot_y.loc[bridge_warnings.index],marker="D",facecolors="none",
                   edgecolors="#d98e04",linewidths=1.8,s=125,label="Cambio puenteado con advertencia",zorder=4)
    for i,d in enumerate(event_dates):
        details=repairs.loc[pd.to_datetime(repairs["Fecha"]).eq(pd.Timestamp(d))]
        event_text=str(details["Comentario"].dropna().iloc[0]) if len(details) and details["Comentario"].notna().any() else "Mantenimiento documentado"
        event_label=f"Reparación general documentada · {pd.Timestamp(d):%Y-%m-%d}" if "general" in event_text.casefold() else f"Mantenimiento documentado · {pd.Timestamp(d):%Y-%m-%d}"
        ax.axvline(d,color="#c62828",linestyle="--",linewidth=2.2,label=event_label if i==0 else None,zorder=2)
    ax.set_yticks(list(action_map.values())); ax.set_yticklabels(action_names)
    ax.text(.01,.01,"Marcadores coincidentes separados verticalmente solo para legibilidad; fechas RAW conservadas en CSV.",
            transform=ax.transAxes,fontsize=8,color="#444444",va="bottom")
    finish(ax,"Maintenance action timeline","Fecha","Acción determinística"); fig.savefig(PLOTS/"05_maintenance_action_timeline.png",dpi=200); plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5.5))
    for p in POINTS:
        g=features[features.point.eq(p)]; ax.scatter(g.date,g.maintenance_priority_rank,c=[point_colors[p]]*len(g),s=50,label=p)
    ax.set_yticks(range(5)); ax.set_yticklabels([f"P{i}" for i in range(5)]); mark_repairs(ax); finish(ax,"Priority timeline","Fecha","Prioridad"); fig.savefig(PLOTS/"06_priority_timeline.png",dpi=200); plt.close(fig)
    # G: zone snapshot state.
    fig,ax=plt.subplots(figsize=(12,4.5))
    zmap={s:i for i,s in enumerate(["NORMAL","INCOMPLETE","ALERT","CRITICAL","UNKNOWN"])}
    for state,color in ZONE_COLORS.items():
        g=zone[zone.zone_state.eq(state)]
        if len(g): ax.scatter(g.date,[zmap[state]]*len(g),c=color,s=70,label=state)
    ax.set_yticks(list(zmap.values())); ax.set_yticklabels(list(zmap.keys())); mark_repairs(ax); finish(ax,"Zone state · Tijeras y spindle","Fecha","Estado de zona"); fig.savefig(PLOTS/"07_zone_state_timeline.png",dpi=200); plt.close(fig)
    # H: chronological repair segments as background blocks and event lines.
    fig,ax=plt.subplots(figsize=(12,4.5))
    unique_dates=sorted(pd.to_datetime(features["date"].unique()))
    seg_dates=features.groupby("date")["maintenance_segment"].first().reindex(unique_dates)
    start=0
    seg_colors=["#dce6f1","#e2f0d9","#fce4d6","#eadcf8"]
    for i in range(1,len(unique_dates)+1):
        if i==len(unique_dates) or seg_dates.iloc[i]!=seg_dates.iloc[start]:
            left=unique_dates[start]; right=unique_dates[i] if i<len(unique_dates) else unique_dates[-1]+pd.Timedelta(days=1)
            ax.axvspan(left,right,color=seg_colors[int(seg_dates.iloc[start])%len(seg_colors)],alpha=.6,label=f"Segmento {int(seg_dates.iloc[start])}" if start==0 or seg_dates.iloc[start]!=seg_dates.iloc[start-1] else None)
            start=i
    for p in POINTS:
        g=features[features.point.eq(p)]; ax.scatter(g.date,[ymap[p]]*len(g),c=[point_colors[p]]*len(g),s=28,label=p)
    ax.set_yticks(list(ymap.values())); ax.set_yticklabels(POINTS); mark_repairs(ax); finish(ax,"Segmentos de mantenimiento","Fecha","Punto"); fig.savefig(PLOTS/"08_maintenance_segments.png",dpi=200); plt.close(fig)

    # Transition and distribution summaries for the JSON/HTML report.
    transitions=[]
    for i in range(1,len(zone)):
        if zone.loc[i,"zone_state"] != zone.loc[i-1,"zone_state"]:
            g=features[features.date.eq(zone.loc[i,"date"])]
            prev_g=features[features.date.eq(zone.loc[i-1,"date"])].set_index("point")
            curr_g=g.set_index("point")
            changed_points=[p for p in POINTS if prev_g.loc[p,"structural_state"] != curr_g.loc[p,"structural_state"]]
            if bool(zone.loc[i,"maintenance_event"]):
                changed_points=sorted(set(changed_points) | set(g.loc[g["maintenance_event"],"point"]))
            if zone.loc[i,"zone_state"] in ("ALERT","CRITICAL"):
                responsible=g.loc[g.structural_state.isin(["Crítico","Alerta"]),"point"].tolist()
            else:
                responsible=changed_points
            transitions.append({"date":zone.loc[i,"date"],"from":zone.loc[i-1,"zone_state"],"to":zone.loc[i,"zone_state"],
                "responsible_points":responsible,"worst_point":zone.loc[i,"worst_point"]})
    action_counts=features["maintenance_action"].value_counts(dropna=False).to_dict()
    priority_counts={f"P{i}":int(features["maintenance_priority"].eq(f"P{i}").sum()) for i in range(5)}
    state_counts={s:int(features["structural_state"].eq(s).sum()) for s in ["Normal","Alerta","Crítico","N/I"]}
    decision_gaps=features[features.maintenance_action.eq("RULE_NOT_DEFINED")][["date","point","structural_state","change_class","decision_reason"]]
    gap_warning_rows=features.loc[features["gap_spanning_change"], ["date","point","bridged_from_date","delta_L_raw","delta_L_bridged_raw","bridge_null_count","data_warning"]]
    gap_summary_records=gap_warning_rows.astype(object).where(pd.notna(gap_warning_rows), None).to_dict(orient="records")
    summary={"source_files":["sd_inspections_qa.csv","sd_delta_L.csv","sd_growth_rates.csv","qa_maintenance_events.csv","qa_summary.json"],
        "scope":{"equipment":"EH4-01","zone":"Tijeras y spindle (suspensión delantera)","points":POINTS},
        "feature_rows":int(len(features)),"inspection_dates":int(features.date.nunique()),"structural_state_counts":state_counts,
        "initial_measure_count":int(features["is_initial_measure"].sum()),"gap_spanning_change_count":int(features["gap_spanning_change"].sum()),
        "gap_spanning_changes":gap_summary_records,
        "maintenance_action_counts":{str(k):int(v) for k,v in action_counts.items()},"maintenance_priority_counts":priority_counts,
        "zone_state_counts":{str(k):int(v) for k,v in zone.zone_state.value_counts().items()},"zone_state_transitions":transitions,
        "priority_action_dates":features[features.maintenance_priority.isin(["P2","P3","P4"])].groupby(["date","maintenance_priority","maintenance_action"])["point"].apply(list).reset_index().to_dict(orient="records"),
        "repair_dates":[pd.Timestamp(x) for x in repair_dates],"latest_condition":zone.iloc[-1].to_dict(),
        "decision_precedence":["Crítico/P4", "Alerta/P2-P3", "N/I/P1", "primera inspección post reparación/P1", "INITIAL_MEASURE sin prioridad", "Normal + reglas de cambio", "cambio puenteado mostrado con advertencia sin escalar prioridad"],
        "explicit_rule_gaps":{"post_repair_priority_and_mode":"No definidos por la solicitud; se asignó P1/INSPECTION para que la verificación obligatoria sea programable.",
          "normal_significant_decrease":"No definida por reglas V1; RULE_NOT_DEFINED se conserva para combinaciones aún no cubiertas.",
          "gap_spanning_change":"Se muestra el cambio entre última medición válida pre-NULL y primera post-NULL con GAP_SPANNING_CHANGE. No sustituye delta_L_raw, no calcula tasa y no modifica prioridad.",
          "initial_measure":"Primera medición válida por punto, etiquetada INITIAL_MEASURE sin delta ni prioridad asignada.",
          "zone_incomplete":"Se usa INCOMPLETE cuando hay al menos un N/I y los puntos medidos no tienen Alerta/Crítico; así N/I nunca hace que la zona aparezca NORMAL.",
          "zone_tie":"Entre puntos con prioridad máxima se selecciona mayor severity_ratio; empate residual por código ascendente."},
        "decision_gaps":decision_gaps.to_dict(orient="records"),"tests_pass":int(tests_df.status.eq("PASS").sum()),"tests_fail":int(tests_df.status.eq("FAIL").sum())}
    (OUT/"maintenance_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=safe_json),encoding="utf-8")

    # Generate a self-contained HTML report with complete tables and all charts.
    plot_files=sorted(PLOTS.glob("*.png"))
    transitions_html=pd.DataFrame(transitions).to_html(index=False,escape=True) if transitions else "<p>Sin cambios de estado de zona.</p>"
    decisions_html=decision_gaps.to_html(index=False,escape=True) if len(decision_gaps) else "<p>Sin combinaciones fuera de regla en este histórico.</p>"
    report=f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><title>EH4000 Maintenance Features</title>
    <style>body{{font:15px Arial,sans-serif;max-width:1250px;margin:2rem auto;padding:0 1rem;color:#222}}h1,h2{{color:#18324b}}table{{border-collapse:collapse;width:100%;font-size:12px;margin:1rem 0}}td,th{{border:1px solid #ccc;padding:5px}}th{{background:#eef2f5}}.plots{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}figure{{margin:0;border:1px solid #ddd;padding:.5rem}}img{{width:100%}}figcaption{{font-size:12px}}</style></head><body>
    <h1>Features de mantenimiento · EH4000</h1><p>EH4-01 · Tijeras y spindle · 4 puntos · {len(features)} filas y {features.date.nunique()} fechas. Solo consume outputs validados de QA; no modifica RAW.</p>
    <h2>Definición de variables</h2><p>severity_ratio=L_raw/Danger; caution_utilization=L_raw/Caution. Márgenes: umbral−L_raw, en mm y como porcentaje del umbral. No se recortan márgenes negativos. Los NULL producen N/I/NaN.</p><p>Los deltas y las tasas proceden de QA y respetan la tolerancia de 10 mm únicamente para análisis de cambio; Caution, Danger y structural_state se mantienen desde QA.</p>
    <h2>Reglas de decisión y precedencia</h2><ol><li>Crítico: REPAIR_BEFORE_OPERATION/P4.</li><li>Alerta: PRIORITIZE_REPAIR/P3 con crecimiento significativo; si no, PLAN_REPAIR/P2.</li><li>N/I: REINSPECTION_REQUIRED/P1.</li><li>Primera inspección post reparación: POST_REPAIR_VERIFICATION/P1/INSPECTION, salvo Alerta/Crítico; N/I conserva reinspección obligatoria.</li><li>Primera medición válida: INITIAL_MEASURE, sin ΔL ni prioridad.</li><li>Normal estable: MONITOR_ROUTINE/P0; Normal con crecimiento significativo consecutivo: MONITOR_INTENSIFIED/P1.</li><li>Normal después de NULL: estado estructural desde medición actual; cambio puenteado visible con advertencia, sin escalar prioridad.</li></ol>
    <p>La solicitud no especifica prioridad/modo para POST_REPAIR_VERIFICATION: se asigna explícitamente P1/INSPECTION como mapeo operativo conservador. N/I tiene precedencia sobre verificación post reparación para mantener REINSPECTION_REQUIRED.</p>
    <h2>Estadísticas</h2><p>Estados: {state_counts}. Acciones: {summary['maintenance_action_counts']}. Prioridades: {priority_counts}. Segmentos reparados: {len(repair_dates)}.</p>
    <h2>Cambios de estado de zona</h2>{transitions_html}<p>INCOMPLETE representa mezcla de mediciones normales y N/I; UNKNOWN significa que los cuatro puntos son N/I. CRITICAL domina ALERT, y ALERT domina estados incompletos/normales.</p>
    <h2>Fechas con acción P2/P3/P4</h2>{pd.DataFrame(summary['priority_action_dates']).to_html(index=False,escape=True) if summary['priority_action_dates'] else '<p>Ninguna.</p>'}
    <h2>Reparación y segmentos</h2><p>Fechas de reparación: {[pd.Timestamp(x).strftime('%Y-%m-%d') for x in repair_dates]}. El segmento aumenta automáticamente una vez por fecha de evento. La inspección del evento o la primera posterior ancla el segmento; no se mezclan tasas a través del reset.</p>
    <h2>Snapshot de zona</h2>{zone_out.to_html(index=False,escape=True)}
    <h2>Cambios puenteados con advertencia</h2>{gap_warning_rows.to_html(index=False,escape=True) if len(gap_warning_rows) else '<p>No hay cambios puenteados.</p>'}<p>El cambio puenteado no sustituye ΔL entre inspecciones consecutivas y no se convierte en tasa.</p>
    <h2>Combinaciones sin regla</h2>{decisions_html}
    <h2>Validaciones automatizadas</h2>{tests_df.to_html(index=False,escape=True)}
    <h2>Timeline completo de features</h2>{features_out.to_html(index=False,escape=True)}
    <h2>Gráficas</h2><div class='plots'>{''.join(f"<figure><img src='plots/{p.name}' alt='{p.stem}'><figcaption>{p.name}</figcaption></figure>" for p in plot_files)}</div>
    <h2>Última condición conocida</h2><p>Fecha {pd.Timestamp(zone.iloc[-1]['date']):%Y-%m-%d}: zona {zone.iloc[-1]['zone_state']}; prioridad {zone.iloc[-1]['highest_priority']}; acción {zone.iloc[-1]['recommended_action']}; completitud {zone.iloc[-1]['data_completeness_pct']:.1f}%.</p>
    </body></html>"""
    (OUT/"MAINTENANCE_FEATURE_REPORT.html").write_text(report,encoding="utf-8")

    # Re-read every tabular/JSON deliverable and validate formulas, decisions, and plot inventory.
    reread_features=pd.read_csv(OUT/"maintenance_features.csv")
    reread_zone=pd.read_csv(OUT/"zone_snapshot.csv")
    reread_tests=pd.read_csv(OUT/"maintenance_tests.csv")
    reread_bridges=pd.read_csv(OUT/"gap_spanning_changes.csv")
    reread_summary=json.loads((OUT/"maintenance_summary.json").read_text(encoding="utf-8"))
    expected_plots=["01_state_timeline.png","02_severity_ratio.png","03_margin_to_caution.png","04_margin_to_danger.png","05_maintenance_action_timeline.png","06_priority_timeline.png","07_zone_state_timeline.png","08_maintenance_segments.png"]
    missing_plots=[n for n in expected_plots if not (PLOTS/n).exists()]
    final_checks={"feature_count_matches":len(reread_features)==len(features),"zone_dates_match":len(reread_zone)==len(zone),
        "tests_csv_all_pass":reread_tests.status.eq("PASS").all(),"summary_feature_count_matches":reread_summary["feature_rows"]==len(features),
        "all_eight_plots_exist":not missing_plots,"report_exists":(OUT/"MAINTENANCE_FEATURE_REPORT.html").exists(),
        "raw_null_count_preserved":int(reread_features["L_raw_mm"].isna().sum())==int(features["L_raw_mm"].isna().sum()),
        "bridge_count_matches":len(reread_bridges)==len(bridge_df)==int(reread_summary["gap_spanning_change_count"]),
        "initial_measure_count_matches":int(reread_features["is_initial_measure"].sum())==int(reread_summary["initial_measure_count"]),
        "no_normal_n_i_rule_gaps":not ((reread_features.structural_state.eq("Normal")) & reread_features.change_class.eq("N_I") & reread_features.maintenance_action.eq("RULE_NOT_DEFINED")).any(),
        "structural_state_counts_match":reread_features.structural_state.value_counts().to_dict()==features.structural_state.value_counts().to_dict(),
        "all_critical_actions_valid":reread_features.loc[reread_features.structural_state.eq("Crítico"),"maintenance_action"].eq("REPAIR_BEFORE_OPERATION").all(),
        "all_critical_priorities_p4":reread_features.loc[reread_features.structural_state.eq("Crítico"),"maintenance_priority"].eq("P4").all(),
        "no_rates_at_maintenance_reset":reread_features.loc[reread_features.change_class.eq("MAINTENANCE_RESET"),["raw_growth_rate_mm_1000h","effective_growth_rate_mm_1000h"]].isna().all().all(),
        "zone_priority_max_matches":bool(max_priority),"no_raw_source_modified":bool(source_hash_matches)}
    (OUT/"maintenance_validation.json").write_text(json.dumps({"checks":final_checks,"missing_plots":missing_plots},ensure_ascii=False,indent=2,default=safe_json),encoding="utf-8")
    if not all(final_checks.values()) or tests_df.status.ne("PASS").any():
        raise RuntimeError(f"Validación falló: {final_checks}; tests={tests_df.to_dict(orient='records')}")
    # Escape non-ASCII in console output for Windows terminals using cp1252;
    # generated UTF-8 JSON/HTML files retain their readable Spanish text.
    print(json.dumps({"status":"COMPLETED","summary":summary,"tests":tests_df.to_dict(orient="records"),"validation":final_checks,"output":str(OUT)},ensure_ascii=True,indent=2,default=safe_json))


if __name__ == "__main__": main()
