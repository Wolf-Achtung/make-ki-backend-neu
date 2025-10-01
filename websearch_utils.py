# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Tavily-Wrapper mit Domain-Whitelist, Zeitfenster & robustem Fallback
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List

import httpx

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("websearch_utils")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
SEARCH_DEPTH = os.getenv("SEARCH_DEPTH", "advanced")
TIMEOUT = float(os.getenv("SEARCH_TIMEOUT", "20"))

def days_to_tavily_range(days: int) -> str:
    # Tavily versteht "d7", "d30", "d60", "m6" etc.
    if days <= 7:
        return "d7"
    if days <= 30:
        return "d30"
    if days <= 60:
        return "d60"
    return "m6"

def tavily_search(query: str, days: int = 30, include_domains: List[str] | None = None,
                  exclude_domains: List[str] | None = None, max_results: int = 8) -> List[Dict[str, str]]:
    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY fehlt – leere Ergebnisliste.")
        return []
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": SEARCH_DEPTH,
        "include_domains": include_domains or [],
        "exclude_domains": exclude_domains or [],
        "max_results": max_results,
        "time_range": days_to_tavily_range(days),
        "topic": "news",
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json() or {}
            results = data.get("results") or data.get("news") or []
            out = []
            for r in results:
                out.append({
                    "title": r.get("title") or r.get("name"),
                    "url": r.get("url") or r.get("link"),
                    "snippet": r.get("snippet") or r.get("content") or "",
                    "published": r.get("published_date") or r.get("date") or "",
                })
            return out
    except Exception as e:
        logger.error("Tavily-Fehler: %s", e)
        return []
