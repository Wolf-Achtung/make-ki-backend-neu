# websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live web search helpers (Perplexity Search API + Tavily) – Gold-Standard+
- Uses Perplexity *Search API* (no model parameter required)
- Uses Tavily with sane defaults
- Robust 429/5xx backoff with jitter
- Domain allowlist via env SEARCH_INCLUDE_DOMAINS="europa.eu,foerderdatenbank.de,..."
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import os, time, random
import httpx

from utils_sources import filter_and_rank

PPLX_BASE = "https://api.perplexity.ai"
TAVILY_URL = "https://api.tavily.com/search"

DEFAULT_TIMEOUT = float(os.getenv("LIVE_TIMEOUT", "20"))

def _split_domains(s: str) -> List[str]:
    parts = [p.strip() for p in (s or "").split(",") if p.strip()]
    return parts[:20]

def _post_with_backoff(url: str, json_payload: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    """POST with exponential backoff on 429/5xx. Returns {} on failure."""
    max_attempts = 5
    base_sleep = 0.6
    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=timeout) as cli:
                r = cli.post(url, headers=headers, json=json_payload)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    # retryable
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as e:
            if attempt >= max_attempts:
                return {}
            # server asked to back off; use jitter
            sleep_s = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            time.sleep(sleep_s)
            continue
        except Exception:
            if attempt >= max_attempts:
                return {}
            sleep_s = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
            time.sleep(sleep_s)
            continue
    return {}

def _normalize_results(items: List[Dict[str, Any]], max_results: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items[:max_results]:
        out.append({
            "title": it.get("title") or it.get("name") or it.get("url"),
            "url": it.get("url"),
            "domain": (it.get("domain") or (it.get("url","").split("/")[2] if "://" in (it.get("url") or "") else "")),
            "date": (it.get("date") or it.get("published_date") or it.get("last_updated") or "")[:10],
            "score": float(it.get("score") or 0.0)
        })
    return filter_and_rank(out)

def perplexity_search(query: str, max_results: int = 8, country: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Calls Perplexity Search API (no explicit model param).
    Supports domain allowlist via SEARCH_INCLUDE_DOMAINS.
    """
    api_key = (os.getenv("PERPLEXITY_API_KEY") or "").strip()
    if not api_key:
        return []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "query": query,
        "max_results": max(1, min(20, int(max_results))),
        "max_tokens_per_page": int(os.getenv("PPLX_MAX_TOKENS_PER_PAGE", "512")),
    }
    # domain filter (allowlist)
    allow = _split_domains(os.getenv("SEARCH_INCLUDE_DOMAINS", ""))
    if allow:
        payload["search_domain_filter"] = allow
    if country:
        payload["country"] = country  # ISO alpha-2
    data = _post_with_backoff(f"{PPLX_BASE}/search", payload, headers, DEFAULT_TIMEOUT)
    if not data:
        return []
    results = data.get("results") or []
    # results can be nested for multi-query; flatten
    if results and isinstance(results[0], list):
        flat: List[Dict[str, Any]] = []
        for block in results:
            flat.extend(block or [])
        results = flat
    return _normalize_results(results, max_results)

def tavily_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str, Any]]:
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not api_key:
        return []
    headers = {"Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "search_depth": os.getenv("SEARCH_DEPTH", "basic"),
    }
    # domain allowlist aligns with Perplexity
    allow = _split_domains(os.getenv("SEARCH_INCLUDE_DOMAINS", ""))
    if allow:
        payload["include_domains"] = allow
    if days:
        payload["days"] = int(days)
    data = _post_with_backoff(TAVILY_URL, payload, headers, DEFAULT_TIMEOUT)
    if not data:
        return []
    results = data.get("results") or []
    # map fields to our schema
    mapped = []
    for r in results[:max_results]:
        mapped.append({
            "title": r.get("title"),
            "url": r.get("url"),
            "domain": (r.get("url","").split("/")[2] if "://" in (r.get("url") or "") else ""),
            "date": (r.get("published_date") or "")[:10],
            "score": float(r.get("score") or 0.0),
        })
    return _normalize_results(mapped, max_results)
