
import os, sys
from pathlib import Path

import importlib
import importlib.util

import pytest
from fastapi.testclient import TestClient

# Ensure repo base on sys.path
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

# Import main app and attach observability (auto-attach tries to import main.app)
observability = importlib.import_module("app.observability")

main_mod = importlib.import_module("main")
app = getattr(main_mod, "app", None)
assert app is not None, "FastAPI app not found in main.py"

client = TestClient(app)

def test_healthz_contains_versions():
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "schema" in data and "prompts" in data

def test_metrics_prometheus_format():
    # Make one request to have something in the counters
    client.get("/")
    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text
    assert "http_requests_total" in text
    assert "app_build_info" in text
