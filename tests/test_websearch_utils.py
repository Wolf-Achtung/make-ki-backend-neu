# File: tests/test_websearch_utils.py
# -*- coding: utf-8 -*-
import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture()
def module_without_keys(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.setenv("LIVE_NEWS_DAYS", "7")
    monkeypatch.setenv("LIVE_FALLBACK_MAX_DAYS", "30")
    monkeypatch.setenv("LIVE_MAX_ITEMS", "5")
    if "websearch_utils" in globals():
        import sys as _sys
        _sys.modules.pop("websearch_utils", None)
    m = importlib.import_module("websearch_utils")
    return m


def test_build_live_sections_empty_without_keys(module_without_keys):
    m = module_without_keys
    out = m.build_live_sections({"branche": "Beratung & Dienstleistungen", "country": "DE", "region_code": "BE"})
    assert isinstance(out, dict)
    assert out["window_days"] in (7, 30)
    # Keine Keys -> keine Netz-Calls, aber Struktur steht
    assert "news" in out and "tools" in out and "funding" in out


def test_berlin_badge_detection(module_without_keys):
    m = module_without_keys
    assert m._is_berlin_funding("https://www.berlin.de/foerderung") is True
    assert m._is_berlin_funding("https://ibb.de/programm") is True
    assert m._is_berlin_funding("https://example.com/") is False
