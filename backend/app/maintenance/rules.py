from __future__ import annotations

import math
from typing import Any


def structural_state_for(length_mm: float | None, caution_mm: float, danger_mm: float) -> str:
    """Return the official state from RAW length; a missing value remains N/I."""
    if caution_mm >= danger_mm:
        raise ValueError("Caution must be lower than Danger.")
    if length_mm is None:
        return "N/I"
    if length_mm < caution_mm:
        return "Normal"
    if length_mm < danger_mm:
        return "Alerta"
    return "Crítico"


def decision(row: Any, first_post_repair: bool, first_valid_measure: bool) -> tuple[str, str | None, str | None, str]:
    """Version 1 deterministic decision aid; this does not imply engineer endorsement."""
    state = row["structural_state"]
    change = row["change_class"]
    L, caution, danger = row["L_raw_mm"], row["caution_mm"], row["danger_mm"]
    if state == "Crítico":
        return "REPAIR_BEFORE_OPERATION", "P4", "CORRECTIVE_IMMEDIATE", f"L = {L:g} mm alcanza Danger = {danger:g} mm. Reparar antes de continuar operando."
    if state == "Alerta":
        if change == "SIGNIFICANT_GROWTH":
            return "PRIORITIZE_REPAIR", "P3", "CORRECTIVE_PRIORITY", f"L = {L:g} mm supera Caution = {caution:g} mm y creció {row['delta_L_raw']:g} mm desde la inspección anterior. Priorizar reparación."
        return "PLAN_REPAIR", "P2", "CORRECTIVE_PLANNED", f"L = {L:g} mm supera Caution = {caution:g} mm. Reparación programable."
    if state == "N/I":
        return "REINSPECTION_REQUIRED", "P1", "INSPECTION", "Medición no disponible. Condición estructural no evaluable."
    if first_post_repair:
        return "POST_REPAIR_VERIFICATION", "P1", "INSPECTION", "Primera inspección posterior a reparación documentada."
    if first_valid_measure:
        return "INITIAL_MEASURE", None, None, "Primera medición válida de la serie; establece línea base y no tiene ΔL previo."
    if state == "Normal" and change == "STABLE_WITHIN_TOLERANCE":
        return "MONITOR_ROUTINE", "P0", "PREVENTIVE", "Normal y sin cambio superior a la tolerancia de medición."
    if state == "Normal" and change == "SIGNIFICANT_GROWTH":
        return "MONITOR_INTENSIFIED", "P1", "PREVENTIVE", f"Normal con crecimiento significativo de {row['delta_L_raw']:g} mm desde la inspección anterior."
    if state == "Normal" and change == "N_I" and bool(row.get("gap_spanning_change", False)):
        bridge = row.get("delta_L_bridged_raw")
        bridge_text = "N/D" if bridge is None or (isinstance(bridge, float) and math.isnan(bridge)) else f"{bridge:g} mm"
        return "MONITOR_ROUTINE", "P0", "PREVENTIVE", f"Estado actual Normal. ΔL consecutivo no calculable por NULL previo; cambio puenteado {bridge_text} mostrado con advertencia y no usado para priorizar."
    return "RULE_NOT_DEFINED", None, None, f"Combinación sin regla V1 explícita: structural_state={state}; change_class={change}. Revisión ingenieril requerida."
