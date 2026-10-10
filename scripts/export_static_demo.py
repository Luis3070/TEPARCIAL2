"""Export validated, read-only API responses for the static evaluation site."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    # A fresh database includes only validated source history. No local user records
    # or evidence files are copied into the public evaluation package.
    with tempfile.TemporaryDirectory(prefix="eh4000-static-") as temporary:
        os.environ["EH4000_DB_PATH"] = str(Path(temporary) / "history.sqlite3")
        from backend.app.main import app
        from backend.app.database import engine

        with TestClient(app) as client:
            def get(path: str):
                response = client.get("/api" + path)
                response.raise_for_status()
                return response.json()

            inspections = get("/inspections?limit=500")
            ids = [inspection["id"] for inspection in inspections]
            points = ("SD-01", "SD-02", "SD-03", "SD-04")
            payload = {
                "health": get("/health"),
                "inspections": inspections,
                "snapshots": get("/snapshots"),
                "events": get("/maintenance/events"),
                "qa": get("/analytics/qa"),
                "maintenanceSummary": get("/analytics/maintenance-summary"),
                "inspectors": get("/analytics/inspectors"),
                "model": get("/3d/models"),
                "hotspots": get("/3d/hotspots"),
                "pointHistories": {point: get(f"/points/{point}/history") for point in points},
                "overviews": {str(i): get(f"/analytics/overview?inspection_id={i}") for i in ids},
                "pointsByInspection": {str(i): get(f"/points?inspection_id={i}") for i in ids},
                "recommendations": {str(i): get(f"/maintenance/recommendations?inspection_id={i}") for i in ids},
            }

        destination = ROOT / "frontend" / "public" / "demo" / "data.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"Exported {len(ids)} inspections to {destination}")
        engine.dispose()


if __name__ == "__main__":
    main()
