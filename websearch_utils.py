# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid live search (Tavily + Perplexity) with model-guards, 400-minimal fallback,
and robust 429/5xx exponential backoff. Import-safe and production-hardened.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
import time
import json
import httpx

try:
    from .utils_sources import filter_and_rank  # type: ignore
except Exception:  # pragma: no cover
    from utils_sources import filter_and_rank  # type: ignore

# ---------------- Structured logging ----------------

def _log_event(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
    payload = {
        "evt": "live_search",
        "provider": provider,
        "model": model,
        "status": status,
        "latency_ms": int(latency_ms),
        "count": int(count),
    }
    payload.update({k: v for k, v in (kw or {}).items() if v is not None})
    try:
        print(json.dumps(payload, ensure_ascii=False))
    except Exception:
        print(f"[live_search] {provider} {status} {latency_ms}ms c={count}")

# ---------------- Config ----------------

TAVILY_URL = "https://api.tavily.com/search"
PPLX_URL = "https://api.perplexity.ai/chat/completions"

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
TAVILY_MAX = int(os.getenv("TAVILY_MAX", "12"))

PPLX_TIMEOUT = float(os.getenv("PPLX_TIMEOUT", os.getenv("PPLX_TIMEOUT_SEC", "30.0")))

# ---------------- Helpers ----------------

def _pplx_model_effective() -> Optional[str]:
    name = (os.getenv("PPLX_MODEL") or "").strip()
    if not name:
        return None
    low = name.lower()
    if low in {"auto", "best", "default", "none"} or "online" in low:
        return None
    return name

def _http_post_with_backoff(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: float,
    provider: str,
    model: Optional[str] = None,
    backoff_codes: Tuple[int, ...] = (429, 502, 503),
    attempts: int = 4,
) -> Tuple[httpx.Response, float]:
    """POST with exponential backoff for transient HTTP error codes."""
    delays = [0.0, 0.6, 1.2, 2.4][:attempts]
    start = time.monotonic()
    last_err: Optional[str] = None
    with httpx.Client(timeout=timeout) as client:
        for i, d in enumerate(delays, start=1):
            if d:
                time.sleep(d)
            try:
                resp = client.post(url, headers=headers, json=payload)
                if resp.status_code in backoff_codes and i < attempts:
                    _log_event(provider, model, f"backoff_{resp.status_code}", int((time.monotonic() - start) * 1000), 0)
                    last_err = f"http_{resp.status_code}"
                    continue
                return resp, start
            except Exception as exc:  # pragma: no cover
                last_err = f"error:{type(exc).__name__}"
                _log_event(provider, model, last_err, int((time.monotonic() - start) * 1000), 0)
                continue
    raise RuntimeError(last_err or "backoff_failed")

# ---------------- Tavily ----------------

def tavily_search(query: str, *, max_results: int = TAVILY_MAX, days: int = SEARCH_DAYS_NEWS) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY") or ""
    if not key or not (query or "").strip():
        return []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    payload_full = {"query": query, "search_depth": "advanced", "max_results": max_results, "include_answer": False, "time_range": f"{days}d"}
    t0 = time.monotonic()
    items: List[Dict[str, Any]] = []
    status = "ok"
    try:
        resp, start = _http_post_with_backoff(TAVILY_URL, headers, payload_full, 30.0, "tavily")
        if resp.status_code == 400:
            _log_event("tavily", None, "400_bad_request_retry_minimal", int((time.monotonic() - start) * 1000), 0)
            resp, start = _http_post_with_backoff(TAVILY_URL, headers, {"query": query}, 30.0, "tavily")
        if resp.status_code == 401:
            status = "unauthorized"
        resp.raise_for_status()
        data = resp.json() or {}
        for r in (data.get("results") or [])[:max_results]:
            url = r.get("url")
            items.append({
                "title": r.get("title") or url,
                "url": url,
                "domain": (url or "").split("/")[2] if "://" in (url or "") else "",
                "date": (r.get("published_date") or "")[:10],
                "provider": "tavily",
            })
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        _log_event("tavily", None, status, int((time.monotonic() - t0) * 1000), len(items))
    return items

# ---------------- Perplexity ----------------

def perplexity_search(query: str, *, max_results: int = 10, category_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or ""
    if not key or not (query or "").strip():
        return []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    system = "Be precise. Return only JSON matching the schema."
    user = f"Find recent sources (title,url,date) for: {query}. Category: {category_hint or 'mixed'}"
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "url": {"type": "string"}, "date": {"type": "string"}},
                    "required": ["title", "url"],
                    "additionalProperties": True,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    model = _pplx_model_effective()
    base_body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.1, "max_tokens": 900, "response_format": {"type": "json_schema", "json_schema": {"schema": schema}}}
    body = dict(base_body, **({"model": model} if model else {}))

    t0 = time.monotonic()
    items: List[Dict[str, Any]] = []
    status = "ok"
    model_used = model or "auto"
    try:
        resp, start = _http_post_with_backoff(PPLX_URL, headers, body, PPLX_TIMEOUT, "perplexity", model_used)
        if resp.status_code == 400 and "invalid_model" in (resp.text or "").lower():
            body.pop("model", None)
            model_used = "auto"
            resp, start = _http_post_with_backoff(PPLX_URL, headers, body, PPLX_TIMEOUT, "perplexity", model_used)
        if resp.status_code == 401:
            status = "unauthorized"
        resp.raise_for_status()
        data = resp.json() or {}
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
        parsed = json.loads(content) if isinstance(content, str) else content
        for r in (parsed.get("items") or [])[:max_results]:
            url = r.get("url")
            items.append({
                "title": r.get("title") or url,
                "url": url,
                "domain": (url or "").split("/")[2] if "://" in (url or "") else "",
                "date": (r.get("date") or "")[:10],
                "provider": "perplexity",
            })
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        _log_event("perplexity", model_used, status, int((time.monotonic() - t0) * 1000), len(items))
    return items

# ---------------- Hybrid ----------------

def hybrid_live_search(query: str, *, short_days: int = SEARCH_DAYS_NEWS, long_days: int = SEARCH_DAYS_TOOLS, max_results: int = 12) -> Dict[str, Any]:
    tav = tavily_search(query, max_results=max_results, days=short_days)
    ppl = perplexity_search(query, max_results=max_results, category_hint="mixed")
    items = filter_and_rank(tav + ppl)
    return {"items": items[:max_results], "counts": {"total": len(items)}, "raw": {"tavily": tav, "perplexity": ppl}}
