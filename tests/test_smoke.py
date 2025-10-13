# filename: tests/test_smoke.py
from fastapi.testclient import TestClient
from backend.main import app

def test_healthz():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_login_json():
    c = TestClient(app)
    r = c.post("/api/login", json={"email": "test@example.com", "password": "x"})
    assert r.status_code == 200
    assert "token" in r.json()
