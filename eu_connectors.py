# filename: eu_connectors.py
# -*- coding: utf-8 -*-
"""
EU-Datenquellen (best-effort, robust gegen API-Änderungen).
Alle Funktionen liefern kurze, homogene Diktlisten mit Feldern: title/url/summary/date
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List

import httpx

logger = logging.getLogger("eu_connectors")

TIMEOUT = 20.0

def _days_ago_iso(days: int) -> str:
    return (datetime.utcnow() - timedelta(days=days)).date().isoformat()

def openaire_search_projects(query: str, from_days: int = 60, size: int = 8) -> List[Dict[str, str]]:
    try:
        base = "https://api.openaire.eu/search/projects"
        params = {"format": "json", "pagesize": str(size), "fp7": "false", "query": query}
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(base, params=params)
            r.raise_for_status()
            data = r.json()
            projects = (data.get("response", {}).get("results", {}).get("result") or [])
            out = []
            for p in projects:
                md = p.get("metadata", {})
                title = (md.get("title", {}) or {}).get("$", "OpenAIRE-Projekt")
                date = (md.get("dateofcollection", {}) or {}).get("$", "")
                link = ""
                if md.get("pid"):
                    link = md["pid"][0].get("$")
                out.append({"title": title, "url": link, "summary": "", "date": date})
            return out
    except Exception as e:
        logger.warning("OpenAIRE error: %s", e)
        return []

def cordis_search_projects(query: str, from_days: int = 60, size: int = 8) -> List[Dict[str, str]]:
    try:
        # CORDIS hat mehrere Varianten; diese Endpoint-Auswahl ist best-effort
        base = "https://cordis.europa.eu/api/projects"
        params = {"page": "1", "size": str(size), "searchText": query}
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(base, params=params)
            r.raise_for_status()
            data = r.json()
            items = data.get("projects", []) if isinstance(data, dict) else []
            out = []
            for it in items:
                out.append({
                    "title": it.get("title", "CORDIS-Projekt"),
                    "url": it.get("rcn", ""),
                    "summary": it.get("objective", ""),
                    "date": it.get("startDate", ""),
                })
            return out
    except Exception as e:
        logger.warning("CORDIS error: %s", e)
        return []

def funding_tenders_search(query: str, from_days: int = 60, size: int = 8) -> List[Dict[str, str]]:
    try:
        base = "https://ec.europa.eu/info/funding-tenders/opportunities/data/reference/opportunities/search"
        params = {"page": "0", "pageSize": str(size), "sort": "publicationDate,desc", "text": query}
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(base, params=params)
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            out = []
            for it in items:
                title = it.get("title", "EU Call")
                url = "https://ec.europa.eu/info/funding-tenders/opportunities/portal"  # Fallback
                summary = it.get("programme", "")
                date = it.get("publicationDate", "")
                out.append({"title": title, "url": url, "summary": summary, "date": date})
            return out
    except Exception as e:
        logger.warning("F&T error: %s", e)
        return []
