from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_import_is_idempotent_and_preserves_zero_and_null(client):
    assert client.get("/api/health").json()["inspection_dates"] == 25
    rows = client.get("/api/inspections?limit=500").json()
    assert len(rows) == 25
    assert sum(len(row["measurements"]) for row in rows) == 100
    values = [m["length_mm"] for row in rows for m in row["measurements"]]
    assert values.count(None) == 3
    assert values.count(0.0) > 0
    qa = client.get("/api/analytics/qa").json()
    assert qa["measurement_uncertainty"]["tolerance_mm"] == 10
    assert qa["validation"]["source_unchanged"] is True
    # A second app lifespan / bootstrap does not add historical rows.
    assert client.get("/api/health").json()["inspection_dates"] == 25


def test_official_state_and_current_snapshot(client):
    latest = client.get("/api/inspections?limit=1").json()[0]
    for item in latest["measurements"]:
        length = item["length_mm"]
        if length is None:
            assert item["structural_state"] == "N/I"
        elif length < item["caution_mm"]:
            assert item["structural_state"] == "Normal"
        elif length < item["danger_mm"]:
            assert item["structural_state"] == "Alerta"
        else:
            assert item["structural_state"] == "Crítico"
    overview = client.get("/api/analytics/overview").json()
    assert overview["date"] == latest["date"]
    assert overview["historical_only"] is True
    assert overview["live_telemetry"] is False


def test_new_inspection_validation_and_append_only(client):
    last = client.get("/api/inspections?limit=1").json()[0]
    next_date = (date.fromisoformat(last["date"]) + timedelta(days=35)).isoformat()
    payload = {"date": next_date, "hours": last["hours"] + 550, "inspector": "TEST-INSP", "measurements": [
        {"point":"SD-01","length_mm":0}, {"point":"SD-02","length_mm":None},
        {"point":"SD-03","length_mm":0}, {"point":"SD-04","length_mm":0},
    ]}
    created = client.post("/api/inspections", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["imported"] is False
    by_point = {m["point"]:m for m in body["measurements"]}
    assert by_point["SD-01"]["length_mm"] == 0
    assert by_point["SD-02"]["length_mm"] is None
    assert by_point["SD-02"]["structural_state"] == "N/I"
    assert by_point["SD-02"]["maintenance_action"] == "REINSPECTION_REQUIRED"
    assert client.post("/api/inspections", json=payload).status_code == 409
    bad_date = {**payload, "date": (date.fromisoformat(next_date) + timedelta(days=1)).isoformat(), "hours": last["hours"] - 1}
    assert client.post("/api/inspections", json=bad_date).status_code == 422


def test_value_after_null_is_only_a_gap_spanning_warning(client):
    previous = client.get("/api/inspections?limit=1").json()[0]
    next_date=(date.fromisoformat(previous["date"])+timedelta(days=35)).isoformat()
    measurements=[]
    for m in previous["measurements"]:
        measurements.append({"point":m["point"],"length_mm":20 if m["point"]=="SD-02" else m["length_mm"]})
    result=client.post("/api/inspections",json={"date":next_date,"hours":previous["hours"]+550,
        "inspector":"TEST-INSP-2","measurements":measurements})
    assert result.status_code==201,result.text
    sd02=next(m for m in result.json()["measurements"] if m["point"]=="SD-02")
    assert sd02["gap_spanning_change"] is True
    assert sd02["change_class"]=="N_I"
    assert sd02["delta_l_raw"] is None
    assert sd02["raw_growth_rate"] is None
    assert sd02["effective_growth_rate"] is None
    assert sd02["delta_l_bridged_raw"] is not None
    assert sd02["data_warning"]=="GAP_SPANNING_CHANGE"


def test_work_order_lifecycle_is_explicit_and_audited(client):
    latest = client.get("/api/inspections?limit=1").json()[0]
    measurement = latest["measurements"][0]
    created = client.post("/api/work-orders", json={"point":measurement["point"],"priority":"P1",
        "intervention_type":"Inspection review","description":"Review the current measurement and validate it with engineering.",
        "source_measurement_id":measurement["id"]})
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["status"] == "PENDING"
    assert client.patch(f"/api/work-orders/{order['id']}",json={"status":"SCHEDULED"}).status_code == 409
    assert client.patch(f"/api/work-orders/{order['id']}",json={"status":"APPROVED"}).status_code == 200
    assert client.patch(f"/api/work-orders/{order['id']}",json={"status":"SCHEDULED"}).status_code == 422
    schedule_date=(date.today()+timedelta(days=14)).isoformat()
    assert client.patch(f"/api/work-orders/{order['id']}",json={"status":"SCHEDULED","scheduled_date":schedule_date}).status_code == 200
    assert client.patch(f"/api/work-orders/{order['id']}",json={"status":"IN_PROGRESS"}).status_code == 200
    completed=client.patch(f"/api/work-orders/{order['id']}",json={"status":"COMPLETED"})
    assert completed.status_code == 200 and completed.json()["closed_at"]
    history=client.get(f"/api/work-orders/{order['id']}/history").json()
    assert [h["to_status"] for h in history] == ["PENDING","APPROVED","SCHEDULED","IN_PROGRESS","COMPLETED"]


def test_hotspot_calibration_and_evidence_persist(client):
    before=client.get("/api/3d/hotspots").json()
    assert len(before)==4
    saved=client.put("/api/3d/hotspots/SD-01",json={"x":1.0,"y":2.0,"z":3.0,"nx":0,"ny":1,"nz":0,"confirmed":False,"calibrated_by":"TEST"})
    assert saved.status_code==200 and saved.json()["calibration_status"]=="UNVERIFIED"
    latest=client.get("/api/inspections?limit=1").json()[0]
    response=client.post("/api/evidence",data={"inspection_id":str(latest["id"]),"point":"SD-01","notes":"Integration test evidence"},
        files={"file":("evidence.png",b"test-image-bytes","image/png")})
    assert response.status_code==201,response.text
    evidence=response.json()
    assert client.get(f"/api/evidence/{evidence['id']}").status_code==200
    assert client.get("/api/evidence?point=SD-01").json()[0]["inspection_id"]==latest["id"]
