# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid live search (Tavily + Perplexity) with multi-query support, model guards,
JSON-schema fallback removal on 400, and robust exponential backoff.

Implements key practices from Perplexity docs:
- Write specific queries & break into sub-queries ("multi-query")
- Limit result counts; cache repeated queries (optional via env)
- Exponential backoff for 429/5xx; controlled retries for 400s
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple
import os, time, json, httpx, hashlib

# Structured logging
try:
    from live_logger import log_event as _emit  # type: ignore
except Exception:
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        payload = {"evt":"live_search","provider":provider,"model":model,"status":status,"latency_ms":int(latency_ms),"count":int(count)}
        payload.update({k:v for k,v in (kw or {}).items() if v is not None})
        print(json.dumps(payload, ensure_ascii=False))

# Source ranking
try:
    from utils_sources import filter_and_rank
except Exception:
    def filter_and_rank(items: Iterable[Dict[str, Any]], **kw) -> List[Dict[str, Any]]:
        return list(items)

TAVILY_URL = "https://api.tavily.com/search"
PPLX_URL = "https://api.perplexity.ai/chat/completions"

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS","30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS","60"))
TAVILY_MAX = int(os.getenv("TAVILY_MAX","12"))
PPLX_TIMEOUT = float(os.getenv("PPLX_TIMEOUT", "30"))
CACHE_TTL = int(os.getenv("LIVE_CACHE_TTL","120"))  # seconds

_cache: Dict[str, Tuple[float, Any]] = {}

def _cache_get(key: str):
    ts_val = _cache.get(key)
    if not ts_val: return None
    ts, val = ts_val
    if time.time() - ts < CACHE_TTL:
        return val
    _cache.pop(key, None)
    return None

def _cache_set(key: str, val: Any):
    if CACHE_TTL > 0:
        _cache[key] = (time.time(), val)

def _mk_key(*parts: str) -> str:
    import hashlib
    return hashlib.sha1(("|".join(parts)).encode("utf-8")).hexdigest()

def _pplx_model_effective() -> Optional[str]:
    name = (os.getenv("PPLX_MODEL") or "").strip()
    if not name: return None
    low = name.lower()
    if low in {"auto","best","default","none"} or "online" in low:
        return None
    return name

def _http_post_with_backoff(url: str, headers: Dict[str,str], payload: Dict[str,Any], timeout: float,
                            provider: str, model: Optional[str] = None, attempts: int = 4):
    delays = [0.0, 0.6, 1.2, 2.4][:attempts]
    start = time.monotonic()
    with httpx.Client(timeout=timeout) as client:
        for i, d in enumerate(delays, start=1):
            if d: time.sleep(d)
            try:
                resp = client.post(url, headers=headers, json=payload)
                # Rate-limit friendly backoff
                if resp.status_code in (408,429,502,503) and i < len(delays):
                    _emit(provider, model, f"backoff_{resp.status_code}", int((time.monotonic()-start)*1000), 0)
                    continue
                return resp, start
            except Exception as exc:
                _emit(provider, model, f"error:{type(exc).__name__}", int((time.monotonic()-start)*1000), 0)
                # retry next delay
    raise RuntimeError("backoff_fail")

def tavily_search(query: str, *, max_results: int = TAVILY_MAX, days: int = SEARCH_DAYS_NEWS) -> List[Dict[str,Any]]:
    if not (os.getenv("TAVILY_API_KEY") or "").strip():
        return []
    headers = {"Authorization": f"Bearer {os.getenv('TAVILY_API_KEY')}", "Content-Type": "application/json"}
    full = {"query": query, "search_depth": "advanced", "max_results": max_results, "include_answer": False, "time_range": f"{days}d"}
    t0 = time.monotonic()
    items: List[Dict[str,Any]] = []
    try:
        resp, start = _http_post_with_backoff(TAVILY_URL, headers, full, 30.0, "tavily")
        if resp.status_code == 400:
            _emit("tavily", None, "400_bad_request_retry_minimal", int((time.monotonic()-start)*1000), 0)
            resp, start = _http_post_with_backoff(TAVILY_URL, headers, {"query": query}, 30.0, "tavily")
        resp.raise_for_status()
        data = resp.json() or {}
        for r in (data.get("results") or [])[:max_results]:
            url = r.get("url"); dom = (url or "").split("/")[2] if "://" in (url or "") else ""
            items.append({"title": r.get("title") or url, "url": url, "domain": dom, "date": (r.get("published_date") or "")[:10], "provider": "tavily"})
        status = "ok"
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        _emit("tavily", None, status, int((time.monotonic()-t0)*1000), len(items))
    return items

def _pplx_call(query: str, *, model: Optional[str]):
    key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or ""
    if not key: return []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"title":{"type":"string"},"url":{"type":"string"},"date":{"type":"string"}},
                    "required": ["title","url"],
                    "additionalProperties": True,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    body = {
        "messages": [
            {"role":"system","content":"Return ONLY compact JSON matching the schema."},
            {"role":"user","content": f"Find recent sources (title,url,date) for: {query}"},
        ],
        "temperature": 0.1,
        "max_tokens": 900,
        "response_format": {"type":"json_schema","json_schema":{"schema": schema}},
    }
    if model: body["model"] = model
    resp, start = _http_post_with_backoff(PPLX_URL, headers, body, PPLX_TIMEOUT, "perplexity", model or "auto")
    if resp.status_code == 400 and "invalid_model" in (resp.text or "").lower():
        body.pop("model", None)
        _emit("perplexity", model or "auto", "400_invalid_model_retry_auto", int((time.monotonic()-start)*1000), 0)
        resp, start = _http_post_with_backoff(PPLX_URL, headers, body, PPLX_TIMEOUT, "perplexity", "auto")
    if resp.status_code == 400:
        # remove response_format and retry
        body.pop("response_format", None)
        body["messages"] = [
            {"role":"system","content":"You are precise. Output a single JSON object: {\"items\":[{\"title\":\"...\",\"url\":\"...\",\"date\":\"YYYY-MM-DD\"}]} Only JSON."},
            {"role":"user","content": query},
        ]
        _emit("perplexity", model or "auto", "400_retry_no_schema", int((time.monotonic()-start)*1000), 0)
        resp, start = _http_post_with_backoff(PPLX_URL, headers, body, PPLX_TIMEOUT, "perplexity", "auto")
    resp.raise_for_status()
    data = resp.json() or {}
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
    import json as _json
    obj = _json.loads(content) if isinstance(content, str) else content
    out = []
    for r in (obj.get("items") or [])[:12]:
        url = r.get("url"); dom = (url or "").split("/")[2] if "://" in (url or "") else ""
        out.append({"title": r.get("title") or url, "url": url, "domain": dom, "date": (r.get("date") or "")[:10], "provider": "perplexity"})
    return out

def perplexity_search_multi(topic: str, *, sub_queries: Optional[List[str]] = None, max_results: int = 12) -> List[Dict[str,Any]]:
    """
    Multi-query strategy inspired by Perplexity docs:
      - break topic into 2-3 focused sub-queries
      - merge + rank results
    """
    model = _pplx_model_effective()
    if sub_queries is None:
        sub_queries = [topic, f"{topic} Deutschland 2025", f"{topic} KMU praktische Tools"]
    items: List[Dict[str,Any]] = []
    for q in sub_queries:
        key = _mk_key("pplx", q, model or "auto")
        cached = _cache_get(key)
        if cached is not None:
            items.extend(cached)
            continue
        try:
            res = _pplx_call(q, model=model)
        except Exception as e:
            _emit("perplexity", model or "auto", f"error:{type(e).__name__}", 0, 0)
            res = []
        _cache_set(key, res)
        items.extend(res)
        # Friendly pacing between sub-queries
        time.sleep(0.25)
    # dedupe & rank via utils_sources
    return filter_and_rank(items)

def hybrid_live_search(topic: str, *, max_results: int = 12, days_news: int = SEARCH_DAYS_NEWS, days_tools: int = SEARCH_DAYS_TOOLS) -> Dict[str,Any]:
    tav = tavily_search(topic, max_results=max_results, days=days_news)
    ppl = perplexity_search_multi(topic, max_results=max_results)
    items = filter_and_rank(tav + ppl)
    return {"items": items[:max_results], "raw": {"tavily": tav, "perplexity": ppl}, "counts": {"total": len(items)}}
# end of file
