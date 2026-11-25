import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test2.db")

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.seed import DEMO_PASSWORD


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username):
    r = client.post("/api/auth/login", data={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def token(client, username):
    return login(client, username)["Authorization"].split()[1]


def uid(client, h, username):
    return next(u["id"] for u in client.get("/api/staff", headers=h).json() if u["username"] == username)


def new_patient(client, name="Temp", allergies=None):
    h = login(client, "front.amy")
    r = client.post("/api/patients", headers=h, json={"first_name": name, "last_name": "Case", "dob": "1990-01-01",
                                                       "sex": "female", "allergies": allergies})
    return r.json()["id"]


# ---------------- admissions ----------------
def test_er_to_ward_admission_flow(client):
    doc = login(client, "dr.webber")
    pid = new_patient(client, "Ward")
    visit = client.post("/api/er", headers=doc, json={"patient_id": pid, "complaint": "Dehydration", "triage_level": 3}).json()
    beds = client.get("/api/beds", headers=doc).json()
    er_bed = next(b for b in beds if b["ward"] == "ER" and not b["occupied"])
    gen = [b for b in beds if b["ward"] == "General" and not b["occupied"]]
    me = uid(client, doc, "dr.webber")

    # put the patient in an ER bed first so we can check it is released on admission
    assert client.post(f"/api/er/{visit['id']}/assign", headers=doc, json={"bed_id": er_bed["id"], "attending_id": me}).status_code == 200
    # the old shortcut is gone: admitting must go through /admissions
    assert client.post(f"/api/er/{visit['id']}/close", headers=doc, json={"status": "admitted"}).status_code == 422
    # ER beds are not inpatient beds
    r = client.post("/api/admissions", headers=doc, json={"patient_id": pid, "bed_id": er_bed["id"], "attending_id": me, "reason": "x", "er_visit_id": visit["id"]})
    assert r.status_code == 422
    # nurses cannot admit
    nurse = login(client, "nurse.olivia")
    assert client.post("/api/admissions", headers=nurse, json={"patient_id": pid, "bed_id": gen[0]["id"], "attending_id": me, "reason": "x"}).status_code == 403

    r = client.post("/api/admissions", headers=doc, json={"patient_id": pid, "bed_id": gen[0]["id"], "attending_id": me, "reason": "IV fluids", "er_visit_id": visit["id"]})
    assert r.status_code == 201, r.text
    adm = r.json()
    assert adm["source"] == "er" and adm["ward"] == "General" and adm["status"] == "admitted"
    after = {b["id"]: b for b in client.get("/api/beds", headers=doc).json()}
    assert after[er_bed["id"]]["occupied"] is False and after[gen[0]["id"]]["occupied"] is True
    assert next(v for v in client.get("/api/er?include_closed=true", headers=doc).json() if v["id"] == visit["id"])["status"] == "admitted"

    # already admitted / occupied bed
    other = new_patient(client, "Other")
    assert client.post("/api/admissions", headers=doc, json={"patient_id": pid, "bed_id": gen[1]["id"], "attending_id": me, "reason": "x"}).status_code == 409
    assert client.post("/api/admissions", headers=doc, json={"patient_id": other, "bed_id": gen[0]["id"], "attending_id": me, "reason": "x"}).status_code == 409

    # transfer (nurses may) frees old bed and logs history
    r = client.post(f"/api/admissions/{adm['id']}/transfer", headers=nurse, json={"bed_id": gen[1]["id"]})
    assert r.status_code == 200 and r.json()["bed_id"] == gen[1]["id"] and len(r.json()["transfers"]) == 1
    after = {b["id"]: b for b in client.get("/api/beds", headers=doc).json()}
    assert after[gen[0]["id"]]["occupied"] is False and after[gen[1]["id"]]["occupied"] is True

    # discharge needs a doctor and a summary, frees the bed, and cannot be repeated
    assert client.post(f"/api/admissions/{adm['id']}/discharge", headers=nurse, json={"summary": "Well, go home"}).status_code == 403
    assert client.post(f"/api/admissions/{adm['id']}/discharge", headers=doc, json={"summary": "ok"}).status_code == 422
    r = client.post(f"/api/admissions/{adm['id']}/discharge", headers=doc, json={"summary": "Recovered, oral fluids tolerated."})
    assert r.json()["status"] == "discharged"
    assert client.post(f"/api/admissions/{adm['id']}/discharge", headers=doc, json={"summary": "Recovered again"}).status_code == 409
    assert {b["id"]: b for b in client.get("/api/beds", headers=doc).json()}[gen[1]["id"]]["occupied"] is False


def test_wards_overview(client):
    wards = client.get("/api/wards", headers=login(client, "nurse.kim")).json()
    names = {w["ward"] for w in wards}
    assert names == {"ICU", "General"}
    icu = next(w for w in wards if w["ward"] == "ICU")
    assert any(b["patient_name"] for b in icu["beds"])
    assert client.get("/api/wards", headers=login(client, "bill.cole")).status_code == 403


# ---------------- roster ----------------
def test_roster_rules(client):
    chief, nurse = login(client, "dr.webber"), login(client, "nurse.olivia")
    who = uid(client, chief, "dr.altman")
    mk = lambda s, e, kind="day": {"user_id": who, "start": s, "end": e, "kind": kind, "unit": "OR"}

    assert client.post("/api/shifts", headers=nurse, json=mk("2035-03-01T06:00:00", "2035-03-01T18:00:00")).status_code == 403
    r = client.post("/api/shifts", headers=chief, json=mk("2035-03-01T06:00:00", "2035-03-01T18:00:00"))
    assert r.status_code == 201
    sid = r.json()["id"]
    # overlap
    assert client.post("/api/shifts", headers=chief, json=mk("2035-03-01T12:00:00", "2035-03-01T20:00:00")).status_code == 409
    # back-to-back shifts violate the 8-hour rest rule
    r = client.post("/api/shifts", headers=chief, json=mk("2035-03-01T18:00:00", "2035-03-02T06:00:00", "night"))
    assert r.status_code == 409 and "rest" in r.json()["detail"]
    # but on-call may overlap a regular shift
    assert client.post("/api/shifts", headers=chief, json=mk("2035-03-01T10:00:00", "2035-03-01T22:00:00", "on_call")).status_code == 201
    # invalid inputs
    assert client.post("/api/shifts", headers=chief, json=mk("2035-03-02T06:00:00", "2035-03-04T06:00:00")).status_code == 422
    admin_id = uid(client, chief, "admin")
    assert client.post("/api/shifts", headers=chief, json={**mk("2035-03-05T06:00:00", "2035-03-05T18:00:00"), "user_id": admin_id}).status_code == 422

    listed = client.get("/api/shifts?start=2035-03-01&days=2", headers=nurse).json()
    assert {s["user_name"] for s in listed} == {"Dr. Erica Hahn"}

    cov = client.get("/api/shifts/coverage?start=2035-03-01&days=1", headers=nurse).json()
    day = next(c for c in cov if c["kind"] == "day")
    assert day["understaffed"] and day["counts"]["doctor"] == 1 and day["gaps"]["nurse"] == 2 and day["gaps"]["surgeon"] == 1

    assert client.delete(f"/api/shifts/{sid}", headers=nurse).status_code == 403
    assert client.delete(f"/api/shifts/{sid}", headers=chief).status_code == 204
    assert client.get("/api/shifts/on-duty", headers=nurse).status_code == 200


# ---------------- imaging ----------------
def test_imaging_flow_and_permissions(client):
    doc, rad, nurse = login(client, "dr.hunt"), login(client, "dr.chen"), login(client, "nurse.olivia")
    pid = new_patient(client, "Scan")
    body = {"patient_id": pid, "modality": "ct", "body_part": "Abdomen", "priority": "urgent", "clinical_info": "RLQ pain"}
    assert client.post("/api/imaging", headers=rad, json=body).status_code == 403  # radiologists don't order
    r = client.post("/api/imaging", headers=doc, json=body)
    assert r.status_code == 201
    iid = r.json()["id"]

    assert client.post(f"/api/imaging/{iid}/report", headers=rad, json={"report": "Normal study."}).status_code == 409  # not performed yet
    slot = "2035-06-01T09:00:00"
    assert client.post(f"/api/imaging/{iid}/schedule", headers=rad, json={"scheduled_at": slot}).json()["status"] == "scheduled"
    # second CT within 30 minutes clashes; a different modality or later slot does not
    other = client.post("/api/imaging", headers=doc, json={**body, "body_part": "Chest"}).json()["id"]
    assert client.post(f"/api/imaging/{other}/schedule", headers=rad, json={"scheduled_at": "2035-06-01T09:15:00"}).status_code == 409
    assert client.post(f"/api/imaging/{other}/schedule", headers=rad, json={"scheduled_at": "2035-06-01T09:30:00"}).status_code == 200

    assert client.post(f"/api/imaging/{iid}/perform", headers=nurse).status_code == 403
    assert client.post(f"/api/imaging/{iid}/perform", headers=rad).json()["status"] == "performed"
    assert client.post(f"/api/imaging/{iid}/report", headers=doc, json={"report": "Acute appendicitis."}).status_code == 403
    r = client.post(f"/api/imaging/{iid}/report", headers=rad, json={"report": "Acute appendicitis, no perforation.", "critical": True})
    assert r.json()["status"] == "reported" and r.json()["critical"] and r.json()["radiologist_name"] == "Dr. Rae Chen"
    assert client.post(f"/api/imaging/{iid}/cancel", headers=doc).status_code == 409

    chart = client.get(f"/api/patients/{pid}/imaging", headers=doc).json()
    assert len(chart) == 2
    # STAT sorts first in the worklist
    client.post("/api/imaging", headers=doc, json={**body, "priority": "stat", "modality": "xray", "body_part": "Chest"})
    assert client.get("/api/imaging?status=ordered", headers=rad).json()[0]["priority"] == "stat"


def test_contrast_rules(client):
    doc = login(client, "dr.hunt")
    pid = new_patient(client, "Allergic", allergies="Iodine contrast")
    base = {"patient_id": pid, "modality": "ct", "body_part": "Chest", "contrast": True}
    r = client.post("/api/imaging", headers=doc, json=base)
    assert r.status_code == 409 and "Allergy" in r.json()["detail"]
    assert client.post("/api/imaging", headers=doc, json={**base, "override_allergy": True}).status_code == 201
    log = client.get("/api/audit", headers=login(client, "admin")).json()
    assert any(e["action"] == "WARN" and "contrast allergy override" in (e["detail"] or "") for e in log)
    assert client.post("/api/imaging", headers=doc, json={**base, "modality": "xray"}).status_code == 422


# ---------------- live updates ----------------
def test_ws_rejects_bad_token(client):
    with client.websocket_connect("/api/ws") as ws:
        ws.send_json({"type": "auth", "token": "garbage"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_ws_events_and_targeted_alerts(client):
    doc, rad = login(client, "dr.hunt"), login(client, "dr.chen")
    pid = new_patient(client, "Live")
    with client.websocket_connect("/api/ws") as ordering, client.websocket_connect("/api/ws") as bystander:
        ordering.send_json({"type": "auth", "token": token(client, "dr.hunt")})
        bystander.send_json({"type": "auth", "token": token(client, "bill.cole")})
        assert ordering.receive_json()["type"] == "hello" and bystander.receive_json()["type"] == "hello"

        # a committed write produces a topic event for everyone (no patient data in it)
        iid = client.post("/api/imaging", headers=doc, json={"patient_id": pid, "modality": "xray", "body_part": "Hand"}).json()["id"]
        for ws in (ordering, bystander):
            msg = ws.receive_json()
            assert msg == {"type": "event", "topics": ["imaging"]}

        client.post(f"/api/imaging/{iid}/perform", headers=rad)
        ordering.receive_json(); bystander.receive_json()

        # a critical report alerts only the ordering clinician
        client.post(f"/api/imaging/{iid}/report", headers=rad, json={"report": "Displaced fracture.", "critical": True})
        got = [ordering.receive_json(), ordering.receive_json()]
        assert {m["type"] for m in got} == {"event", "alert"}
        alert = next(m for m in got if m["type"] == "alert")
        assert alert["level"] == "critical" and "Hand" in alert["message"]
        assert bystander.receive_json()["type"] == "event"  # only the topic event, never the alert


def test_dashboard_phase2_stats(client):
    d = client.get("/api/dashboard", headers=login(client, "admin")).json()
    assert d["inpatients"] >= 2 and d["imaging_pending"] >= 1 and d["staff_on_duty"] >= 0


# ---------------- local-day filtering (tz_offset) ----------------
def test_day_filters_respect_client_timezone(client):
    h = login(client, "front.amy")
    doc = uid(client, h, "dr.webber")
    # 22:30 UTC on 1 Jan is 01:30 on 2 Jan in Nairobi (UTC+3 = 180 minutes)
    body = {"patient_id": 1, "doctor_id": doc, "start": "2036-01-01T22:30:00", "end": "2036-01-01T23:00:00", "reason": "Late slot"}
    assert client.post("/api/appointments", json=body, headers=h).status_code == 201
    ids = lambda q: [a["reason"] for a in client.get(f"/api/appointments?{q}", headers=h).json()]
    assert "Late slot" in ids("day=2036-01-02&tz_offset=180")       # local day 2 Jan
    assert "Late slot" not in ids("day=2036-01-01&tz_offset=180")
    assert "Late slot" in ids("day=2036-01-01")                      # default = UTC days (old behaviour)
    assert "Late slot" not in ids("day=2036-01-02")
    assert client.get("/api/appointments?day=2036-01-01&tz_offset=99999", headers=h).status_code == 422


def test_roster_coverage_uses_local_days(client):
    chief = login(client, "dr.webber")
    who = uid(client, chief, "dr.altman")
    # starts 23:00 UTC on 10 Mar = 02:00 on 11 Mar local
    assert client.post("/api/shifts", headers=chief, json={"user_id": who, "kind": "night", "unit": "OR",
                       "start": "2036-03-10T23:00:00", "end": "2036-03-11T09:00:00"}).status_code == 201
    night = lambda q: next(c for c in client.get(f"/api/shifts/coverage?{q}", headers=chief).json() if c["kind"] == "night")
    assert night("start=2036-03-11&days=1&tz_offset=180")["counts"]["doctor"] == 1
    assert night("start=2036-03-10&days=1&tz_offset=180")["counts"]["doctor"] == 0
    assert night("start=2036-03-10&days=1")["counts"]["doctor"] == 1  # UTC view


# ---------------- surgery roster warnings ----------------
def test_surgery_warns_when_not_rostered(client):
    chief = login(client, "dr.webber")
    staff = {u["username"]: u["id"] for u in client.get("/api/staff", headers=chief).json()}
    room = client.get("/api/operating-rooms", headers=chief).json()[0]["id"]
    base = {"patient_id": 1, "room_id": room, "surgeon_id": staff["dr.torres"], "procedure": "Hip repair"}

    # no shift for dr.torres on that date: booked anyway (non-blocking) but with a warning
    r = client.post("/api/surgeries", headers=chief, json={**base, "start": "2037-01-01T08:00:00", "end": "2037-01-01T10:00:00"})
    assert r.status_code == 201 and any("dr." not in w and "Torres" in w for w in r.json()["warnings"])
    # rostered for the whole window: no warning
    assert client.post("/api/shifts", headers=chief, json={"user_id": staff["dr.torres"], "kind": "day", "unit": "OR",
                       "start": "2037-01-02T06:00:00", "end": "2037-01-02T18:00:00"}).status_code == 201
    r = client.post("/api/surgeries", headers=chief, json={**base, "start": "2037-01-02T08:00:00", "end": "2037-01-02T10:00:00"})
    assert r.status_code == 201 and r.json()["warnings"] == []
    # warnings are only set on booking, not on later reads
    assert all(s["warnings"] == [] for s in client.get("/api/surgeries?day=2037-01-02", headers=chief).json())
