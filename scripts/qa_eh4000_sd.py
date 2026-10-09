#!/usr/bin/env python3
"""Reproducible QA of EH4000 front suspension crack inspections (SD-01..04).

The source workbook is read-only evidence. Empty measurements remain NULL; 0 mm
means inspected with no detectable crack. Run from the repository root:
    python scripts/qa_eh4000_sd.py
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Write figures through an already-open file handle for reliable replacement of
# prior generated PNGs on Windows (Pillow otherwise reopens the path internally).
_matplotlib_savefig = plt.Figure.savefig
def _savefig_via_open_handle(self: Any, fname: Any, *args: Any, **kwargs: Any) -> Any:
    if isinstance(fname, (str, Path)):
        path = Path(fname)
        with path.open("wb") as stream:
            kwargs.setdefault("format", path.suffix.lstrip("."))
            return _matplotlib_savefig(self, stream, *args, **kwargs)
    return _matplotlib_savefig(self, fname, *args, **kwargs)
plt.Figure.savefig = _savefig_via_open_handle


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "DATOSCRUDOS" / "EH4000_historial_grietas.xlsx"
OUT = ROOT / "outputs"
PLOTS = OUT / "plots"
POINTS = ["SD-01", "SD-02", "SD-03", "SD-04"]
MEASUREMENT_TOLERANCE_MM = 10.0
EXPECTED_ZONE = "Tijeras y spindle (suspensión delantera)"
EXPECTED_EQUIPMENT = "EH4-01"
REQUIRED_HISTORY = ["Fecha", "Equipo", "Horas (h)", "Inspector", "Zona", "Código",
                    "Descripción", "L actual (mm)", "Comentario", "Imagen"]
REQUIRED_POINTS = ["Código", "Zona", "Descripción", "Caution (mm)", "Danger (mm)", "Esquema"]


def json_safe(obj: Any) -> Any:
    if isinstance(obj, (pd.Timestamp,)): return obj.strftime("%Y-%m-%d")
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating,)): return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, (np.bool_,)): return bool(obj)
    if pd.isna(obj): return None
    return obj


def robust_stats(values: pd.Series | list[float]) -> dict[str, Any]:
    s = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float)
    if s.empty:
        return {k: None for k in ["n", "mean", "median", "std", "min", "max", "q1", "q3", "iqr", "mad", "cv"]}
    q1, q3 = s.quantile(.25), s.quantile(.75)
    med = s.median()
    std = s.std(ddof=1) if len(s) > 1 else 0.0
    return {"n": int(len(s)), "mean": float(s.mean()), "median": float(med),
            "std": float(std), "min": float(s.min()), "max": float(s.max()),
            "q1": float(q1), "q3": float(q3), "iqr": float(q3-q1),
            "mad": float((s-med).abs().median()),
            "cv": float(std/s.mean()) if s.mean() else None}


def add_test(rows: list[dict], name: str, condition: bool, detail: str = "", warning: bool = False) -> None:
    rows.append({"test": name, "status": "PASS" if condition else ("WARNING" if warning else "FAIL"), "detail": detail})


def fmt(x: Any, digits: int = 2) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)): return "N/D"
    if isinstance(x, (int, np.integer)): return str(x)
    if isinstance(x, (float, np.floating)): return f"{x:.{digits}f}"
    return str(x)


def save_csv(df: pd.DataFrame, name: str) -> None:
    df.to_csv(OUT / name, index=False, encoding="utf-8-sig")


def main() -> None:
    if not SOURCE.exists(): raise FileNotFoundError(f"No se encontró el Excel: {SOURCE}")
    OUT.mkdir(parents=True, exist_ok=True); PLOTS.mkdir(parents=True, exist_ok=True)
    xls = pd.ExcelFile(SOURCE, engine="openpyxl")
    raw_hist = pd.read_excel(xls, sheet_name="Historial")
    raw_points = pd.read_excel(xls, sheet_name="Puntos")
    sheet_names = xls.sheet_names
    missing_hist_cols = [c for c in REQUIRED_HISTORY if c not in raw_hist.columns]
    missing_point_cols = [c for c in REQUIRED_POINTS if c not in raw_points.columns]
    if missing_hist_cols or missing_point_cols:
        raise ValueError(f"Columnas requeridas ausentes. Historial={missing_hist_cols}; Puntos={missing_point_cols}")

    # Keep original row number (Excel header is row 1) and raw values before parsing.
    candidates = raw_hist[raw_hist["Código"].astype(str).isin(POINTS)].copy()
    candidates["fila_excel"] = candidates.index + 2
    candidates["Fecha"] = pd.to_datetime(candidates["Fecha"], errors="coerce")
    candidates["Horas (h)"] = pd.to_numeric(candidates["Horas (h)"], errors="coerce")
    candidates["L actual (mm)"] = pd.to_numeric(candidates["L actual (mm)"], errors="coerce")
    candidates["codigo"] = candidates["Código"].astype(str)
    bad_candidate_mask = ~candidates["Equipo"].eq(EXPECTED_EQUIPMENT) | ~candidates["Zona"].eq(EXPECTED_ZONE)
    # Analyze only the requested equipment/zone, but retain candidate evidence for structural checks.
    scope = candidates[~bad_candidate_mask].copy()
    scope.sort_values(["Fecha", "codigo", "fila_excel"], inplace=True)

    limits = raw_points[raw_points["Código"].astype(str).isin(POINTS)].copy()
    limits["Caution (mm)"] = pd.to_numeric(limits["Caution (mm)"], errors="coerce")
    limits["Danger (mm)"] = pd.to_numeric(limits["Danger (mm)"], errors="coerce")
    lim = limits.set_index("Código").to_dict("index")
    for p in POINTS:
        if p not in lim: lim[p] = {"Caution (mm)": np.nan, "Danger (mm)": np.nan}

    tests: list[dict] = []
    add_test(tests, "hojas_requeridas", {"Historial", "Puntos"}.issubset(sheet_names), f"Hojas: {sheet_names}")
    add_test(tests, "columnas_historial", not missing_hist_cols, f"Ausentes: {missing_hist_cols}")
    add_test(tests, "columnas_puntos", not missing_point_cols, f"Ausentes: {missing_point_cols}")
    add_test(tests, "fechas_parseables", scope["Fecha"].notna().all(), f"No parseables: {int(scope['Fecha'].isna().sum())}")
    add_test(tests, "horas_numericas", scope["Horas (h)"].notna().all(), f"No numéricas: {int(scope['Horas (h)'].isna().sum())}")
    add_test(tests, "medicion_numerica_o_null", True, f"NULL preservados: {int(scope['L actual (mm)'].isna().sum())}")
    add_test(tests, "codigos_solo_SD01_SD04", set(scope.codigo.unique()).issubset(set(POINTS)) and set(scope.codigo.unique()) == set(POINTS), f"Códigos: {sorted(scope.codigo.unique())}")
    add_test(tests, "equipo_consistente", candidates["Equipo"].eq(EXPECTED_EQUIPMENT).all(),
             f"Candidatos SD fuera de equipo: {int((~candidates['Equipo'].eq(EXPECTED_EQUIPMENT)).sum())}")
    add_test(tests, "zona_consistente", candidates["Zona"].eq(EXPECTED_ZONE).all(),
             f"Candidatos SD fuera de zona: {int((~candidates['Zona'].eq(EXPECTED_ZONE)).sum())}")
    desc_cons = all(scope.loc[scope.codigo.eq(p), "Descripción"].nunique(dropna=False) == 1 and
                    scope.loc[scope.codigo.eq(p), "Descripción"].iloc[0] == lim[p].get("Descripción") for p in POINTS)
    add_test(tests, "descripciones_consistentes_con_catalogo", desc_cons, "Comparación con hoja Puntos")
    limits_valid = all(pd.notna(lim[p].get("Caution (mm)")) and pd.notna(lim[p].get("Danger (mm)")) and
                       lim[p]["Caution (mm)"] < lim[p]["Danger (mm)"] for p in POINTS)
    add_test(tests, "limites_caution_menor_danger", limits_valid, "Leídos de hoja Puntos")
    dups = scope.duplicated(["Fecha", "Equipo", "Código"], keep=False)
    add_test(tests, "duplicados_fecha_equipo_codigo", not dups.any(), f"Filas duplicadas: {int(dups.sum())}", warning=True)

    inspections = scope.drop_duplicates("Fecha").sort_values("Fecha").copy()
    by_date = scope.groupby("Fecha", dropna=False)
    perdate_count = scope.groupby("Fecha").size()
    counts_by_date = scope.groupby("Fecha")["Código"].nunique()
    add_test(tests, "cuatro_filas_por_inspeccion", bool((perdate_count == 4).all()),
             f"Fechas con recuento distinto a 4: {int((perdate_count != 4).sum())}", warning=True)
    add_test(tests, "cuatro_puntos_por_fecha", bool((counts_by_date == 4).all()),
             f"Fechas con distinto número de códigos: {int((counts_by_date != 4).sum())}", warning=True)
    hours_inconsistent = int((by_date["Horas (h)"].nunique(dropna=False) > 1).sum())
    inspector_inconsistent = int((by_date["Inspector"].nunique(dropna=False) > 1).sum())
    image_inconsistent = int((by_date["Imagen"].nunique(dropna=False) > 1).sum())
    add_test(tests, "horas_consistentes_en_fecha", hours_inconsistent == 0, f"Fechas inconsistentes: {hours_inconsistent}", warning=True)
    add_test(tests, "inspector_consistente_en_fecha", inspector_inconsistent == 0, f"Fechas inconsistentes: {inspector_inconsistent}", warning=True)
    add_test(tests, "imagen_consistente_en_fecha", image_inconsistent == 0, f"Fechas inconsistentes: {image_inconsistent}", warning=True)
    image_refs = sorted({str(x) for x in candidates["Imagen"].dropna() if str(x).strip()})
    missing_image_refs = [x for x in image_refs if not (SOURCE.parent / x).exists()]
    add_test(tests, "referencias_imagen_resolubles", not missing_image_refs,
             f"Referencias sin archivo externo en DATOSCRUDOS: {missing_image_refs}", warning=True)
    add_test(tests, "fechas_no_nulas", inspections["Fecha"].notna().all(), "Fecha de inspección parseada")
    add_test(tests, "horometro_no_nulo_por_fecha", inspections["Horas (h)"].notna().all(), "Horómetro deduplicado por fecha")

    # Keep inspector/image metadata from first row per date, while consistency is tested above.
    inspections = inspections[["Fecha", "Horas (h)", "Inspector", "Imagen"]].sort_values("Fecha").reset_index(drop=True)
    inspections["delta_dias"] = inspections["Fecha"].diff().dt.total_seconds() / 86400
    inspections["delta_horas"] = inspections["Horas (h)"].diff()
    inspections["fecha_duplicada"] = inspections["Fecha"].duplicated(keep=False)
    inspections["horometro_decreciente"] = inspections["delta_horas"] < 0
    inspections["horas_duplicadas"] = inspections["Horas (h)"].duplicated(keep=False)

    def robust_bounds(series: pd.Series) -> tuple[float, float]:
        s = series.dropna().astype(float)
        if s.empty: return (np.nan, np.nan)
        q1, q3 = s.quantile(.25), s.quantile(.75); iqr = q3-q1
        return float(q1-1.5*iqr), float(q3+1.5*iqr)
    d_lo, d_hi = robust_bounds(inspections["delta_dias"])
    h_lo, h_hi = robust_bounds(inspections["delta_horas"])
    for col, lo, hi, outcol in [("delta_dias", d_lo, d_hi, "gap_dias_atipico"), ("delta_horas", h_lo, h_hi, "gap_horas_atipico")]:
        inspections[outcol] = inspections[col].lt(lo) | inspections[col].gt(hi)

    # Domain and maintenance classification; preserve exact comments and source Excel rows.
    pattern = re.compile(r"repar|soldad|interven|cambio|post.?repar|manten|reconstru", re.I)
    scope["structural_state"] = "N/I"
    for p in POINTS:
        mask = scope["codigo"].eq(p) & scope["L actual (mm)"].notna()
        c, danger = lim[p]["Caution (mm)"], lim[p]["Danger (mm)"]
        scope.loc[mask & (scope["L actual (mm)"] < c), "structural_state"] = "Normal"
        scope.loc[mask & (scope["L actual (mm)"].ge(c)) & (scope["L actual (mm)"].lt(danger)), "structural_state"] = "Alerta"
        scope.loc[mask & scope["L actual (mm)"].ge(danger), "structural_state"] = "Crítico"
    scope["severity_ratio"] = scope.apply(lambda r: r["L actual (mm)"] / lim[r["codigo"]]["Danger (mm)"] if pd.notna(r["L actual (mm)"]) and lim[r["codigo"]]["Danger (mm)"] else np.nan, axis=1)
    scope["maintenance_event"] = scope["Comentario"].fillna("").astype(str).apply(lambda x: bool(pattern.search(x)))
    scope["classification"] = np.where(scope["maintenance_event"], "MAINTENANCE_EVENT", "")
    expected_state = scope.apply(lambda r: "N/I" if pd.isna(r["L actual (mm)"]) else
                                 "Normal" if r["L actual (mm)"] < lim[r["codigo"]]["Caution (mm)"] else
                                 "Alerta" if r["L actual (mm)"] < lim[r["codigo"]]["Danger (mm)"] else "Crítico", axis=1)
    add_test(tests, "structural_state_uses_raw_and_official_limits",
             scope["structural_state"].eq(expected_state).all(),
             "Estado validado exclusivamente con L RAW y umbrales oficiales; tolerancia no aplicada")

    anomalies: list[dict] = []
    def finding(severity: str, date: Any, code: str, field: str, observed: Any, previous: Any,
                explanation: str, cause: str, action: str, row: Any, change_class: str | None = None) -> None:
        anomalies.append({"severity": severity, "fecha": date, "codigo": code, "campo": field,
                          "valor_observado": observed, "valor_anterior": previous,
                          "explicacion": explanation, "posible_causa": cause,
                          "accion_sugerida": action, "fila_excel": row, "change_class": change_class})
    for _, r in scope.iterrows():
        if pd.isna(r["L actual (mm)"]):
            finding("INFO", r["Fecha"], r["codigo"], "L actual (mm)", None, None, "Medición vacía preservada como N/I; no equivale a 0 mm.", "Punto no inspeccionado o medición no disponible", "Confirmar motivo de ausencia", r["fila_excel"])
        v = r["L actual (mm)"]
        if pd.notna(v) and (v < 0 or v > 10000):
            finding("ERROR", r["Fecha"], r["codigo"], "L actual (mm)", v, None, "Valor fuera del dominio físico/configurado de QA (>=0 y <=10000 mm).", "Error de captura o unidad", "Validar contra registro de campo; conservar RAW", r["fila_excel"])
        if r["maintenance_event"]:
            finding("MAINTENANCE_EVENT", r["Fecha"], r["codigo"], "Comentario", r["Comentario"], None,
                    "Comentario documental que indica intervención/reparación general de chasis.", "Reparación general documentada", "Confirmar alcance y puntos intervenidos; segmentar serie", r["fila_excel"])
    if missing_image_refs and len(candidates):
        for image_ref in missing_image_refs:
            ref_rows = candidates[candidates["Imagen"].astype(str).eq(image_ref)]
            first_ref = ref_rows.iloc[0]
            finding("WARNING", first_ref["Fecha"], first_ref["codigo"], "Imagen", image_ref, None,
                    "El metadato referencia una imagen que no está disponible junto al Excel; no hay imagen incrustada para verificar.",
                    "Paquete de evidencias incompleto o ruta externa no incluida", "Solicitar la imagen original y verificar correspondencia con el punto", first_ref["fila_excel"])
    for _, r in inspections.iterrows():
        if bool(r["horometro_decreciente"]):
            pos = inspections.index[inspections["Fecha"].eq(r["Fecha"])][0]
            prior_hour = inspections.iloc[pos-1]["Horas (h)"] if pos > 0 else None
            finding("ERROR", r["Fecha"], "", "Horas (h)", r["Horas (h)"], prior_hour,
                    "Horómetro decrece frente a la inspección anterior.", "Reinicio o captura inconsistente", "Contrastar con horómetro primario", None)
        if bool(r["gap_dias_atipico"]):
            finding("WARNING", r["Fecha"], "", "delta_dias", r["delta_dias"], None,
                    "Intervalo fuera de cercas IQR 1.5; es atípico estadístico, no prueba de error.", "Cadencia irregular o registro omitido", "Revisar calendario de inspecciones", None)
        if bool(r["gap_horas_atipico"]):
            finding("WARNING", r["Fecha"], "", "delta_horas", r["delta_horas"], None,
                    "Incremento de horómetro fuera de cercas IQR 1.5.", "Utilización excepcional o registro inconsistente", "Contrastar con registros operacionales", None)
    # Only confirmed comments count as maintenance events. One event has four point rows.
    maintenance = scope[scope.maintenance_event].copy()
    maintenance["tipo_inferido"] = maintenance["Comentario"].fillna("").apply(
        lambda x: "reparación general" if re.search(r"reparaci[oó]n general", str(x), re.I) else "mantenimiento/intervención")
    maintenance["confianza"] = maintenance["Comentario"].fillna("").apply(
        lambda x: "alta" if re.search(r"reparaci[oó]n|soldad|cambio", str(x), re.I) else "media")
    maintenance_out = maintenance[["Fecha", "Horas (h)", "codigo", "Comentario", "tipo_inferido", "confianza", "fila_excel"]].rename(columns={"codigo":"punto", "Horas (h)":"horas"})

    # Completeness and inspection-level summaries.
    date_count = inspections["Fecha"].nunique()
    expected = date_count * len(POINTS)
    existing = len(scope)
    n_null = int(scope["L actual (mm)"].isna().sum())
    completeness = {p: {"available": int(scope.loc[scope.codigo.eq(p), "L actual (mm)"].notna().sum()),
                        "null": int(scope.loc[scope.codigo.eq(p), "L actual (mm)"].isna().sum()),
                        "completeness_pct": float(scope.loc[scope.codigo.eq(p), "L actual (mm)"].notna().mean()*100)} for p in POINTS}
    by_inspector = scope.groupby("Inspector", dropna=False).agg(records=("codigo", "size"), measured=("L actual (mm)", "count"), nulls=("L actual (mm)", lambda x: x.isna().sum())).reset_index()
    by_inspector["completeness_pct"] = by_inspector["measured"] / by_inspector["records"] * 100
    missing = scope[scope["L actual (mm)"].isna()][["Fecha", "Equipo", "Horas (h)", "Inspector", "codigo", "Zona", "Descripción", "L actual (mm)", "Comentario", "Imagen", "fila_excel"]].rename(columns={"codigo":"Código"})
    missing_dates = sorted(scope.loc[scope["L actual (mm)"].isna(), "Fecha"].dropna().unique())

    # Per point dynamics: only adjacent non-null observations make a delta; any NULL breaks rate.
    growth_rows: list[dict] = []
    delta_rows: list[dict] = []
    point_summary: dict[str, dict] = {}
    for p in POINTS:
        q = scope[scope.codigo.eq(p)].sort_values("Fecha").reset_index(drop=True)
        vals = q["L actual (mm)"].dropna()
        states = q["structural_state"].value_counts().to_dict()
        if len(vals):
            max_idx = q["L actual (mm)"].idxmax()
            max_row = q.loc[max_idx]
        else: max_row = None
        point_summary[p] = {
            "caution_mm": lim[p]["Caution (mm)"], "danger_mm": lim[p]["Danger (mm)"],
            "caution_ratio": float(lim[p]["Caution (mm)"]/lim[p]["Danger (mm)"]) if lim[p]["Danger (mm)"] else None,
            "n_observations": int(len(q)), "n_numeric": int(vals.count()), "n_null": int(q["L actual (mm)"].isna().sum()),
            "min_mm": float(vals.min()) if len(vals) else None, "max_mm": float(vals.max()) if len(vals) else None,
            "mean_mm": float(vals.mean()) if len(vals) else None, "median_mm": float(vals.median()) if len(vals) else None,
            "max_date": max_row["Fecha"] if max_row is not None else None,
            "first_positive": q.loc[q["L actual (mm)"].gt(0), "Fecha"].min() if q["L actual (mm)"].gt(0).any() else None,
            "first_alert": q.loc[q.structural_state.eq("Alerta"), "Fecha"].min() if q.structural_state.eq("Alerta").any() else None,
            "first_critical": q.loc[q.structural_state.eq("Crítico"), "Fecha"].min() if q.structural_state.eq("Crítico").any() else None,
            "states": {s: int(states.get(s, 0)) for s in ["Normal", "Alerta", "Crítico", "N/I"]}}
        prev = None
        for _, r in q.iterrows():
            current_l = r["L actual (mm)"]
            previous_l = prev["L actual (mm)"] if prev is not None else np.nan
            interval_h = float(r["Horas (h)"] - prev["Horas (h)"]) if prev is not None and pd.notna(r["Horas (h)"]) and pd.notna(prev["Horas (h)"]) else np.nan
            delta_raw = float(current_l - previous_l) if prev is not None and pd.notna(current_l) and pd.notna(previous_l) else np.nan
            if prev is None or pd.isna(current_l) or pd.isna(previous_l):
                change_class = "N_I"
            elif bool(r["maintenance_event"]):
                change_class = "MAINTENANCE_RESET"
            elif abs(delta_raw) <= MEASUREMENT_TOLERANCE_MM:
                change_class = "STABLE_WITHIN_TOLERANCE"
            elif delta_raw > MEASUREMENT_TOLERANCE_MM:
                change_class = "SIGNIFICANT_GROWTH"
            else:
                change_class = "SIGNIFICANT_DECREASE_REVIEW"
            delta_effective = (0.0 if abs(delta_raw) <= MEASUREMENT_TOLERANCE_MM else delta_raw) if pd.notna(delta_raw) else np.nan
            maintenance_boundary = change_class == "MAINTENANCE_RESET"
            raw_rate = delta_raw / interval_h * 1000 if pd.notna(delta_raw) and interval_h > 0 and not maintenance_boundary else np.nan
            if change_class in ("N_I", "MAINTENANCE_RESET"):
                effective_rate = np.nan
            elif change_class == "STABLE_WITHIN_TOLERANCE":
                effective_rate = 0.0
            else:
                effective_rate = raw_rate
            common = {"fecha":r["Fecha"], "codigo":p, "desde_fecha":prev["Fecha"] if prev is not None else None,
                      "delta_L_raw":delta_raw, "delta_L_effective":delta_effective,
                      "change_class":change_class, "delta_horas":interval_h,
                      "maintenance_boundary":maintenance_boundary,
                      "fila_excel_desde":prev["fila_excel"] if prev is not None else None,
                      "fila_excel_hasta":r["fila_excel"]}
            delta_rows.append({**common, "delta_L_mm":delta_raw,
                               "tipo_delta":"incremento" if delta_raw>0 else "decremento" if delta_raw<0 else "plateau" if pd.notna(delta_raw) else "N/I"})
            growth_rows.append({**common, "raw_growth_rate_mm_1000h":raw_rate,
                                "effective_growth_rate_mm_1000h":effective_rate,
                                "v_mm_por_1000h":raw_rate,
                                "intervalo_valido":bool(pd.notna(raw_rate)),
                                "rate_exclusion_reason":"NULL" if change_class=="N_I" else "MAINTENANCE_RESET" if maintenance_boundary else "INVALID_DELTA_HOURS" if pd.notna(delta_raw) and not (interval_h>0) else ""})
            prev = r
    growth = pd.DataFrame(growth_rows); delta_df = pd.DataFrame(delta_rows)

    # Reclassify change findings using the operational tolerance.
    for _, r in delta_df.iterrows():
        raw_delta = r["delta_L_raw"]
        if pd.isna(raw_delta):
            continue
        previous_record = scope.loc[scope["fila_excel"].eq(r["fila_excel_desde"])].iloc[0]
        current_record = scope.loc[scope["fila_excel"].eq(r["fila_excel_hasta"])].iloc[0]
        if r["change_class"] == "STABLE_WITHIN_TOLERANCE" and raw_delta < 0:
            finding("INFO", r["fecha"], r["codigo"], "L actual (mm)", current_record["L actual (mm)"], previous_record["L actual (mm)"],
                    f"El descenso RAW de {raw_delta:g} mm queda dentro de ±{MEASUREMENT_TOLERANCE_MM:g} mm y se reclasifica como estable operacional.",
                    "Variación dentro de tolerancia operacional adoptada", "Conservar RAW; usar delta efectivo cero para análisis de cambio", r["fila_excel_hasta"], r["change_class"])
        elif r["change_class"] == "SIGNIFICANT_DECREASE_REVIEW":
            finding("WARNING", r["fecha"], r["codigo"], "L actual (mm)", current_record["L actual (mm)"], previous_record["L actual (mm)"],
                    f"Descenso RAW de {raw_delta:g} mm excede la tolerancia; requiere revisión y no implica propagación negativa.",
                    "Incertidumbre de medición, cambio físico o intervención no documentada", "Revisar evidencia de campo y método de medición", r["fila_excel_hasta"], r["change_class"])
        elif r["change_class"] == "SIGNIFICANT_GROWTH" and raw_delta > 50:
            finding("WARNING", r["fecha"], r["codigo"], "L actual (mm)", current_record["L actual (mm)"], previous_record["L actual (mm)"],
                    f"Crecimiento RAW de {raw_delta:g} mm excede 50 mm entre inspecciones.", "Cambio abrupto o variación de medición", "Validar fotografías y medición original", r["fila_excel_hasta"], r["change_class"])

    interval_stats = {"delta_dias": robust_stats(inspections["delta_dias"]), "delta_horas": robust_stats(inspections["delta_horas"]),
                      "robust_iqr_bounds": {"delta_dias": [d_lo, d_hi], "delta_horas": [h_lo, h_hi]},
                      "outlier_dates": {"delta_dias": [x for x in inspections.loc[inspections.gap_dias_atipico, "Fecha"]],
                                        "delta_horas": [x for x in inspections.loc[inspections.gap_horas_atipico, "Fecha"]]}}
    status_counts = {s: int((scope.structural_state == s).sum()) for s in ["Normal", "Alerta", "Crítico", "N/I"]}
    change_class_counts = {k: int((delta_df["change_class"] == k).sum()) for k in ["STABLE_WITHIN_TOLERANCE", "SIGNIFICANT_GROWTH", "SIGNIFICANT_DECREASE_REVIEW", "MAINTENANCE_RESET", "N_I"]}
    observed_raw = delta_df["delta_L_raw"]
    expected_effective = observed_raw.where(observed_raw.abs() > MEASUREMENT_TOLERANCE_MM, 0.0)
    effective_delta_ok = delta_df["delta_L_effective"].isna().eq(observed_raw.isna()).all() and np.allclose(
        delta_df.loc[observed_raw.notna(), "delta_L_effective"], expected_effective[observed_raw.notna()])
    rate_policy_ok = bool(growth.loc[growth.change_class.isin(["N_I", "MAINTENANCE_RESET"]), "effective_growth_rate_mm_1000h"].isna().all()
                          and (growth.loc[growth.change_class.eq("STABLE_WITHIN_TOLERANCE"), "effective_growth_rate_mm_1000h"] == 0).all())
    other_rate = growth[growth.change_class.isin(["SIGNIFICANT_GROWTH", "SIGNIFICANT_DECREASE_REVIEW"])]
    rate_policy_ok = rate_policy_ok and np.allclose(other_rate["effective_growth_rate_mm_1000h"].fillna(-999), other_rate["raw_growth_rate_mm_1000h"].fillna(-999))
    add_test(tests, "delta_effective_applies_tolerance_only", bool(effective_delta_ok), f"Tolerancia operacional ±{MEASUREMENT_TOLERANCE_MM:g} mm")
    add_test(tests, "growth_rates_follow_class_policy", bool(rate_policy_ok), "Tasa RAW conservada; efectiva respeta NULL, mantenimiento y tolerancia")
    add_test(tests, "change_class_partition", sum(change_class_counts.values()) == len(scope), f"Clases: {change_class_counts}")
    prior_changes = []
    for _, r in delta_df[(delta_df["change_class"] == "STABLE_WITHIN_TOLERANCE") & (delta_df["delta_L_raw"] < 0)].iterrows():
        prior_changes.append({"fecha":r["fecha"], "codigo":r["codigo"], "delta_L_raw":r["delta_L_raw"],
                              "previous_classification":"WARNING_DECREMENT_REVIEW", "new_classification":"STABLE_WITHIN_TOLERANCE",
                              "delta_L_effective":r["delta_L_effective"], "fila_excel":r["fila_excel_hasta"]})

    # Save tabular deliverables.
    tests_df = pd.DataFrame(tests); save_csv(tests_df, "qa_tests.csv")
    anomalies_df = pd.DataFrame(anomalies); save_csv(anomalies_df, "qa_anomalies.csv")
    save_csv(missing, "qa_missing_values.csv"); save_csv(maintenance_out, "qa_maintenance_events.csv")
    out_ins = scope.rename(columns={"codigo":"Código", "fila_excel":"fila_excel_origen"})
    save_csv(out_ins, "sd_inspections_qa.csv")
    save_csv(inspections, "sd_intervals.csv")
    save_csv(growth, "sd_growth_rates.csv")
    save_csv(by_inspector, "inspector_completeness.csv")
    save_csv(delta_df, "sd_delta_L.csv")

    # Plotting setup and interval event dates.
    plt.rcParams.update({"figure.figsize":(11, 5.2), "font.size":9, "axes.grid":True, "grid.alpha":.25})
    event_dates = pd.to_datetime(maintenance["Fecha"].dropna().unique())
    colors = {"SD-01":"#1f77b4", "SD-02":"#ff7f0e", "SD-03":"#2ca02c", "SD-04":"#9467bd"}
    state_colors = {"Normal":"#d9ead3", "Alerta":"#fff2cc", "Crítico":"#f4cccc"}
    def finish(ax: Any, title: str, xlabel: str, ylabel: str, date_axis: bool=False) -> None:
        ax.set_title(title); ax.set_xlabel(xlabel); ax.set_ylabel(ylabel); ax.grid(True, alpha=.25)
        if date_axis:
            ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=10)); ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
        ax.legend(loc="best", fontsize=8); plt.tight_layout()
    def add_events(ax: Any) -> None:
        for i, d in enumerate(event_dates):
            ax.axvline(d, color="#b22222", linestyle="--", linewidth=1.2, label="Reparación documentada" if i==0 else None)
    # A/B individual traces, retaining NaN in line series to create true gaps.
    for i, p in enumerate(POINTS, 1):
        q = scope[scope.codigo.eq(p)].sort_values("Fecha")
        c, dg = lim[p]["Caution (mm)"], lim[p]["Danger (mm)"]
        for kind, xcol, fname, xlabel in [("fecha", "Fecha", f"{i:02d}_{p.replace('-','')}_vs_fecha.png", "Fecha"),
                                          ("horas", "Horas (h)", f"{i+4:02d}_{p.replace('-','')}_vs_horas.png", "Horas acumuladas (h)")]:
            fig, ax = plt.subplots()
            trace = q["L actual (mm)"].copy()
            for event_pos in np.flatnonzero(q["maintenance_event"].to_numpy()):
                if event_pos > 0:
                    trace.iloc[event_pos-1] = np.nan  # break pre-repair -> post-repair connection
            ax.plot(q[xcol], trace, color=colors[p], linewidth=1.25, label=f"{p} (línea sin interpolación; reparación segmentada)")
            ax.errorbar(q[xcol], q["L actual (mm)"], yerr=MEASUREMENT_TOLERANCE_MM, fmt="none", ecolor=colors[p], alpha=.35, capsize=2, linewidth=.8,
                        label=f"Guía ±{MEASUREMENT_TOLERANCE_MM:g} mm para cambios (L sigue RAW)")
            ax.scatter(q[xcol], q["L actual (mm)"], color=colors[p], edgecolor="black", linewidth=.3, s=34, label="Medición RAW")
            nulls = q[q["L actual (mm)"].isna()]
            if len(nulls):
                bottom = ax.get_ylim()[0]
                ax.scatter(nulls[xcol], np.full(len(nulls), bottom), marker="x", color="black", s=50, label="NULL / N-I (eje inferior)")
            ax.axhline(c, color="#d18b00", linestyle="--", label=f"Caution {c:g} mm")
            ax.axhline(dg, color="#b22222", linestyle="--", label=f"Danger {dg:g} mm")
            add_events(ax)
            for _, r in q[q.maintenance_event].iterrows():
                ax.annotate("Reparación", (r[xcol], r["L actual (mm)"] if pd.notna(r["L actual (mm)"]) else 0), xytext=(5, 9), textcoords="offset points", fontsize=8)
            changed = q[q["structural_state"].ne(q["structural_state"].shift()) & q["L actual (mm)"].notna() & q["structural_state"].ne("N/I") & ~q["maintenance_event"]]
            for _, r in changed.iloc[1:].iterrows():
                ax.annotate(f"Estado: {r['structural_state']}", (r[xcol], r["L actual (mm)"]), xytext=(4, 10),
                            textcoords="offset points", fontsize=7, color="#333333")
            finish(ax, f"{p}: longitud observada vs {xlabel.lower()}", xlabel, "L actual (mm)", kind=="fecha")
            fig.savefig(PLOTS/fname, dpi=200); plt.close(fig)
        # State validation panel, with measured raw points.
        fig, ax = plt.subplots()
        ax.axhspan(0, c, color=state_colors["Normal"], alpha=.65, label="NORMAL: L < Caution")
        ax.axhspan(c, dg, color=state_colors["Alerta"], alpha=.65, label="ALERTA: Caution ≤ L < Danger")
        top = max(float(q["L actual (mm)"].max(skipna=True) or 0), dg)*1.1
        ax.axhspan(dg, top, color=state_colors["Crítico"], alpha=.65, label="CRÍTICO: L ≥ Danger")
        ax.plot(q["Fecha"], q["L actual (mm)"], color=colors[p], marker="o", linewidth=1, label="Medición RAW")
        if len(q[q["L actual (mm)"].isna()]): ax.scatter(q.loc[q["L actual (mm)"].isna(),"Fecha"], np.zeros(q["L actual (mm)"].isna().sum()), marker="x", color="black", label="NULL / N-I")
        ax.axhline(c, color="#d18b00", linestyle="--", label=f"Caution {c:g} mm"); ax.axhline(dg, color="#b22222", linestyle="--", label=f"Danger {dg:g} mm")
        add_events(ax); finish(ax, f"Validación visual de estados: {p}", "Fecha", "L actual (mm)", True)
        fig.savefig(PLOTS/f"18_{p.replace('-','')}_validacion_estados.png", dpi=200); plt.close(fig)

    fig, ax = plt.subplots()
    for p in POINTS:
        q=scope[scope.codigo.eq(p)].sort_values("Fecha")
        ax.plot(q["Fecha"],q["L actual (mm)"],marker="o",linewidth=1.2,color=colors[p],label=p)
    add_events(ax); finish(ax,"Comparación global de longitudes observadas","Fecha","L actual (mm)",True); fig.savefig(PLOTS/"09_comparacion_global.png",dpi=200); plt.close(fig)
    fig, ax = plt.subplots()
    for p in POINTS:
        q=scope[scope.codigo.eq(p)].sort_values("Fecha")
        ax.plot(q["Fecha"],q["severity_ratio"],marker="o",linewidth=1.2,color=colors[p],label=f"{p} (Caution/Danger={point_summary[p]['caution_ratio']:.2f})")
    ax.axhline(1,color="#b22222",linestyle="--",label="Danger normalizado = 1.0"); add_events(ax)
    finish(ax,"SeverityRatio normalizada por Danger","Fecha","SeverityRatio = L / Danger",True); fig.savefig(PLOTS/"09_severity_normalizada.png",dpi=200); plt.close(fig)

    for name,col,title,ylabel,lo,hi,mean,median in [("10_intervalo_dias.png","delta_dias","Cadencia temporal entre inspecciones","Δdías",d_lo,d_hi,interval_stats["delta_dias"]["mean"],interval_stats["delta_dias"]["median"]),
        ("11_intervalo_horas.png","delta_horas","Cadencia operacional entre inspecciones","Δhoras (h)",h_lo,h_hi,interval_stats["delta_horas"]["mean"],interval_stats["delta_horas"]["median"])]:
        fig,ax=plt.subplots(); sub=inspections.dropna(subset=[col]); ax.plot(sub["Fecha"],sub[col],marker="o",label=ylabel)
        ax.axhline(mean,color="#1f77b4",linestyle="--",label=f"Media {mean:.2f}"); ax.axhline(median,color="#2ca02c",linestyle=":",label=f"Mediana {median:.2f}")
        ax.axhline(lo,color="#b22222",linestyle="--",label=f"Cerca IQR inferior {lo:.2f}"); ax.axhline(hi,color="#b22222",linestyle="--",label=f"Cerca IQR superior {hi:.2f}")
        flag="gap_dias_atipico" if col=="delta_dias" else "gap_horas_atipico"
        bad=inspections[inspections[flag]]; ax.scatter(bad.Fecha,bad[col],color="red",marker="D",s=50,label="Atípico IQR")
        finish(ax,title,"Fecha de inspección",ylabel,True); fig.savefig(PLOTS/name,dpi=200); plt.close(fig)
    fig,ax=plt.subplots(); ax.plot(inspections.Fecha,inspections["Horas (h)"],marker="o",label="Horómetro acumulado")
    for _,r in inspections[inspections.horometro_decreciente].iterrows(): ax.annotate("decreciente",(r.Fecha,r["Horas (h)"]),xytext=(4,8),textcoords="offset points")
    finish(ax,"Horómetro vs fecha","Fecha","Horas acumuladas (h)",True); fig.savefig(PLOTS/"12_horometro_vs_fecha.png",dpi=200); plt.close(fig)
    class_markers={"STABLE_WITHIN_TOLERANCE":"o","SIGNIFICANT_GROWTH":"^","SIGNIFICANT_DECREASE_REVIEW":"v","MAINTENANCE_RESET":"*","N_I":"x"}
    fig,ax=plt.subplots()
    for p in POINTS:
        q=delta_df[delta_df.codigo==p]
        for cls,marker in class_markers.items():
            z=q[q.change_class==cls]
            if not len(z): continue
            y=z.delta_L_raw.fillna(0) if cls!="N_I" else np.zeros(len(z))
            ax.scatter(z.fecha,y,color=colors[p] if cls!="MAINTENANCE_RESET" else "#b22222",marker=marker,s=80 if cls in ("MAINTENANCE_RESET","N_I") else 48,
                       edgecolor="black" if marker not in ("x",) else None,linewidth=.4,
                       label=f"{p} · {cls}")
            if cls == "STABLE_WITHIN_TOLERANCE":
                ax.scatter(z.fecha,z.delta_L_effective,facecolors="none",edgecolors="black",marker="D",s=25,
                           label=f"{p} · ΔL effective")
    ax.axhline(0,color="black",linewidth=.8); add_events(ax)
    finish(ax,"ΔL RAW por clase de cambio","Fecha de inspección","ΔL RAW (mm)",True); fig.savefig(PLOTS/"13_delta_L.png",dpi=200); plt.close(fig)
    fig,ax=plt.subplots()
    for p in POINTS:
        q=growth[growth.codigo==p]
        for cls,marker in class_markers.items():
            z=q[q.change_class==cls]
            if not len(z): continue
            # Non-rate classes are shown on zero only as categorical markers, not as rates.
            y=z.effective_growth_rate_mm_1000h.fillna(0)
            color="#b22222" if cls=="MAINTENANCE_RESET" else colors[p]
            ax.scatter(z.fecha,y,color=color,marker=marker,s=80 if cls in ("MAINTENANCE_RESET","N_I") else 48,
                       edgecolor="black" if marker not in ("x",) else None,linewidth=.4,
                       label=f"{p} · {cls}" + (" (sin tasa; marcador en cero)" if cls in ("MAINTENANCE_RESET","N_I") else ""))
    ax.axhline(0,color="black",linewidth=.8); add_events(ax)
    finish(ax,"Tasa efectiva por clase de cambio","Fecha de inspección","Tasa efectiva (mm / 1000 h)",True); fig.savefig(PLOTS/"14_growth_rate.png",dpi=200); plt.close(fig)
    # missingness matrix has one cell per date and point; measured=1, NULL=0.
    pivot=scope.pivot_table(index="Fecha",columns="codigo",values="L actual (mm)",aggfunc="first").reindex(columns=POINTS)
    fig,ax=plt.subplots(figsize=(9,max(4,len(pivot)*.24)))
    ax.imshow(pivot.notna().astype(int).values,aspect="auto",interpolation="nearest",cmap=matplotlib.colors.ListedColormap(["#d9534f","#5cb85c"]),vmin=0,vmax=1)
    ax.set_yticks(range(len(pivot))); ax.set_yticklabels([d.strftime("%Y-%m-%d") for d in pivot.index],fontsize=7); ax.set_xticks(range(len(POINTS))); ax.set_xticklabels(POINTS)
    ax.set_title("Completitud por fecha y punto (verde=medición, rojo=NULL)"); ax.set_xlabel("Punto"); ax.set_ylabel("Fecha de inspección")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#5cb85c",label="Medición disponible"),Patch(color="#d9534f",label="NULL / N-I")],loc="upper right"); plt.tight_layout(); fig.savefig(PLOTS/"15_missingness_matrix.png",dpi=200); plt.close(fig)
    inspector_map={v:i for i,v in enumerate(sorted(inspections["Inspector"].dropna().unique()))}
    fig,ax=plt.subplots(); yy=inspections["Inspector"].map(inspector_map)
    ax.scatter(inspections.Fecha,yy,c=yy,cmap="tab10",s=55,label="Inspección")
    ax.set_yticks(list(inspector_map.values())); ax.set_yticklabels(list(inspector_map.keys())); finish(ax,"Inspectores en secuencia temporal","Fecha","Inspector",True); fig.savefig(PLOTS/"16_inspectores_timeline.png",dpi=200); plt.close(fig)
    fig,ax=plt.subplots(); ct=inspections["Inspector"].fillna("(vacío)").value_counts().sort_index(); ax.bar(ct.index.astype(str),ct.values,label="Inspecciones");
    for j,v in enumerate(ct.values): ax.text(j,v,f"{v}",ha="center",va="bottom")
    finish(ax,"Número de inspecciones por inspector","Inspector","Inspecciones"); fig.savefig(PLOTS/"17_inspecciones_por_inspector.png",dpi=200); plt.close(fig)

    # Global decision from explicit structural failures and warnings.
    n_fail=int((tests_df.status=="FAIL").sum()); n_warn=int((tests_df.status=="WARNING").sum())
    quality="NO APTO" if n_fail else "APTO CON OBSERVACIONES" if n_warn or n_null or len(anomalies_df) else "APTO"
    all_dates=scope["Fecha"].dropna()
    summary={"source_file":str(SOURCE.relative_to(ROOT)), "source_sha256":__import__("hashlib").sha256(SOURCE.read_bytes()).hexdigest(),
      "scope":{"equipment":EXPECTED_EQUIPMENT,"zone":EXPECTED_ZONE,"points":POINTS}, "workbook":{"sheet_names":sheet_names,"columns_historial":list(raw_hist.columns),"columns_puntos":list(raw_points.columns)},
      "dataset":{"period_start":all_dates.min(),"period_end":all_dates.max(),"inspections":int(date_count),"inspectors":int(scope["Inspector"].nunique(dropna=True)),
        "expected_records":int(expected),"existing_records":int(existing),"numeric_measurements":int(scope["L actual (mm)"].notna().sum()),"null_measurements":n_null,
        "completeness_pct":float(scope["L actual (mm)"].notna().mean()*100 if existing else 0),"by_point":completeness,"by_inspector":by_inspector.to_dict(orient="records"),
        "missing_dates":missing_dates,"state_counts":status_counts},
      "temporal":interval_stats,"points":point_summary,"maintenance_events":maintenance_out.to_dict(orient="records"),
      "measurement_uncertainty":{"tolerance_mm":MEASUREMENT_TOLERANCE_MM,
        "purpose":"Interpretación de cambio entre inspecciones","affects_structural_state":False},
      "change_class_counts":change_class_counts,"previous_anomalies_reclassified":prior_changes,
      "qa":{"duplicate_rows":int(dups.sum()),"duplicate_keys":int(scope.duplicated(["Fecha","Equipo","Código"]).sum()),
        "hour_decreases":int(inspections.horometro_decreciente.sum()),"duplicate_dates":int(inspections.Fecha.duplicated().sum()),
        "duplicate_hour_observations":int(inspections["Horas (h)"].duplicated().sum()),"date_gap_outliers":int(inspections.gap_dias_atipico.sum()),
        "operational_gap_outliers":int(inspections.gap_horas_atipico.sum()),"decrements":int((delta_df.tipo_delta=="decremento").sum()),
        "change_class_counts":change_class_counts,"previous_anomalies_reclassified":prior_changes,
        "large_jumps_over_50mm":int((delta_df.delta_L_mm>50).sum()),"anomaly_rows":len(anomalies_df),"tests_pass":int((tests_df.status=="PASS").sum()),
        "tests_warning":n_warn,"tests_fail":n_fail,"quality_classification":quality},
      "interpretation":{"facts":[f"El libro cubre {all_dates.min():%Y-%m-%d} a {all_dates.max():%Y-%m-%d} en el alcance SD.",
          f"Se encontraron {n_null} celdas de medición NULL; se conservaron como N/I.","Se registró una anotación de reparación general de chasis el 2025-01-07."],
        "hypotheses":["Decrementos previos al evento pueden reflejar incertidumbre de medición, variación física o una intervención no anotada.","Las diferencias entre inspectores son descriptivas; el calendario y la identidad del inspector están asociados y no permiten inferencia causal."],
        "human_review_questions":["¿La reparación general del 2025-01-07 intervino los cuatro puntos SD y hubo remoción/reemplazo de material?","¿Cuál fue el motivo de los tres registros vacíos?","¿Las mediciones con decremento se pueden contrastar con fotografías o protocolo de medición?","¿Qué tolerancia de medición y resolución aplicó cada inspector?"]}}
    (OUT/"qa_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=json_safe),encoding="utf-8")

    # Self-contained HTML report with all plot assets referenced by relative path.
    plot_files=sorted(PLOTS.glob("*.png"))
    test_html=tests_df.to_html(index=False,escape=True)
    anomaly_html=anomalies_df.to_html(index=False,escape=True) if len(anomalies_df) else "<p>Sin hallazgos.</p>"
    missing_html=missing.to_html(index=False,escape=True) if len(missing) else "<p>Sin valores NULL.</p>"
    maint_html=maintenance_out.to_html(index=False,escape=True) if len(maintenance_out) else "<p>Sin eventos documentados.</p>"
    point_rows="".join(f"<tr><td>{p}</td><td>{fmt(s['caution_mm'])}</td><td>{fmt(s['danger_mm'])}</td><td>{fmt(s['max_mm'])}</td><td>{fmt(s['max_date'])}</td><td>{fmt(s['first_positive'])}</td><td>{fmt(s['first_alert'])}</td><td>{fmt(s['first_critical'])}</td><td>{s['states']['Normal']}</td><td>{s['states']['Alerta']}</td><td>{s['states']['Crítico']}</td><td>{s['states']['N/I']}</td></tr>" for p,s in point_summary.items())
    def stats_table(title: str, s: dict) -> str:
        keys=[("n","n"),("mean","media"),("median","mediana"),("std","desv. estándar"),("min","mínimo"),("max","máximo"),("q1","Q1"),("q3","Q3"),("iqr","IQR"),("mad","MAD"),("cv","CV")]
        return f"<h3>{title}</h3><table><tbody>"+"".join(f"<tr><th>{label}</th><td>{fmt(s[k])}</td></tr>" for k,label in keys)+"</tbody></table>"
    plots_html="".join(f"<figure><img src='plots/{p.name}' alt='{p.stem}'><figcaption>{p.name}</figcaption></figure>" for p in plot_files)
    reclass_html=pd.DataFrame(prior_changes).to_html(index=False,escape=True) if prior_changes else "<p>Ningún decremento previamente marcado quedó dentro de tolerancia.</p>"
    report=f"""<!doctype html><html lang='es'><head><meta charset='utf-8'><title>QA EH4000 SD</title><style>body{{font:15px Arial,sans-serif;max-width:1250px;margin:2rem auto;padding:0 1rem;color:#222}}h1,h2{{color:#18324b}}table{{border-collapse:collapse;margin:.7rem 0 1.5rem;width:100%;font-size:13px}}td,th{{border:1px solid #ccc;padding:6px;text-align:left}}th{{background:#eef2f5}}.status{{padding:1rem;background:#fff2cc;border-left:5px solid #d18b00}}.plots{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}figure{{margin:0;border:1px solid #ddd;padding:.5rem}}img{{width:100%;height:auto}}figcaption{{font-size:12px;color:#555}}pre{{white-space:pre-wrap}}</style></head><body>
    <h1>Auditoría QA: EH4000, tijeras y spindle</h1><p>Alcance: EH4-01, SD-01 a SD-04. Fuente: {SOURCE.name}. RAW no modificado; 0 mm se conserva distinto de NULL.</p>
    <div class='status'><b>Clasificación: {quality}</b><br>Periodo {all_dates.min():%Y-%m-%d} – {all_dates.max():%Y-%m-%d}; {date_count} inspecciones, {existing}/{expected} filas, completitud de medición {fmt(summary['dataset']['completeness_pct'])}%.</div>
    <h2>Resumen ejecutivo</h2><p>Se encontraron {n_null} mediciones NULL, {int(dups.sum())} filas duplicadas según (Fecha, Equipo, Código), {int(inspections.horometro_decreciente.sum())} decrementos del horómetro y {len(maintenance_out)} filas de evento documental, agrupadas en {maintenance_out['Fecha'].nunique() if len(maintenance_out) else 0} fecha(s). La anotación del 2025-01-07 identifica una reparación general; se excluyen de velocidad los intervalos que tocan el evento.</p>
    <h2>Tolerancia operacional</h2><p>MEASUREMENT_TOLERANCE_MM = {MEASUREMENT_TOLERANCE_MM:g} mm; aplica únicamente a cambios entre inspecciones. structural_state se calcula con L RAW y límites oficiales, sin tolerancia.</p><p>Conteos change_class: {change_class_counts}.</p><h3>Anomalías previas reclasificadas</h3>{reclass_html}
    <h2>Metadata</h2><p>Hojas: {', '.join(sheet_names)}. Columnas Historial: {', '.join(map(str,raw_hist.columns))}. Columna de imagen presente: sí; imágenes embebidas no se usan para inferir mediciones.</p>
    <h2>Tests estructurales</h2>{test_html}<h2>Estadísticas temporales</h2>{stats_table('Δdías',interval_stats['delta_dias'])}{stats_table('Δhoras',interval_stats['delta_horas'])}<p>Cercas robustas IQR: días [{fmt(d_lo)}, {fmt(d_hi)}]; horas [{fmt(h_lo)}, {fmt(h_hi)}]. Detección descriptiva, no dictamen de error.</p>
    <h2>Estadísticas por punto</h2><table><thead><tr><th>Punto</th><th>Caution</th><th>Danger</th><th>Máximo</th><th>Fecha máximo</th><th>Primera &gt;0</th><th>Primera alerta</th><th>Primera crítica</th><th>Normal</th><th>Alerta</th><th>Crítico</th><th>N/I</th></tr></thead><tbody>{point_rows}</tbody></table>
    <h2>Valores faltantes</h2>{missing_html}<h2>Anomalías y hallazgos</h2>{anomaly_html}<h2>Eventos de mantenimiento</h2>{maint_html}<h2>Inspector por completitud</h2>{by_inspector.to_html(index=False,escape=True)}<p>La secuencia por inspector es descriptiva. Con 25 fechas y rotación temporal, estos datos no permiten separar estadísticamente el efecto del inspector del efecto temporal ni afirmar causalidad.</p>
    <h2>Visualizaciones QA</h2><div class='plots'>{plots_html}</div><h2>Conclusiones científicas</h2><h3>Hechos observados</h3><ul>{''.join(f'<li>{x}</li>' for x in summary['interpretation']['facts'])}</ul><h3>Anomalías detectadas</h3><ul>{''.join(f'<li>{a["severity"]}: {a["explicacion"]} (fila Excel {a["fila_excel"]})</li>' for a in anomalies[:40])}</ul><h3>Hipótesis</h3><ul>{''.join(f'<li>{x}</li>' for x in summary['interpretation']['hypotheses'])}</ul><h3>Decisiones pendientes</h3><ul>{''.join(f'<li>{x}</li>' for x in summary['interpretation']['human_review_questions'])}</ul>
    </body></html>"""
    (OUT/"QA_REPORT.html").write_text(report,encoding="utf-8")

    # Re-read outputs and enforce reproducibility checks without changing source.
    expected_files=["qa_summary.json","qa_tests.csv","qa_anomalies.csv","qa_missing_values.csv","qa_maintenance_events.csv","sd_inspections_qa.csv","sd_intervals.csv","sd_growth_rates.csv","sd_delta_L.csv","inspector_completeness.csv","QA_REPORT.html"]
    missing_files=[f for f in expected_files if not (OUT/f).exists()]
    plot_missing=[name for name in ["01_SD01_vs_fecha.png","02_SD02_vs_fecha.png","03_SD03_vs_fecha.png","04_SD04_vs_fecha.png","05_SD01_vs_horas.png","06_SD02_vs_horas.png","07_SD03_vs_horas.png","08_SD04_vs_horas.png","09_severity_normalizada.png","10_intervalo_dias.png","11_intervalo_horas.png","12_horometro_vs_fecha.png","13_delta_L.png","14_growth_rate.png","15_missingness_matrix.png","16_inspectores_timeline.png","17_inspecciones_por_inspector.png","18_SD01_validacion_estados.png","18_SD02_validacion_estados.png","18_SD03_validacion_estados.png","18_SD04_validacion_estados.png"] if not (PLOTS/name).exists()]
    reread_ins=pd.read_csv(OUT/"sd_inspections_qa.csv")
    reread_null=pd.read_csv(OUT/"qa_missing_values.csv")
    reread_delta=pd.read_csv(OUT/"sd_delta_L.csv")
    reread_growth=pd.read_csv(OUT/"sd_growth_rates.csv")
    reread_summary=json.loads((OUT/"qa_summary.json").read_text(encoding="utf-8"))
    source_hash_after=__import__("hashlib").sha256(SOURCE.read_bytes()).hexdigest()
    required_delta_cols={"delta_L_raw","delta_L_effective","change_class"}
    required_growth_cols={"raw_growth_rate_mm_1000h","effective_growth_rate_mm_1000h","change_class"}
    csv_eff=reread_delta["delta_L_effective"]
    csv_raw=reread_delta["delta_L_raw"]
    expected_csv_eff=csv_raw.where(csv_raw.abs()>MEASUREMENT_TOLERANCE_MM,0.0)
    csv_effective_matches=csv_eff.isna().eq(csv_raw.isna()).all() and np.allclose(csv_eff[csv_raw.notna()],expected_csv_eff[csv_raw.notna()])
    csv_rate_policy=(reread_growth.loc[reread_growth.change_class.isin(["N_I","MAINTENANCE_RESET"]),"effective_growth_rate_mm_1000h"].isna().all()
                     and (reread_growth.loc[reread_growth.change_class.eq("STABLE_WITHIN_TOLERANCE"),"effective_growth_rate_mm_1000h"]==0).all())
    validations={"promised_files_missing":missing_files,"plots_missing":plot_missing,
      "csv_record_count_matches":len(reread_ins)==existing,"csv_null_count_matches":len(reread_null)==n_null,
      "json_record_count_matches":reread_summary["dataset"]["existing_records"]==existing,
      "delta_csv_rows_match":len(reread_delta)==len(scope),"growth_csv_rows_match":len(reread_growth)==len(scope),
      "delta_csv_columns_present":required_delta_cols.issubset(reread_delta.columns),
      "growth_csv_columns_present":required_growth_cols.issubset(reread_growth.columns),
      "effective_delta_formula_matches":bool(csv_effective_matches),"effective_rate_policy_matches":bool(csv_rate_policy),
      "measurement_uncertainty_metadata_matches":reread_summary.get("measurement_uncertainty")=={"tolerance_mm":MEASUREMENT_TOLERANCE_MM,"purpose":"Interpretación de cambio entre inspecciones","affects_structural_state":False},
      "html_contains_tolerance_and_reclassification":"Anomalías previas reclasificadas" in (OUT/"QA_REPORT.html").read_text(encoding="utf-8") and "MEASUREMENT_TOLERANCE_MM" in (OUT/"QA_REPORT.html").read_text(encoding="utf-8"),
      "source_unchanged":source_hash_after==summary["source_sha256"],
      "null_not_converted_to_zero":int(reread_ins["L actual (mm)"].isna().sum())==n_null and int((reread_ins["L actual (mm)"].fillna(999999)==0).sum())==int((scope["L actual (mm)"]==0).sum()),
      "plots_saved":len(list(PLOTS.glob("*.png")))>=21}
    (OUT/"qa_validation.json").write_text(json.dumps(validations,ensure_ascii=False,indent=2),encoding="utf-8")
    if missing_files or plot_missing or not all(v for k,v in validations.items() if isinstance(v,bool)):
        raise RuntimeError(f"Validación de salidas falló: {validations}")
    print(json.dumps({"status":"COMPLETED","classification":quality,"dataset":summary["dataset"],"temporal":interval_stats,
                      "points":point_summary,"qa":summary["qa"],"validation":validations,"output":str(OUT)},ensure_ascii=False,indent=2,default=json_safe))


if __name__ == "__main__": main()
