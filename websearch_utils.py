# filename: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid-Live-Suche (Gold-Standard+)

- Tavily (Bearer) mit Minimal-Payload-Retry bei 400
- Perplexity ChatCompletions mit JSON-Schema; **kein** model-Feld im Auto-Mode
  * ENV `PPLX_MODEL` wird über Guards interpretiert (''/auto/best/default/none -> Auto)
  * 400/invalid_model -> ein Retry ohne Modell
- Deduplication & einfaches Ranking
- Optionaler File-Cache für 30 min (`live_cache.py`)

ENV (relevant):
  TAVILY_API_KEY, PPLX_API_KEY|PERPLEXITY_API_KEY
  PPLX_MODEL (optional), PPLX_TIMEOUT
  LIVE_CACHE_ENABLED, LIVE_CACHE_TTL_SECONDS
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os, time, json, httpx, hashlib

try:
    from live_logger import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, extra: Optional[Dict[str, Any]] = None) -> None:  # type: ignore
        pass

try:
    from live_cache import cache_get, cache_set  # type: ignore
except Exception:  # pragma: no cover
    def cache_get(key: str):  # type: ignore
        return None
    def cache_set(key: str, value: Any) -> None:  # type: ignore
        return None

TAVILY_URL = "https://api.tavily.com/search"
PPLX_URL = "https://api.perplexity.ai/chat/completions"

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
TAVILY_MAX = int(os.getenv("TAVILY_MAX", "12"))

PPLX_TIMEOUT = float(os.getenv("PPLX_TIMEOUT", os.getenv("PPLX_TIMEOUT_SEC", "30.0")))

def _pplx_model_effective(raw: Optional[str]) -> Optional[str]:
    name = (raw or "").strip()
    if not name:
        return None
    low = name.lower()
    if low in {"auto", "best", "default", "none"}:
        return None
    if "online" in low:
        log_event("perplexity", name, "deprecated_model_ignored", 0, 0)
        return None
    return name

def _dedupe_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set(); out: List[Dict[str, Any]] = []
    for it in items:
        url = (it.get("url") or "").split("?")[0].lower()
        title = (it.get("title") or "").strip().lower()
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def _rank_by_date(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from datetime import datetime
    def parse_dt(s: str):
        try:
            return datetime.fromisoformat((s or "").replace("Z", "")[:19])
        except Exception:
            return datetime.min
    return sorted(items, key=lambda x: parse_dt(str(x.get("date") or "")), reverse=True)

def _cache_key(prefix: str, **kw: Any) -> str:
    h = hashlib.sha256(json.dumps(kw, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{h}"

def tavily_search(query: str, max_results: int = TAVILY_MAX, days: int = SEARCH_DAYS_NEWS) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY") or ""
    if not key or not query.strip():
        return []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    payload = {"query": query, "search_depth": "advanced", "max_results": max_results, "include_answer": False, "time_range": f"{days}d"}
    ts = time.time(); items: List[Dict[str, Any]] = []; status = "ok"
    # Cache
    k = _cache_key("tav", q=query, max=max_results, d=days)
    cached = cache_get(k)
    if cached:
        log_event("tavily", None, "cache_hit", 0, len(cached))
        return cached
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(TAVILY_URL, headers=headers, json=payload)
        if resp.status_code == 400:
            # minimal retry
            log_event("tavily", None, "400_bad_request_retry_minimal", int((time.time()-ts)*1000), 0)
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(TAVILY_URL, headers=headers, json={"query": query})
        if resp.status_code == 401:
            status = "unauthorized"
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
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
        items = _rank_by_date(_dedupe_items(items))[:max_results]
        log_event("tavily", None, status, int((time.time()-ts)*1000), count=len(items))
        if items:
            cache_set(k, items)
    return items

def perplexity_search(query: str, max_results: int = 10, category_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or ""
    if not key or not query.strip():
        return []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    system = "Be precise and return ONLY valid JSON matching the provided schema."
    user = f"Find recent, reliable sources (title, url, date) for: {query}. Category: {category_hint or 'mixed'}"
    schema = {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}, "date": {"type": "string"}}, "required": ["title", "url"], "additionalProperties": True}}},
        "required": ["items"],
        "additionalProperties": False,
    }
    base_body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.1, "max_tokens": 900, "response_format": {"type": "json_schema", "json_schema": {"schema": schema}}}
    eff_model = _pplx_model_effective(os.getenv("PPLX_MODEL", ""))
    body = {**base_body, **({"model": eff_model} if eff_model else {})}
    ts = time.time(); items: List[Dict[str, Any]] = []; status = "ok"
    # Cache
    k = _cache_key("pplx", q=query, max=max_results, cat=category_hint, m=eff_model or "auto")
    cached = cache_get(k)
    if cached:
        log_event("perplexity", eff_model or "auto", "cache_hit", 0, len(cached))
        return cached
    try:
        with httpx.Client(timeout=PPLX_TIMEOUT) as client:
            resp = client.post(PPLX_URL, headers=headers, json=body)
        body_txt = resp.text or ""
        if resp.status_code == 400 and "invalid_model" in body_txt.lower() and "model" in body:
            log_event("perplexity", eff_model or "auto", "400_invalid_model_retry_auto", int((time.time()-ts)*1000), 0)
            body.pop("model", None)
            with httpx.Client(timeout=PPLX_TIMEOUT) as client:
                resp = client.post(PPLX_URL, headers=headers, json=body)
        if resp.status_code == 401:
            status = "unauthorized"
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
        parsed = json.loads(content) if isinstance(content, str) else content
        for r in parsed.get("items", []):
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
        items = _rank_by_date(_dedupe_items(items))[:max_results]
        log_event("perplexity", eff_model or "auto", status, int((time.time()-ts)*1000), count=len(items))
        if items:
            cache_set(k, items)
    return items

def hybrid_live_search(query: str, briefing: Optional[Dict[str, Any]] = None, short_days: int = SEARCH_DAYS_NEWS, long_days: int = SEARCH_DAYS_TOOLS, max_results: int = 12) -> Dict[str, Any]:
    tav = tavily_search(query, max_results=max_results, days=short_days)
    ppl = perplexity_search(query, max_results=max_results, category_hint="mixed")
    deduped = _dedupe_items(tav + ppl)
    # einfache Zählwerte – in diesem Modul nicht branchen-/themenspezifisch
    counts = {"news": 0, "tools": 0, "funding": 0, "other": len(deduped)}
    return {"items": _rank_by_date(deduped)[:max_results], "counts": counts, "raw": {"tavily": tav, "perplexity": ppl}}
