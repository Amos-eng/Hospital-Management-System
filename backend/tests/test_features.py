"""Small features added after phase 2."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test3.db")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import DEMO_PASSWORD


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username, password=DEMO_PASSWORD):
    r = client.post("/api/auth/login", data={"username": username, "password": password})
    return r


def auth(client, username):
    r = login(client, username)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_user(client, username, role="nurse", password="Temp-Pass-123"):
    admin = auth(client, "admin")
    r = client.post("/api/staff", headers=admin, json={"username": username, "full_name": f"Test {username}", "password": password, "role": role})
    assert r.status_code == 201, r.text
    return password


# ---------- change password ----------
def test_change_password(client):
    pw = make_user(client, "pw.user")
    h = {"Authorization": f"Bearer {login(client, 'pw.user', pw).json()['access_token']}"}
    url = "/api/auth/change-password"
    assert client.post(url, headers=h, json={"current_password": "wrong-wrong", "new_password": "New-Pass-456"}).status_code == 400
    assert client.post(url, headers=h, json={"current_password": pw, "new_password": pw}).status_code == 422
    assert client.post(url, headers=h, json={"current_password": pw, "new_password": "short"}).status_code == 422
    assert client.post(url, headers=h, json={"current_password": pw, "new_password": "New-Pass-456"}).status_code == 204
    assert login(client, "pw.user", pw).status_code == 401           # old password no longer works
    assert login(client, "pw.user", "New-Pass-456").status_code == 200
    assert client.post(url, json={"current_password": pw, "new_password": "New-Pass-456"}).status_code == 401  # needs a token
    log = client.get("/api/audit", headers=auth(client, "admin")).json()
    assert any(e["username"] == "pw.user" and e["detail"] == "password changed" for e in log)


# ---------- login throttling ----------
def test_login_lockout_and_recovery(client):
    from app import security
    pw = make_user(client, "lock.user")
    clock = [1000.0]
    real = security.throttle._now
    security.throttle._now = lambda: clock[0]
    try:
        for _ in range(5):
            assert login(client, "lock.user", "wrong-password").status_code == 401
        r = login(client, "lock.user", pw)                      # correct password, but locked
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
        assert "minute" in r.json()["detail"]
        assert login(client, "pw.user", "x").status_code in (401, 429) and login(client, "admin").status_code == 200  # others unaffected
        clock[0] += 15 * 60 + 5                                   # window passes
        assert login(client, "lock.user", pw).status_code == 200
        # a success resets the counter: 4 more failures do not lock
        for _ in range(4):
            login(client, "lock.user", "wrong-password")
        assert login(client, "lock.user", pw).status_code == 200
        # unknown usernames are throttled too, with the same response shape
        for _ in range(5):
            assert login(client, "nobody.here", "x").status_code == 401
        assert login(client, "nobody.here", "x").status_code == 429
    finally:
        security.throttle._now = real


# ---------- audit CSV export ----------
def test_csv_safe_blocks_formula_injection():
    from app.csvutil import csv_safe, to_csv
    assert csv_safe("=HYPERLINK(\"http://evil\")") == "'=HYPERLINK(\"http://evil\")"
    assert csv_safe("+1") == "'+1" and csv_safe("-2") == "'-2" and csv_safe("@x") == "'@x"
    assert csv_safe("normal") == "normal" and csv_safe(None) == "" and csv_safe(5) == "5"
    out = to_csv(["a", "b"], [["x,y", 'say "hi"']])
    assert out == 'a,b\r\n"x,y","say ""hi"""\r\n'


def test_audit_csv_export(client):
    admin = auth(client, "admin")
    r = client.get("/api/audit.csv?limit=50", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and "audit-log.csv" in r.headers["content-disposition"]
    lines = r.text.strip().split("\r\n")
    assert lines[0] == "id,at_utc,username,action,entity,entity_id,detail" and len(lines) > 1
    only = client.get("/api/audit.csv?action=login&username=admin", headers=admin).text.strip().split("\r\n")
    assert len(only) > 1 and all(",admin,LOGIN," in l for l in only[1:])
    assert client.get("/api/audit.csv?limit=0", headers=admin).status_code == 422
    assert client.get("/api/audit.csv", headers=auth(client, "dr.webber")).status_code == 403
    assert client.get("/api/audit.csv").status_code == 401
    # exporting is itself audited
    log = client.get("/api/audit", headers=admin).json()
    assert any(e["entity"] == "audit_export" for e in log)
