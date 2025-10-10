
import json
from pathlib import Path

import pytest

# Import the module directly from repo layout
import importlib.util, sys, os
BASE = Path(__file__).resolve().parents[2] / "make-ki-backend-neu-main" / "make-ki-backend-neu-main"
sys.path.insert(0, str(BASE))

ga = importlib.import_module("gpt_analyze")

def test_normalize_briefing_minimal():
    raw = {
        "branche": "beratung",
        "unternehmensgroesse": "10-49",
        "bundesland_code": "BE",
        "hauptleistung": "KI-Beratung",
        "pull_kpis": {
            "digitalisierung": 50, "automatisierung": 40, "compliance": 60, "prozessreife": 55, "innovation": 65
        }
    }
    norm = ga.normalize_briefing(raw, lang="de")
    assert norm.branche in {"beratung", "Beratung", "consulting"}
    assert 0 <= norm.kpi_digitalisierung <= 100
    assert norm.hauptleistung

def test_compute_scores_delta_signs():
    raw = {
        "branche": "beratung",
        "unternehmensgroesse": "10-49",
        "bundesland_code": "BE",
        "hauptleistung": "KI-Beratung",
        "pull_kpis": {"digitalisierung": 80, "automatisierung": 50, "compliance": 60, "prozessreife": 40, "innovation": 30}
    }
    norm = ga.normalize_briefing(raw, lang="de")
    score = ga.compute_scores(norm)
    # Sanity: structure present
    assert "digitalisierung" in score.kpis
    # Delta defined and numeric
    for k, v in score.kpis.items():
        assert isinstance(v["delta"], float)
    # Total within [0,100]
    assert 0 <= score.total <= 100
