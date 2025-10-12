
# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Perplexity adapter (tolerant)
- Tries Search API first (no explicit model).
- Falls back to chat/completions with a safe default model if model=auto/empty/invalid.
- Graceful 400-handling with automatic disable (returns [] and logs one-line hint).
Env:
  PERPLEXITY_API_KEY / PPLX_API_KEY
  PPLX_MODEL (optional; if "auto"/empty -> omit for Search API or use 'sonar-large-online' fallback)
"""
from __future__ import annotations

from typing import Dict, List, Optional
import os, time, json
import httpx
import logging

log = logging.getLogger("perplexity")

API_BASE = os.getenv("PPLX_BASE_URL", "https://api.perplexity.ai")
API_KEY  = os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY") or ""
RAW_MODEL = (os.getenv("PPLX_MODEL") or "").strip()

SAFE_FALLBACK_MODEL = os.getenv("PPLX_FALLBACK_MODEL", "sonar-large-online")

def _effective_model(name: str) -> Optional[str]:
    if not name:
        return None
    low = name.lower()
    if low in {"auto","default","best","online","sonar-online","sonar-medium-online","sonar-small-online"}:
        # treat as "let server choose" -> no model if using search API, else SAFE_FALLBACK_MODEL
        return SAFE_FALLBACK_MODEL
    return name

class PerplexityClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, timeout: float = 12.0):
        self.api_key = api_key or API_KEY
        self.model   = _effective_model(model or RAW_MODEL)
        self.timeout = timeout

    def _headers(self) -> Dict[str,str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "KI-Ready-Report/1.0"
        }

    def search(self, query: str, max_results: int = 6) -> List[Dict]:
        if not self.api_key:
            return []

        # 1) Try Search API (no explicit model)
        payload = {"query": query, "top_k": max_results, "include_images": False}
        try:
            with httpx.Client(timeout=self.timeout) as cli:
                r = cli.post(f"{API_BASE}/search", headers=self._headers(), json=payload)
                if r.status_code == 200 and "application/json" in (r.headers.get("content-type","")).lower():
                    data = r.json() or {}
                    out: List[Dict] = []
                    for it in data.get("results", []):
                        out.append({
                            "title": it.get("title") or it.get("url"),
                            "url": it.get("url"),
                            "content": it.get("snippet") or it.get("content"),
                            "date": it.get("published_at") or it.get("published_date") or it.get("date"),
                            "score": it.get("score", 0)
                        })
                    return out
                # Some tenants have /v1/search instead of /search
                if r.status_code in (404, 405):
                    r2 = cli.post(f"{API_BASE}/v1/search", headers=self._headers(), json=payload)
                    if r2.status_code == 200:
                        data = r2.json() or {}
                        out: List[Dict] = []
                        for it in data.get("results", []):
                            out.append({
                                "title": it.get("title") or it.get("url"),
                                "url": it.get("url"),
                                "content": it.get("snippet") or it.get("content"),
                                "date": it.get("published_at") or it.get("published_date") or it.get("date"),
                                "score": it.get("score", 0)
                            })
                        return out
        except Exception as exc:
            log.warning("Perplexity search endpoint failed: %s", exc)

        # 2) Fallback to chat/completions with a safe model + JSON-style instruction
        eff_model = self.model or SAFE_FALLBACK_MODEL
        payload_cc = {
            "model": eff_model,
            "messages": [
                {"role":"system","content":"Return strictly a JSON array of objects with fields: title, url, date (YYYY-MM-DD if present). No prose."},
                {"role":"user","content": f"List up to {max_results} relevant, recent sources for: {query}"}
            ],
            "max_tokens": 700,
            "temperature": 0.0
        }
        try:
            with httpx.Client(timeout=self.timeout) as cli:
                r = cli.post(f"{API_BASE}/chat/completions", headers=self._headers(), json=payload_cc)
                if r.status_code == 200:
                    data = r.json()
                    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "[]"
                    try:
                        arr = json.loads(content)
                    except Exception:
                        arr = []
                    out: List[Dict] = []
                    for it in (arr if isinstance(arr, list) else []):
                        url = it.get("url")
                        if not url:
                            continue
                        out.append({
                            "title": it.get("title") or url,
                            "url": url,
                            "date": it.get("date"),
                            "score": 0
                        })
                    return out
                elif r.status_code == 400:
                    log.warning("Perplexity 400 – model invalid? model=%s", eff_model)
                    return []
        except httpx.HTTPStatusError as exc:
            log.warning("Perplexity chat/completions HTTP error: %s", exc)
        except Exception as exc:
            log.warning("Perplexity chat/completions failed: %s", exc)

        return []
