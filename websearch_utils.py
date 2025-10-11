# filename: websearch_utils.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Any, Dict, List, Optional
import os, time, json, httpx
from datetime import datetime

# optional local helpers
try:
    from .utils_sources import dedupe_items  # type: ignore
except Exception:
    def dedupe_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen, out = set(), []
        for it in items:
            key = (it.get("url") or "").split("?")[0].strip().lower() or (it.get("title") or "").strip().lower()
            if key and key not in seen:
                seen.add(key); out.append(it)
        return out

from .live_logger import log_event  # type: ignore

TAVILY_URL = "https://api.tavily.com/search"
PPLX_URL = "https://api.perplexity.ai/chat/completions"

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
TAVILY_MAX = int(os.getenv("TAVILY_MAX", "12"))
PPLX_TIMEOUT = float(os.getenv("PPLX_TIMEOUT", "30.0"))

def _pplx_model_effective() -> Optional[str]:
    name = (os.getenv("PPLX_MODEL") or "").strip()
    if not name or name.lower() in {"auto", "best", "default", "none"}:
        return None
    if "online" in name.lower():
        return None
    return name

def tavily_search(query: str, max_results: int = TAVILY_MAX, days: int = SEARCH_DAYS_NEWS) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY") or ""
    headers = {"Authorization": f"Bearer {key}", "Content-Type":"application/json","Accept":"application/json"}
    payload = {"query": query, "search_depth":"advanced","max_results":max_results,"include_answer":False,"time_range":f"{days}d"}
    ts = time.time(); items: List[Dict[str, Any]] = []; status="ok"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(TAVILY_URL, headers=headers, json=payload)
        if resp.status_code == 400:
            log_event("tavily", None, "400_bad_request_retry_minimal", int((time.time()-ts)*1000), 0)
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(TAVILY_URL, headers=headers, json={"query": query})
        if resp.status_code == 401: status = "unauthorized"
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            url = r.get("url")
            items.append({"title": r.get("title") or url, "url": url, "domain": (url or "").split('/')[2] if '://' in (url or "") else "", "date": (r.get("published_date") or "")[:10], "provider": "tavily"})
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        log_event("tavily", None, status, int((time.time()-ts)*1000), count=len(items))
    return items

def perplexity_search(query: str, max_results: int = 10, category_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or ""
    headers = {"Authorization": f"Bearer {key}", "Content-Type":"application/json","Accept":"application/json"}
    system = "Be precise. Return only JSON matching the schema."
    user = f"Find recent sources (title,url,date) for: {query}. Category: {category_hint or 'mixed'}"
    schema = {"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"title":{"type":"string"},"url":{"type":"string"},"date":{"type":"string"}},"required":["title","url"],"additionalProperties":True}}},"required":["items"],"additionalProperties":False}
    base = {"messages":[{"role":"system","content":system},{"role":"user","content":user}], "temperature":0.1, "max_tokens":900, "response_format":{"type":"json_schema","json_schema":{"schema":schema}}}
    model = _pplx_model_effective()
    body = dict(base, **({"model": model} if model else {}))
    ts = time.time(); items: List[Dict[str, Any]] = []; status="ok"; model_used = model or "auto"
    try:
        with httpx.Client(timeout=PPLX_TIMEOUT) as client:
            resp = client.post(PPLX_URL, headers=headers, json=body)
        if resp.status_code == 400 and "invalid_model" in (resp.text or "").lower():
            # retry once without model
            body.pop("model", None); model_used = "auto"
            with httpx.Client(timeout=PPLX_TIMEOUT) as client:
                resp = client.post(PPLX_URL, headers=headers, json=body)
        if resp.status_code == 401: status = "unauthorized"
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
        parsed = json.loads(content) if isinstance(content, str) else content
        for r in parsed.get("items", []):
            url = r.get("url")
            items.append({"title": r.get("title") or url, "url": url, "domain": (url or "").split('/')[2] if '://' in (url or "") else "", "date": (r.get("date") or "")[:10], "provider": "perplexity"})
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        log_event("perplexity", model_used, status, int((time.time()-ts)*1000), count=len(items))
    return items

def hybrid_live_search(query: str, briefing: Optional[Dict[str, Any]] = None, short_days: int = SEARCH_DAYS_NEWS, long_days: int = SEARCH_DAYS_TOOLS, max_results: int = 12) -> Dict[str, Any]:
    tav = tavily_search(query, max_results=max_results, days=short_days)
    ppl = perplexity_search(query, max_results=max_results, category_hint="mixed")
    deduped = dedupe_items(tav + ppl)
    counts = {"news": 0, "tools": 0, "funding": 0, "other": len(deduped)}
    return {"items": deduped, "counts": counts, "raw": {"tavily": tav, "perplexity": ppl}}
