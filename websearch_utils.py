
# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live search utilities with robust 429 backoff (Gold-Standard+)
- tavily_search(query, max_results=8, days=30)
- perplexity_search(query, max_results=8, days=None)
Both return a list of dicts: {title, url, domain, date, score}
"""

from __future__ import annotations

import os, time, random, json
from typing import Any, Dict, List, Optional
import httpx

# structured event logger (optional)
try:
    from live_logger import log_event as _emit  # type: ignore
except Exception:
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        pass

from utils_sources import filter_and_rank

HTTP_TIMEOUT = float(os.getenv("LIVE_HTTP_TIMEOUT", "15"))
TAVILY_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
PPLX_KEY = (os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY") or "").strip()
SEARCH_INCLUDE = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS") or "").split(",") if d.strip()]

def _should_keep(url: str) -> bool:
    if not SEARCH_INCLUDE:
        return True
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0]
    except Exception:
        host = url
    return any(host.endswith(d) for d in SEARCH_INCLUDE)

def _backoff_sleep(attempt: int, base: float = 0.6, cap: float = 8.0) -> None:
    # full jitter
    wait = min(cap, base * (2 ** (attempt - 1)))
    time.sleep(random.uniform(0, wait))

def _safe_post(url: str, headers: Dict[str,str], payload: Dict[str,Any], provider: str, max_attempts: int = 4) -> Optional[httpx.Response]:
    start = time.time()
    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as cli:
                r = cli.post(url, headers=headers, json=payload)
            if r.status_code == 429:
                _emit(provider, None, "429", int((time.time()-start)*1000), 0)
                _backoff_sleep(attempt)
                continue
            if r.status_code >= 400:
                _emit(provider, None, f"{r.status_code}_bad_request", int((time.time()-start)*1000), 0)
                # specific handling for Perplexity invalid model
                try:
                    data = r.json()
                    if data and isinstance(data, dict) and "error" in data:
                        # we'll just continue; caller will try fallback
                        pass
                except Exception:
                    pass
                if attempt < max_attempts:
                    _backoff_sleep(attempt)
                    continue
                return r
            _emit(provider, None, "ok", int((time.time()-start)*1000), 0)
            return r
        except httpx.HTTPError:
            if attempt < max_attempts:
                _backoff_sleep(attempt)
                continue
            return None
    return None

def tavily_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    if not TAVILY_KEY:
        return []
    payload: Dict[str, Any] = {
        "api_key": TAVILY_KEY,
        "query": query,
        "max_results": max(1, int(max_results)),
        "include_answer": False,
        "search_depth": os.getenv("TAVILY_SEARCH_DEPTH","advanced"),
    }
    if days is not None:
        payload["days"] = int(days)
    r = _safe_post("https://api.tavily.com/search", headers={"Content-Type":"application/json"}, payload=payload, provider="tavily")
    items: List[Dict[str,Any]] = []
    if r and r.status_code == 200:
        try:
            data = r.json()
            for res in data.get("results", [])[:max_results]:
                url = res.get("url") or ""
                if not url or not _should_keep(url):
                    continue
                items.append({
                    "title": res.get("title") or url,
                    "url": url,
                    "domain": url.split("/")[2] if "://" in url else "",
                    "date": res.get("published_date") or "",
                    "score": res.get("score") or 0.0,
                })
        except Exception:
            return []
    return filter_and_rank(items)

def perplexity_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    """
    Uses Perplexity Search API; if unavailable, falls back to pplx chat/completions
    without passing a bogus 'model=auto'.
    """
    if not PPLX_KEY:
        return []
    headers = {
        "Authorization": f"Bearer {PPLX_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "KI-Ready-Search/1.0"
    }

    # 1) Try Search API (no explicit model)
    payload = {"query": query, "top_k": max(3, min(12, max_results)), "include_sources": True}
    if days:
        payload["time"] = f"{max(1,int(days))}d"
    r = _safe_post("https://api.perplexity.ai/search", headers=headers, payload=payload, provider="perplexity")
    items: List[Dict[str,Any]] = []
    if r and r.status_code == 200:
        try:
            data = r.json()
            for res in data.get("results", [])[:max_results]:
                srcs = res.get("source_links") or res.get("sources") or []
                # take first source as canonical
                canonical = None
                if srcs:
                    canonical = srcs[0]
                url = canonical or res.get("url") or ""
                if not url or not _should_keep(url):
                    continue
                items.append({
                    "title": res.get("title") or url,
                    "url": url,
                    "domain": url.split("/")[2] if "://" in url else "",
                    "date": res.get("published_at") or res.get("date") or "",
                    "score": res.get("score") or 0.0,
                })
            return filter_and_rank(items)
        except Exception:
            items = []  # fall through to chat fallback

    # 2) Fallback: chat/completions with a valid model (if env provides one)
    model_env = (os.getenv("PPLX_MODEL") or "").strip()
    model = model_env if model_env and model_env.lower() not in {"auto","best","default"} else "sonar-large"
    payload2 = {
        "model": model,
        "messages": [{"role":"user","content": f"Search the web and return {max_results} high-quality links (title, url, date) for: {query}"}],
        "max_tokens": 500,
    }
    r2 = _safe_post("https://api.perplexity.ai/chat/completions", headers=headers, payload=payload2, provider="perplexity")
    if r2 and r2.status_code == 200:
        try:
            data = r2.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            # try to parse loose JSON in the output; otherwise extract links heuristically
            # very defensive:
            import re, json as _json
            urls = re.findall(r"https?://[^\s)>\]]+", content)
            for u in urls[:max_results]:
                if not _should_keep(u):
                    continue
                items.append({"title": u, "url": u, "domain": u.split('/')[2] if '://' in u else "", "date": "", "score": 0.0})
            return filter_and_rank(items)
        except Exception:
            return []
    return []
