# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Minimal Perplexity client with robust guards.

Default uses the Search API (no explicit model). If 'PPLX_MODEL' is provided
AND endpoint '/chat/completions' must be used, we fall back to 'sonar-pro' as
a safe default and never send the placeholder 'auto'.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import os, time, random
import httpx

try:
    from live_logger import log_event as _emit  # type: ignore
except Exception:  # pragma: no cover
    def _emit(provider: str, model: Optional[str], status: str, latency_ms: int, count: int = 0, **kw: Any) -> None:
        pass

API_BASE = os.getenv("PPLX_BASE_URL", "https://api.perplexity.ai")
API_KEY = os.getenv("PERPLEXITY_API_KEY", "").strip()
TIMEOUT = float(os.getenv("PPLX_TIMEOUT", "30"))
MODEL = os.getenv("PPLX_MODEL", "").strip()

def _effective_model() -> Optional[str]:
    m = (MODEL or "").strip().lower()
    if not m or m in {"auto", "default", "best", "best_mode"}:
        return None
    return MODEL

def search(query: str, top_k: int = 8, days: Optional[int] = None) -> List[Dict[str,Any]]:
    """Use Perplexity Search API (no explicit model required)."""
    if not API_KEY:
        return []
    t0 = time.time()
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload: Dict[str, Any] = {"q": query, "top_k": int(top_k)}
    if days:
        payload["time"] = f"{int(days)}d"  # relative window e.g. '30d'

    url = f"{API_BASE}/search"
    try:
        with httpx.Client(timeout=TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            if r.status_code == 404:
                # Some deployments require /v1/search
                url_v1 = f"{API_BASE}/v1/search"
                r = cli.post(url_v1, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            items = []
            for hit in (data.get("results") or []):
                items.append({
                    "title": hit.get("title") or hit.get("name") or hit.get("url"),
                    "url": hit.get("url"),
                    "domain": (hit.get("source") or ""),
                    "date": hit.get("published_at") or hit.get("date") or "",
                    "provider": "perplexity",
                })
            latency = int((time.time() - t0) * 1000)
            _emit("perplexity", None, "ok", latency, count=len(items))
            return items
    except httpx.HTTPStatusError as e:  # pragma: no cover
        latency = int((time.time() - t0) * 1000)
        _emit("perplexity", None, f"error:{e.__class__.__name__}", latency, count=0)
        return []
    except Exception as e:  # pragma: no cover
        latency = int((time.time() - t0) * 1000)
        _emit("perplexity", None, f"error:{e.__class__.__name__}", latency, count=0)
        return []

def chat_search(query: str, top_k: int = 8) -> List[Dict[str,Any]]:
    """Fallback to chat/completions with a supported model if Search API is unavailable.
       Returns a list of dicts with 'title','url','domain','date' when the model can tool-use or quote URLs.
    """
    if not API_KEY:
        return []
    model = _effective_model() or "sonar-pro"
    t0 = time.time()
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    url = f"{API_BASE}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return JSON with an array 'results' of {title,url,source,date}. Be concise."},
            {"role": "user", "content": f"Find {top_k} trustworthy sources for: {query}. Return only JSON."},
        ],
        "max_tokens": 500,
        "temperature": 0.0
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}"
            # naive JSON extraction
            import json as _json
            content = content.strip().strip("`").strip()
            if content.startswith("{") and content.endswith("}"):
                obj = _json.loads(content)
                arr = obj.get("results") or []
            else:
                arr = []
            items = []
            for hit in arr:
                items.append({
                    "title": hit.get("title") or hit.get("url"),
                    "url": hit.get("url"),
                    "domain": (hit.get("source") or ""),
                    "date": hit.get("date") or "",
                    "provider": "perplexity",
                })
            latency = int((time.time() - t0) * 1000)
            _emit("perplexity", model, "ok_fallback_chat", latency, count=len(items))
            return items
    except Exception:
        latency = int((time.time() - t0) * 1000)
        _emit("perplexity", model, "error_fallback_chat", latency, count=0)
        return []
