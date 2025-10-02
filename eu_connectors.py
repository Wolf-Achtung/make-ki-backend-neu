# File: eu_connectors.py
# -*- coding: utf-8 -*-
"""
EU‑Connectoren (Gold‑Standard+)

Schlanke, fehlertolerante Wrapper, die JSON normalisieren und niemals Exceptions
nach oben leaken. Diese Adapter können optional zusätzlich zu den direkten
Abfragen in `websearch_utils.py` verwendet werden (oder als Fallback).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
import httpx
import os
import time
import json

logger = logging.getLogger("eu_connectors")
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

DEFAULT_TIMEOUT = 20.0

# kleiner In‑Memory TTL‑Cache
_CACHE: Dict[str, tuple[float, Any]] = {}
def _cache_get(key: str, ttl: int) -> Optional[Any]:
    if ttl <= 0:
        return None
    now = time.time()
    v = _CACHE.get(key)
    if not v:
        return None
    exp, data = v
    if now <= exp:
        return data
    _CACHE.pop(key, None)
    return None

def _cache_set(key: str, value: Any, ttl: int) -> None:
    if ttl > 0:
        _CACHE[key] = (time.time() + ttl, value)

EU_TTL = int(os.getenv("EU_CACHE_TTL", "1200"))  # 20 min

def _http_get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    try:
        with httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT), follow_redirects=True) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.warning("EU API call failed: %s %s", url, exc)
        return None

def openaire_search_projects(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    key = f"openaire:{json.dumps([query, from_days, max_results])}"
    if (cached := _cache_get(key, EU_TTL)) is not None:
        return cached
    data = _http_get_json("https://api.openaire.eu/search/projects", params={"format": "json", "title": query})
    out: List[Dict[str, str]] = []
    for r in (data or {}).get("response", {}).get("results", {}).get("result", [])[: max_results]:
        md = r.get("metadata", {}).get("oaf:project", {})
        out.append({
            "title": md.get("title", {}).get("$", "") or f"OpenAIRE Project {md.get('code','')}",
            "url": md.get("websiteurl", ""),
            "snippet": "",
            "date": "",
        })
    _cache_set(key, out, EU_TTL)
    return out

def cordis_search_projects(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    key = f"cordis:{json.dumps([query, from_days, max_results])}"
    if (cached := _cache_get(key, EU_TTL)) is not None:
        return cached
    data = _http_get_json("https://cordis.europa.eu/api/projects", params={"q": query, "format": "json"})
    out: List[Dict[str, str]] = []
    for r in (data or {}).get("projects", [])[: max_results]:
        out.append({
            "title": r.get("title", ""),
            "url": r.get("rcn_url", "") or r.get("url", ""),
            "snippet": r.get("objective", ""),
            "date": r.get("startDate", ""),
        })
    _cache_set(key, out, EU_TTL)
    return out

def funding_tenders_search(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    """
    Allgemeiner Fallback über Tavily, falls die F&T‑API nicht nutzbar ist.
    Filtert auf EU‑Domains.
    """
    key = f"fts_fallback:{json.dumps([query, from_days, max_results])}"
    if (cached := _cache_get(key, EU_TTL)) is not None:
        return cached

    try:
        # relativ oder absolut importieren – was eben verfügbar ist
        try:
            from .websearch_utils import tavily_search  # type: ignore
        except Exception:
            from websearch_utils import tavily_search  # type: ignore
        hits = tavily_search(
            f'{query} site:ec.europa.eu OR site:europa.eu "call" OR "tenders"',
            days=from_days,
            include_domains=["ec.europa.eu", "europa.eu"],
            max_results=max_results,
        )
        out = [{"title": h.get("title",""), "url": h.get("url",""), "snippet": h.get("snippet",""), "date": h.get("published","")} for h in hits[:max_results]]
    except Exception as exc:
        logger.info("Tavily fallback not available for F&T: %s", exc)
        out = []

    _cache_set(key, out, EU_TTL)
    return out
