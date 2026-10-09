import csv
from collections import Counter
from pathlib import Path

import pytest

from backend.app.maintenance.rules import decision, structural_state_for


ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / "outputs" / "maintenance" / "maintenance_features.csv"


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (None, "N/I"),
        (0, "Normal"),
        (139.9, "Normal"),
        (140, "Alerta"),
        (199.9, "Alerta"),
        (200, "Crítico"),
        (34.9, "Normal"),
        (35, "Alerta"),
        (49.9, "Alerta"),
        (50, "Crítico"),
    ],
)
def test_state_uses_raw_length_and_inclusive_official_boundaries(length, expected):
    caution, danger = (35, 50) if length is not None and length < 100 else (140, 200)
    assert structural_state_for(length, caution_mm=caution, danger_mm=danger) == expected


def test_state_rejects_invalid_limit_order():
    with pytest.raises(ValueError, match="Caution must be lower than Danger"):
        structural_state_for(10, caution_mm=50, danger_mm=35)


def test_rule_examples_are_deterministic_and_do_not_claim_engineer_approval():
    cases = [
        ({"structural_state": "Normal", "change_class": "STABLE_WITHIN_TOLERANCE", "L_raw_mm": 0, "caution_mm": 140, "danger_mm": 200}, False, False, "MONITOR_ROUTINE", "P0"),
        ({"structural_state": "Normal", "change_class": "SIGNIFICANT_GROWTH", "L_raw_mm": 50, "caution_mm": 140, "danger_mm": 200, "delta_L_raw": 20}, False, False, "MONITOR_INTENSIFIED", "P1"),
        ({"structural_state": "Alerta", "change_class": "STABLE_WITHIN_TOLERANCE", "L_raw_mm": 140, "caution_mm": 140, "danger_mm": 200}, False, False, "PLAN_REPAIR", "P2"),
        ({"structural_state": "Alerta", "change_class": "SIGNIFICANT_GROWTH", "L_raw_mm": 150, "caution_mm": 140, "danger_mm": 200, "delta_L_raw": 20}, False, False, "PRIORITIZE_REPAIR", "P3"),
        ({"structural_state": "Crítico", "change_class": "STABLE_WITHIN_TOLERANCE", "L_raw_mm": 200, "caution_mm": 140, "danger_mm": 200}, False, False, "REPAIR_BEFORE_OPERATION", "P4"),
        ({"structural_state": "N/I", "change_class": "N_I", "L_raw_mm": None, "caution_mm": 140, "danger_mm": 200}, False, False, "REINSPECTION_REQUIRED", "P1"),
        ({"structural_state": "Normal", "change_class": "MAINTENANCE_RESET", "L_raw_mm": 0, "caution_mm": 140, "danger_mm": 200}, True, False, "POST_REPAIR_VERIFICATION", "P1"),
        ({"structural_state": "Normal", "change_class": "N_I", "L_raw_mm": 0, "caution_mm": 140, "danger_mm": 200, "gap_spanning_change": True, "delta_L_bridged_raw": 15}, False, False, "MONITOR_ROUTINE", "P0"),
        ({"structural_state": "Normal", "change_class": "N_I", "L_raw_mm": 0, "caution_mm": 140, "danger_mm": 200}, False, True, "INITIAL_MEASURE", None),
    ]
    for row, post_repair, initial, expected_action, expected_priority in cases:
        action, priority, _mode, reason = decision(row, post_repair, initial)
        assert (action, priority) == (expected_action, expected_priority)
        assert reason


def _number(value):
    if value is None or not value.strip() or value.strip().lower() in {"nan", "null", "none"}:
        return None
    return float(value)


def _boolean(value):
    return value.strip().lower() in {"true", "1", "yes"}


def test_all_historical_actions_match_the_versioned_rule_table():
    assert FEATURES.exists(), f"Missing reproducible QA output: {FEATURES}"
    with FEATURES.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 100
    assert Counter(row["point"] for row in rows) == {
        "SD-01": 25, "SD-02": 25, "SD-03": 25, "SD-04": 25,
    }
    assert sum(_number(row["L_raw_mm"]) is None for row in rows) == 3
    assert sum(_number(row["L_raw_mm"]) == 0 for row in rows if _number(row["L_raw_mm"]) is not None) > 0

    undefined = []
    for row in rows:
        raw = _number(row["L_raw_mm"])
        rule_input = {
            "structural_state": row["structural_state"],
            "change_class": row["change_class"],
            "L_raw_mm": raw,
            "caution_mm": _number(row["caution_mm"]),
            "danger_mm": _number(row["danger_mm"]),
            "delta_L_raw": _number(row["delta_L_raw"]),
            "gap_spanning_change": _boolean(row["gap_spanning_change"]),
            "delta_L_bridged_raw": _number(row["delta_L_bridged_raw"]),
        }
        action, priority, mode, reason = decision(
            rule_input,
            _boolean(row["is_first_post_repair_inspection"]),
            _boolean(row["is_initial_measure"]),
        )
        assert row["maintenance_action"] == action, (row["date"], row["point"], action)
        assert (row["maintenance_priority"] or None) == priority, (row["date"], row["point"], priority)
        assert (row["maintenance_mode"] or None) == mode, (row["date"], row["point"], mode)
        assert row["decision_reason"] == reason, (row["date"], row["point"], reason)
        if action == "RULE_NOT_DEFINED":
            undefined.append((row["date"], row["point"], row["change_class"]))

    assert undefined == []
