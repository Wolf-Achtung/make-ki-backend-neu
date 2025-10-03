# File: tests/test_live_search_smoke.py
# -*- coding: utf-8 -*-
import os
from websearch_utils import query_live_items

def test_live_search_shape_minimum(monkeypatch):
    # Kein echter Netztest; nur Form/Keys prüfen (Provider ohne Keys -> leere Listen)
    monkeypatch.setenv("SEARCH_PROVIDER", "hybrid")
    monkeypatch.setenv("LIVE_CACHE_ENABLED", "true")
    monkeypatch.setenv("ENABLE_CASE_STUDIES", "true")
    monkeypatch.setenv("ENABLE_REGULATORY", "true")

    res = query_live_items(
        branche="Beratung",
        unternehmensgroesse="solo",
        leistung="GPT-Auswertung",
        bundesland="BE",
        lang="de",
    )
    # Kernkanäle
    assert isinstance(res, dict)
    for key in ("news", "tools", "funding"):
        assert key in res and isinstance(res[key], list)
    # Erweiterungen
    for key in ("case_studies", "regulatory", "vendor_shortlist", "tool_alternatives"):
        assert key in res  # können leere Listen sein
