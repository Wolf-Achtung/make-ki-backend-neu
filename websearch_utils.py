# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid web search utilities (Perplexity + Tavily) with 429 backoff & guards.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import os, time, random, httpx

from utils_sources import filter_and_rank

# Optional structured emitter
try:
    from live_logger import log_event as _emit  # type: ignore
except Exception:  # pragma: no cover
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        pass

# ---- Perplexity (prefer Search API) ----
from perplexity_client import search as pplx_search, chat_search as pplx_chat

def _backoff_sleep(i: int, base: float = 0.5, cap: float = 6.0) -> None:
    # exponential backoff with jitter
    import math, random
    t = min(cap, base * (2 ** i)) + random.uniform(0, 0.25)
    time.sleep(t)

def tavily_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    payload: Dict[str, Any] = {
        "api_key": key, "query": query, "max_results": int(max_results),
        "include_answer": False,
        "search_depth": os.getenv("SEARCH_DEPTH", "basic"),
    }
    if days:
        payload["days"] = int(days)
    url = "https://api.tavily.com/search"
    t0 = time.time()
    for i in range(3):
        try:
            with httpx.Client(timeout=float(os.getenv("TAVILY_TIMEOUT","20"))) as cli:
                r = cli.post(url, json=payload)
                if r.status_code == 429:
                    _emit("tavily", None, "429_backoff", int((time.time()-t0)*1000), count=0)
                    _backoff_sleep(i)
                    continue
                if r.status_code == 400 and i == 0:
                    # minimal retry without 'search_depth' (observed 400s)
                    payload_min = {k:v for k,v in payload.items() if k not in {"search_depth"}}
                    r = cli.post(url, json=payload_min)
                r.raise_for_status()
                data = r.json()
                items = []
                for hit in (data.get("results") or [])[:max_results]:
                    items.append({
                        "title": hit.get("title") or hit.get("url"),
                        "url": hit.get("url"),
                        "domain": hit.get("url").split("/")[2] if "://" in (hit.get("url") or "") else "",
                        "date": (hit.get("published_date") or "")[:10],
                        "provider": "tavily",
                    })
                _emit("tavily", None, "ok", int((time.time()-t0)*1000), count=len(items))
                return items
        except httpx.HTTPStatusError:
            _emit("tavily", None, "error:HTTPStatusError", int((time.time()-t0)*1000), count=0)
            _backoff_sleep(i)
        except Exception:
            _emit("tavily", None, "error:Exception", int((time.time()-t0)*1000), count=0)
            _backoff_sleep(i)
    return []

def perplexity_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    t0 = time.time()
    # Prefer Search API (no model); fall back to chat/completions only if needed
    items = pplx_search(query, top_k=max_results, days=days)
    if not items:
        items = pplx_chat(query, top_k=max_results)
    _emit("perplexity_adapter", None, "ok", int((time.time()-t0)*1000), count=len(items))
    return items

def perplexity_search_multi(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    """Run PPLX + Tavily, merge, dedupe & rank with include/exclude filters."""
    inc = os.getenv("SEARCH_INCLUDE_DOMAINS", "")
    exc = os.getenv("SEARCH_EXCLUDE_DOMAINS", "")
    items: List[Dict[str,Any]] = []
    try:
        items.extend(perplexity_search(query, max_results=max_results, days=days))
    except Exception:
        pass
    try:
        items.extend(tavily_search(query, max_results=max_results, days=days))
    except Exception:
        pass
    return filter_and_rank(items, include_domains=inc, exclude_domains=exc)
