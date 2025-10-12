# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid Live‑Layer (Perplexity + Tavily) mit hartem 429‑Backoff und Domain‑Filter.
- perplexity_search(query, max_results=8)
- tavily_search(query, max_results=8, days=None)
Die Funktionen geben normalisierte Dict‑Listen zurück: {title,url,domain,date,score}.
"""
from __future__ import annotations

import os, time, random
from typing import Any, Dict, List, Optional

import httpx

from utils_sources import filter_and_rank
from perplexity_client import PerplexityClient

INCLUDE_DOMAINS = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_INCLUDE_DOMAINS") else []) if d.strip()]
TAVILY_KEY = os.getenv("TAVILY_API_KEY","").strip()
TAVILY_TIMEOUT = float(os.getenv("TAVILY_TIMEOUT","18.0"))
TAVILY_SEARCH_DEPTH = os.getenv("SEARCH_DEPTH","basic")
MAX_RETRIES = int(os.getenv("LIVE_MAX_RETRIES","3"))

def _backoff(attempt: int) -> None:
    base = 0.8 * (2 ** attempt)
    time.sleep(base + random.random() * 0.5)

def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set(); out: List[Dict[str, Any]] = []
    for it in items:
        url = (it.get("url") or "").split("#")[0]
        if not url or url in seen: 
            continue
        seen.add(url)
        out.append(it)
    return out

def perplexity_search(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    cli = PerplexityClient()
    if not cli.key:
        return []
    items: List[Dict[str, Any]] = []
    for attempt in range(MAX_RETRIES):
        try:
            res = cli.search(query, top_k=max_results, include_domains=INCLUDE_DOMAINS)
            items = res or []
            break
        except Exception:
            _backoff(attempt)
    return filter_and_rank(_dedupe(items))[:max_results]

def tavily_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str, Any]]:
    if not TAVILY_KEY:
        return []
    payload: Dict[str, Any] = {
        "api_key": TAVILY_KEY,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "search_depth": TAVILY_SEARCH_DEPTH,
    }
    if days is not None:
        payload["days"] = int(days)

    items: List[Dict[str, Any]] = []
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=TAVILY_TIMEOUT) as c:
                r = c.post("https://api.tavily.com/search", json=payload)
                if r.status_code == 429:
                    _backoff(attempt); 
                    continue
                if r.status_code == 400 and attempt == 0:
                    # auto‑downgrade: minimal payload
                    payload_min = {"api_key": TAVILY_KEY, "query": query, "max_results": max_results}
                    r = c.post("https://api.tavily.com/search", json=payload_min)
                r.raise_for_status()
                data = r.json() or {}
                for it in data.get("results", [])[:max_results]:
                    url = it.get("url")
                    items.append({
                        "title": it.get("title") or url,
                        "url": url,
                        "content": it.get("content"),
                        "date": it.get("published_date") or it.get("date") or "",
                        "score": it.get("score") or 0.0,
                        "domain": (url.split('/')[2] if url and '://' in url else "")
                    })
                break
        except Exception:
            _backoff(attempt)
            continue
    # Domain‑Filter (soft): wenn INCLUDE_DOMAINS gesetzt, priorisiere diese
    if INCLUDE_DOMAINS:
        pref = [it for it in items if any(d in (it.get("domain") or "") for d in INCLUDE_DOMAINS)]
        rest = [it for it in items if it not in pref]
        items = pref + rest
    return filter_and_rank(_dedupe(items))[:max_results]
