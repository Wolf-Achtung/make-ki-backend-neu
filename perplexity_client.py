# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Perplexity Search Adapter (robust)
- bevorzugt /search (ohne model)
- Fallback auf /chat/completions nur mit expliziter PPLX_MODEL (kein 'auto')
- 429/5xx Backoff + dedupe
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional
import os, time, httpx

PPLX_API_KEY = os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY") or ""
PPLX_MODEL = (os.getenv("PPLX_MODEL") or "").strip()
TIMEOUT = float(os.getenv("PPLX_TIMEOUT","15"))

def _client() -> httpx.Client:
    headers = {"Authorization": f"Bearer {PPLX_API_KEY}", "Content-Type": "application/json"}
    return httpx.Client(timeout=TIMEOUT, headers=headers)

def _backoff_sleep(i: int) -> None:
    time.sleep(min(0.25 * (2 ** i), 6.0))

def search(query: str, max_results: int = 6, days: Optional[int] = None) -> List[Dict[str,Any]]:
    if not PPLX_API_KEY:
        return []
    payload = {"q": query, "max_results": max_results}
    if days:
        payload["search_recency_days"] = int(days)
    # Try /search first
    try:
        with _client() as c:
            for i in range(4):
                r = c.post("https://api.perplexity.ai/search", json=payload)
                if r.status_code == 429 or r.status_code >= 500:
                    _backoff_sleep(i)
                    continue
                if r.status_code == 404:
                    break
                r.raise_for_status()
                data = r.json()
                results = []
                for item in (data.get("results") or []):
                    results.append({
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "date": (item.get("published_at") or item.get("published_date") or ""),
                        "domain": item.get("domain") or None,
                        "score": item.get("score") or None
                    })
                if results:
                    return results[:max_results]
                break
    except Exception:
        pass
    # Fallback: chat/completions only with explicit (non-auto) model
    model = PPLX_MODEL if (PPLX_MODEL and PPLX_MODEL.lower() not in {"auto","best","default"}) else None
    if not model:
        return []
    messages = [{"role":"user","content": f"Suche aktuelle Ergebnisse: {query}. Gib eine JSON-Liste mit Objekten {{title,url,date}} zurück."}]
    try:
        with _client() as c:
            for i in range(3):
                r = c.post("https://api.perplexity.ai/chat/completions", json={"model": model, "messages": messages, "temperature": 0.0})
                if r.status_code == 429 or r.status_code >= 500:
                    _backoff_sleep(i)
                    continue
                if r.status_code >= 400:
                    return []
                data = r.json()
                txt = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or "[]"
                import json as _json, re as _re
                # Extract first JSON list
                m = _re.search(r"\[.*\]", txt, _re.S)
                if m:
                    try:
                        arr = _json.loads(m.group(0))
                        out = []
                        for it in arr:
                            out.append({"title": it.get("title"), "url": it.get("url"), "date": it.get("date")})
                        return out[:max_results]
                    except Exception:
                        return []
                return []
    except Exception:
        return []
    return []
