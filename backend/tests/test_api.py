import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

import pytest
from fastapi.testclient import TestClient

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


def test_auth_required_and_bad_login(client):
    assert client.get("/api/patients").status_code == 401
    r = client.post("/api/auth/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_rbac(client):
    billing = login(client, "bill.cole")
    assert client.get("/api/patients/1/notes", headers=billing).status_code == 403
    nurse = login(client, "nurse.olivia")
    assert client.post("/api/patients/1/notes", json={"text": "x"}, headers=nurse).status_code == 403
    doc = login(client, "dr.grey")
    assert client.post("/api/patients/1/notes", json={"text": "Stable."}, headers=doc).status_code == 201
    assert client.get("/api/patients/1/notes", headers=nurse).json()[0]["author_name"] == "Dr. Meredith Grey"


def test_register_patient_and_audit(client):
    h = login(client, "front.amy")
    r = client.post("/api/patients", headers=h, json={"first_name": "Test", "last_name": "Person",
                                                       "dob": "2000-01-01", "sex": "male"})
    assert r.status_code == 201 and r.json()["mrn"].startswith("MRN")
    admin = login(client, "admin")
    log = client.get("/api/audit", headers=admin).json()
    assert any(e["entity"] == "patient" and e["action"] == "CREATE" for e in log)
    assert client.get("/api/audit", headers=h).status_code == 403


def test_appointment_conflict(client):
    h = login(client, "front.amy")
    staff = client.get("/api/staff", headers=h).json()
    doc = next(u for u in staff if u["username"] == "dr.webber")
    body = {"patient_id": 1, "doctor_id": doc["id"], "start": "2030-01-01T09:00:00",
            "end": "2030-01-01T09:30:00", "reason": "Checkup"}
    assert client.post("/api/appointments", json=body, headers=h).status_code == 201
    body2 = {**body, "patient_id": 2, "start": "2030-01-01T09:15:00", "end": "2030-01-01T09:45:00"}
    assert client.post("/api/appointments", json=body2, headers=h).status_code == 409
    body3 = {**body, "start": "2030-01-01T10:00:00", "end": "2030-01-01T09:00:00"}
    assert client.post("/api/appointments", json=body3, headers=h).status_code == 422


def test_er_flow(client):
    h = login(client, "dr.hunt")
    board = client.get("/api/er", headers=h).json()
    assert [v["triage_level"] for v in board] == sorted(v["triage_level"] for v in board)
    waiting = next(v for v in board if v["status"] == "waiting")
    beds = client.get("/api/beds?ward=ER", headers=h).json()
    free = next(b for b in beds if not b["occupied"])
    taken = next(b for b in beds if b["occupied"])
    me = client.get("/api/auth/me", headers=h).json()
    assert client.post(f"/api/er/{waiting['id']}/assign", json={"bed_id": taken["id"]}, headers=h).status_code == 409
    r = client.post(f"/api/er/{waiting['id']}/assign", json={"bed_id": free["id"], "attending_id": me["id"]}, headers=h)
    assert r.json()["status"] == "in_treatment"
    r = client.post(f"/api/er/{waiting['id']}/close", json={"status": "discharged"}, headers=h)
    assert r.status_code == 200
    assert next(b for b in client.get("/api/beds", headers=h).json() if b["id"] == free["id"])["occupied"] is False


def test_surgery_conflicts(client):
    h = login(client, "dr.bailey")
    staff = {u["username"]: u["id"] for u in client.get("/api/staff", headers=h).json()}
    rooms = client.get("/api/operating-rooms", headers=h).json()
    base = {"patient_id": 1, "room_id": rooms[3]["id"], "surgeon_id": staff["dr.bailey"],
            "procedure": "Appendectomy", "start": "2031-05-01T08:00:00", "end": "2031-05-01T10:00:00"}
    assert client.post("/api/surgeries", json=base, headers=h).status_code == 201
    # same room
    r = client.post("/api/surgeries", json={**base, "surgeon_id": staff["dr.grey"]}, headers=h)
    assert r.status_code == 409 and "room" in r.json()["detail"].lower()
    # same surgeon, different room
    r = client.post("/api/surgeries", json={**base, "room_id": rooms[2]["id"]}, headers=h)
    assert r.status_code == 409 and "surgeon" in r.json()["detail"].lower()
    # busy team member
    r = client.post("/api/surgeries", json={**base, "room_id": rooms[2]["id"], "surgeon_id": staff["dr.grey"],
                                            "team": [{"user_id": staff["dr.bailey"], "role": "assistant"}]}, headers=h)
    assert r.status_code == 409
    # non-overlapping works
    r = client.post("/api/surgeries", json={**base, "start": "2031-05-01T10:00:00", "end": "2031-05-01T12:00:00"}, headers=h)
    assert r.status_code == 201


def test_pharmacy_stock_and_allergy(client):
    doc, ph = login(client, "dr.webber"), login(client, "pharm.lee")
    drugs = {d["name"]: d for d in client.get("/api/drugs", headers=ph).json()}
    pcm = drugs["Paracetamol 500mg"]
    r = client.post("/api/prescriptions", headers=doc, json={"patient_id": 2, "drug_id": pcm["id"], "dosage": "1 tab", "quantity": 10})
    rid = r.json()["id"]
    assert client.post(f"/api/prescriptions/{rid}/dispense", headers=ph).json()["status"] == "dispensed"
    assert client.post(f"/api/prescriptions/{rid}/dispense", headers=ph).status_code == 409
    after = next(d for d in client.get("/api/drugs", headers=ph).json() if d["id"] == pcm["id"])
    assert after["stock"] == pcm["stock"] - 10
    # patient 7 (Sofia) is allergic to Aspirin
    asp = drugs["Aspirin 75mg"]
    rid = client.post("/api/prescriptions", headers=doc, json={"patient_id": 7, "drug_id": asp["id"], "dosage": "1", "quantity": 5}).json()["id"]
    assert client.post(f"/api/prescriptions/{rid}/dispense", headers=ph).status_code == 409
    # insufficient stock
    big = client.post("/api/prescriptions", headers=doc, json={"patient_id": 2, "drug_id": drugs["Morphine 10mg/ml"]["id"], "dosage": "x", "quantity": 9999}).json()["id"]
    assert client.post(f"/api/prescriptions/{big}/dispense", headers=ph).status_code == 409


def test_lab_workflow(client):
    doc, lab = login(client, "dr.hunt"), login(client, "lab.tran")
    lid = client.post("/api/labs", headers=doc, json={"patient_id": 3, "test_name": "CBC"}).json()["id"]
    assert client.post(f"/api/labs/{lid}/result", headers=lab, json={"result": "ok"}).status_code == 409
    assert client.post(f"/api/labs/{lid}/collect", headers=lab).status_code == 200
    r = client.post(f"/api/labs/{lid}/result", headers=lab, json={"result": "WBC 15.2", "abnormal": True})
    assert r.json()["status"] == "resulted" and r.json()["abnormal"] is True


def test_billing(client):
    b = login(client, "bill.cole")
    inv = client.post("/api/invoices", headers=b, json={"patient_id": 1, "items": [
        {"description": "Consult", "quantity": 2, "unit_price": 50}]}).json()
    assert inv["total"] == 100 and inv["balance"] == 100
    assert client.post(f"/api/invoices/{inv['id']}/pay", headers=b, json={"amount": 150, "method": "cash"}).status_code == 422
    r = client.post(f"/api/invoices/{inv['id']}/pay", headers=b, json={"amount": 40, "method": "card"}).json()
    assert r["status"] == "open" and r["balance"] == 60
    r = client.post(f"/api/invoices/{inv['id']}/pay", headers=b, json={"amount": 60, "method": "insurance"}).json()
    assert r["status"] == "paid" and r["balance"] == 0
    assert client.post(f"/api/invoices/{inv['id']}/void", headers=b).status_code == 409


def test_dashboard(client):
    d = client.get("/api/dashboard", headers=login(client, "admin")).json()
    assert d["beds_total"] == 22 and d["patients"] >= 8
