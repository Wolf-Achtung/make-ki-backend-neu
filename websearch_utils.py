# websearch_utils.py — Hybrid live search (Perplexity + Tavily) with 429 backoff
from __future__ import annotations
from typing import List, Dict, Any, Optional
import os, time, random
import httpx

try:
    from live_logger import log_event as _emit  # optional structured logs
except Exception:
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        pass

from utils_sources import filter_and_rank

# ---------------- backoff helpers ----------------
def _sleep(attempt: int, base: float = 0.5) -> None:
    import math, random
    t = base * (2 ** attempt) + random.random() * 0.2
    time.sleep(min(8.0, t))

def _now_ms() -> int:
    return int(time.time() * 1000)

# ---------------- Tavily ----------------
def tavily_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    include = [d.strip() for d in os.getenv("SEARCH_INCLUDE_DOMAINS","" ).split(",") if d.strip()]
    exclude = [d.strip() for d in os.getenv("SEARCH_EXCLUDE_DOMAINS","" ).split(",") if d.strip()]
    payload: Dict[str,Any] = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "search_depth": os.getenv("SEARCH_DEPTH","advanced"),
    }
    if include:
        payload["include_domains"] = include
    if exclude:
        payload["exclude_domains"] = exclude
    if days:
        payload["days"] = int(days)

    started = _now_ms()
    for attempt in range(0, 3):
        try:
            with httpx.Client(timeout=float(os.getenv("TAVILY_TIMEOUT","14"))) as c:
                r = c.post("https://api.tavily.com/search", json=payload)
                if r.status_code == 200:
                    js = r.json()
                    out = [{
                        "title": it.get("title") or it.get("url"),
                        "url": it.get("url"),
                        "domain": (it.get("url") or "").split('/')[2] if '://' in (it.get("url") or '') else "",
                        "date": (it.get("published_date") or it.get("date") or "")[:10],
                        "snippet": it.get("content") or "",
                        "score": it.get("score") or 0.0,
                    } for it in js.get("results", [])[:max_results]]
                    _emit("tavily", None, "ok", _now_ms()-started, len(out))
                    return filter_and_rank(out)
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    if ra:
                        try: time.sleep(float(ra))
                        except Exception: _sleep(attempt)
                    else:
                        _sleep(attempt)
                    continue
                if r.status_code >= 400 and r.status_code < 500:
                    _emit("tavily", None, f"{r.status_code}_bad_request_retry_minimal", _now_ms()-started, 0)
                    # Retry once minimal; then stop
                    if attempt == 0:
                        payload_min = {"api_key": key, "query": query, "max_results": max_results, "include_answer": False}
                        try:
                            r2 = httpx.post("https://api.tavily.com/search", json=payload_min, timeout=10.0)
                            if r2.status_code == 200:
                                js = r2.json()
                                out = [{
                                    "title": it.get("title") or it.get("url"),
                                    "url": it.get("url"),
                                    "domain": (it.get("url") or "").split('/')[2] if '://' in (it.get("url") or '') else "",
                                    "date": (it.get("published_date") or it.get("date") or "")[:10],
                                    "snippet": it.get("content") or "",
                                    "score": it.get("score") or 0.0,
                                } for it in js.get("results", [])[:max_results]]
                                _emit("tavily", None, "ok", _now_ms()-started, len(out))
                                return filter_and_rank(out)
                        except Exception:
                            pass
                    break
                if r.status_code >= 500:
                    _sleep(attempt); continue
        except Exception:
            _sleep(attempt)
    _emit("tavily", None, "error", _now_ms()-started, 0)
    return []

# ---------------- Perplexity ----------------
def perplexity_search(query: str, max_results: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    from perplexity_client import PerplexityClient
    include = [d.strip() for d in os.getenv("SEARCH_INCLUDE_DOMAINS","" ).split(",") if d.strip()]
    exclude = [d.strip() for d in os.getenv("SEARCH_EXCLUDE_DOMAINS","" ).split(",") if d.strip()]
    started = _now_ms()
    try:
        cli = PerplexityClient()
        res = cli.search(query, max_results=max_results, include_domains=include, exclude_domains=exclude, days=days)
        _emit("perplexity", os.getenv("PPLX_MODEL","auto") or "auto", "ok" if res else "empty", _now_ms()-started, len(res))
        return filter_and_rank(res)
    except Exception as exc:
        _emit("perplexity", os.getenv("PPLX_MODEL","auto") or "auto", f"error:{type(exc).__name__}", _now_ms()-started, 0)
        return []