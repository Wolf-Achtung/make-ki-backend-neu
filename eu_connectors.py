# filename: eu_connectors.py
# -*- coding: utf-8 -*-
"""
Einfache, fehlertolerante EU-Connectoren.
Hinweise:
- Endpunkte können sich ändern; Code fängt HTTP/Schemafehler robust ab.
- Ergebnisse sind auf die im Report verwendeten Felder gemappt (title, url, date, summary).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import httpx


def _http_get_json(url: str, params: Optional[Dict[str, str]] = None, timeout: float = 20.0):
    with httpx.Client(timeout=timeout) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()


def _clip(s: str, n: int = 280) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def openaire_search_projects(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    """
    OpenAIRE (public search). Schema variiert, wir mappen defensiv.
    """
    try:
        base = "https://api.openaire.eu/search/projects"
        params = {"format": "json", "size": str(max_results), "title": query}
        data = _http_get_json(base, params=params)
        items = data.get("response", {}).get("results", []) or data.get("results", []) or []
        out: List[Dict[str, str]] = []
        for it in items[:max_results]:
            title = it.get("title") or it.get("name") or ""
            url = it.get("url") or it.get("link") or ""
            start = it.get("startdate") or it.get("startDate") or ""
            abs_ = it.get("objective") or it.get("summary") or it.get("description") or ""
            out.append({"title": title, "url": url, "date": start, "summary": _clip(abs_)})
        return out
    except Exception:
        return []


def cordis_search_projects(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    """
    CORDIS API (EU-Forschung). Defensive Feld-Mappings.
    """
    try:
        base = "https://cordis.europa.eu/api/projects"
        params = {"search": query, "format": "json", "limit": str(max_results)}
        data = _http_get_json(base, params=params)
        items = data.get("projects", []) or data.get("result", []) or []
        out: List[Dict[str, str]] = []
        for it in items[:max_results]:
            title = it.get("title") or it.get("acronym") or ""
            url = it.get("rcn_url") or it.get("url") or ""
            date = it.get("startDate") or it.get("startdate") or ""
            sum_ = it.get("objective") or it.get("summary") or it.get("description") or ""
            out.append({"title": title, "url": url, "date": date, "summary": _clip(sum_)})
        return out
    except Exception:
        return []


def funding_tenders_search(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    """
    Funding & Tenders (EU Portal).
    """
    try:
        base = "https://ec.europa.eu/info/funding-tenders/opportunities/api/search"
        since = (datetime.utcnow() - timedelta(days=from_days)).date().isoformat()
        params = {"text": query, "programme": "", "type": "call", "modifiedFrom": since, "limit": str(max_results)}
        data = _http_get_json(base, params=params)
        items = data.get("items", []) or data.get("data", []) or []
        out: List[Dict[str, str]] = []
        for it in items[:max_results]:
            title = it.get("title") or it.get("identifier") or ""
            url = it.get("url") or it.get("permalink") or ""
            date = it.get("deadline") or it.get("publicationDate") or ""
            sum_ = it.get("objective") or it.get("summary") or it.get("description") or ""
            out.append({"title": title, "url": url, "date": date, "summary": _clip(sum_)})
        return out
    except Exception:
        return []
