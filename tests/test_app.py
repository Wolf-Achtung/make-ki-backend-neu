from fastapi.testclient import TestClient
from main import app

def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200 and r.json().get("status") == "ok"

def test_report_basic():
    c = TestClient(app)
    r = c.post("/api/report", json={"language":"de","company":"Muster AG","industry":"Finanzen","include_news":False,"format":"html"})
    assert r.status_code == 200
    data = r.json()
    assert data["language"] == "de"
    assert "html" in data and data["html"]
