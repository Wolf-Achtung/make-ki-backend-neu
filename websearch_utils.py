# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid Live-Search (Tavily + Perplexity) mit 429-Backoff, Dedupe und Domain-Filter.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
import os, time, httpx
from urllib.parse import urlparse

from utils_sources import filter_and_rank

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY","").strip()
PPLX_ENABLED = bool(os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY"))
SEARCH_INCLUDE = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_INCLUDE_DOMAINS") else []) if d.strip()]
SEARCH_DEPTH = os.getenv("SEARCH_DEPTH","basic")

def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""

def _backoff_sleep(i: int) -> None:
    time.sleep(min(0.25 * (2 ** i), 6.0))

def tavily_search(query: str, max_results: int = 6, days: Optional[int] = None) -> List[Dict[str,Any]]:
    if not TAVILY_API_KEY:
        return []
    payload = {"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results, "include_answer": False, "search_depth": SEARCH_DEPTH}
    if days: payload["days"] = int(days)
    out: List[Dict[str,Any]] = []
    try:
        with httpx.Client(timeout=15.0) as c:
            for i in range(4):
                r = c.post("https://api.tavily.com/search", json=payload)
                if r.status_code in (429,500,502,503,504):
                    _backoff_sleep(i); continue
                if r.status_code >= 400:
                    break
                data = r.json()
                for item in (data.get("results") or [])[: max_results * 2]:
                    url = item.get("url")
                    if not url: continue
                    dom = _domain(url)
                    if SEARCH_INCLUDE and not any(dom.endswith(d) or d in dom for d in SEARCH_INCLUDE):
                        # nicht strikt filtern – nur soft markieren
                        pass
                    out.append({
                        "title": item.get("title") or url,
                        "url": url,
                        "date": (item.get("published_date") or "")[:10],
                        "domain": dom,
                        "score": item.get("score")
                    })
                break
    except Exception:
        return []
    return out[: max_results * 2]

def perplexity_search(query: str, max_results: int = 6, days: Optional[int] = None) -> List[Dict[str,Any]]:
    if not PPLX_ENABLED:
        return []
    try:
        from perplexity_client import search as pplx_search  # type: ignore
    except Exception:
        return []
    out = pplx_search(query, max_results=max_results, days=days) or []
    return out[: max_results * 2]

def hybrid_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    t = tavily_search(query, max_results=max_results, days=days)
    p = perplexity_search(query, max_results=max_results, days=days)
    combined = (p or []) + (t or [])
    return filter_and_rank(combined)[:max_results]
