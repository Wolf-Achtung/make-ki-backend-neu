
# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live search aggregator (Tavily + Perplexity) with robust 429/5xx backoff and domain include filter.
Returns normalized list of dicts: {title, url, date, domain, score}
"""

from __future__ import annotations
from typing import Dict, List, Optional
import os, time, random, json
import httpx
import logging

try:
    from .perplexity_client import PerplexityClient  # type: ignore
except Exception:  # pragma: no cover
    from perplexity_client import PerplexityClient  # type: ignore

try:
    from .utils_sources import filter_and_rank  # type: ignore
except Exception:  # pragma: no cover
    from utils_sources import filter_and_rank  # type: ignore

# optional logger
try:
    from .live_logger import log_event as _emit  # type: ignore
except Exception:  # pragma: no cover
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw):
        pass

log = logging.getLogger("live_layer")

TAVILY_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
TAVILY_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "basic")

def _sleep_backoff(attempt: int, base: float = 0.35, cap: float = 6.0):
    # exponential backoff with jitter
    delay = min(cap, base * (2 ** attempt)) * (0.8 + random.random() * 0.4)
    time.sleep(delay)

def _augment_query(query: str) -> str:
    incl = (os.getenv("SEARCH_INCLUDE_DOMAINS") or "").strip()
    if not incl:
        return query
    parts = [d.strip() for d in incl.split(",") if d.strip()]
    if not parts:
        return query
    # site:domain1 OR site:domain2 ...
    site_filter = " OR ".join([f"site:{d}" for d in parts])
    return f"({query}) ({site_filter})"

def _normalize(results: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for it in results or []:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        dom = url.split("/")[2] if "://" in url else ""
        out.append({
            "title": it.get("title") or url,
            "url": url,
            "date": it.get("date") or it.get("published_date") or it.get("published_at") or "",
            "domain": dom.lower(),
            "score": int(it.get("score") or 0)
        })
    return out

def tavily_search(query: str, max_results: int = 6, days: Optional[int] = None) -> List[Dict]:
    if not TAVILY_KEY:
        return []
    q = _augment_query(query)
    payload = {
        "api_key": TAVILY_KEY,
        "query": q,
        "max_results": max_results,
        "include_answer": False,
        "search_depth": TAVILY_DEPTH
    }
    if days:
        payload["days"] = days

    attempt = 0
    start = time.time()
    while attempt < 3:
        try:
            with httpx.Client(timeout=15.0) as cli:
                r = cli.post("https://api.tavily.com/search", json=payload)
                if r.status_code == 200:
                    data = r.json() or {}
                    items = data.get("results", [])[:max_results]
                    res = [{"title": it.get("title"), "url": it.get("url"), "date": it.get("published_date"), "score": it.get("score")} for it in items]
                    out = filter_and_rank(_normalize(res))
                    _emit("tavily", None, "ok", int((time.time()-start)*1000), count=len(out))
                    return out
                elif r.status_code == 429:
                    _emit("tavily", None, "429", int((time.time()-start)*1000), count=0)
                    attempt += 1
                    _sleep_backoff(attempt)
                    # minimal query retry: strip filters
                    if attempt == 1:
                        payload.pop("days", None)
                        payload["search_depth"] = "basic"
                    continue
                elif 500 <= r.status_code < 600:
                    attempt += 1
                    _emit("tavily", None, f"{r.status_code}", int((time.time()-start)*1000), count=0)
                    _sleep_backoff(attempt)
                    continue
                else:
                    _emit("tavily", None, f"{r.status_code}", int((time.time()-start)*1000), count=0)
                    return []
        except Exception as exc:  # pragma: no cover
            _emit("tavily", None, f"error:{type(exc).__name__}", int((time.time()-start)*1000), count=0)
            attempt += 1
            _sleep_backoff(attempt)

    return []

def perplexity_search(query: str, max_results: int = 6) -> List[Dict]:
    key = (os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY") or "").strip()
    if not key:
        return []
    q = _augment_query(query)
    model = (os.getenv("PPLX_MODEL") or "").strip()
    start = time.time()
    try:
        client = PerplexityClient(api_key=key, model=model, timeout=12.0)
        res = client.search(q, max_results=max_results) or []
        out = filter_and_rank(_normalize(res))
        _emit("perplexity", (model or "auto"), "ok" if out else "ok_empty", int((time.time()-start)*1000), count=len(out))
        return out
    except Exception as exc:  # pragma: no cover
        _emit("perplexity", (model or "auto"), f"error:{type(exc).__name__}", int((time.time()-start)*1000), count=0)
        return []
