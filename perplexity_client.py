# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Minimaler Perplexity‑Client mit Search‑First Ansatz.
- Verwendet /v1/search (keine Modellangabe nötig)
- Fallback: /chat/completions mit explizitem Modell (ENV PPLX_FALLBACK_MODEL)
- 429‑Backoff mit Jitter
"""
from __future__ import annotations

import os, time, random
from typing import Any, Dict, List, Optional

import httpx

PPLX_KEY = os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY") or ""
BASE = os.getenv("PPLX_BASE_URL", "https://api.perplexity.ai")
FALLBACK_MODEL = os.getenv("PPLX_FALLBACK_MODEL", "sonar-large")  # nur für /chat/completions

DEFAULT_TIMEOUT = float(os.getenv("PPLX_TIMEOUT", "18.0"))
MAX_RETRIES = int(os.getenv("PPLX_MAX_RETRIES", "3"))

class PerplexityClient:
    def __init__(self, api_key: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT):
        self.key = api_key or PPLX_KEY
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {self.key}", "Accept": "application/json", "Content-Type": "application/json"}

    def _backoff(self, attempt: int) -> None:
        base = 0.75 * (2 ** attempt)
        time.sleep(base + random.random() * 0.4)

    def _site_clause(self, include_domains: Optional[List[str]]) -> str:
        if not include_domains:
            return ""
        parts = [f"(site:{d.strip()})" for d in include_domains if d.strip()]
        return " OR ".join(parts)

    def search(self, query: str, top_k: int = 8, include_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if not self.key:
            return []
        site = self._site_clause(include_domains)
        q = f"({query}) {'(' + site + ')' if site else ''}".strip()
        payload = {"query": q, "top_k": max(1, min(10, int(top_k))), "include_sources": True}
        endpoints = ["/v1/search", "/search"]
        last_err: Optional[Exception] = None
        for ep in endpoints:
            for attempt in range(MAX_RETRIES):
                try:
                    with httpx.Client(timeout=self.timeout) as cli:
                        r = cli.post(f"{BASE}{ep}", headers=self.headers, json=payload)
                        if r.status_code == 429:
                            self._backoff(attempt)
                            continue
                        r.raise_for_status()
                        data = r.json() or {}
                        results = data.get("results") or data.get("data") or []
                        out: List[Dict[str, Any]] = []
                        for it in results:
                            # unified mapping
                            url = it.get("url") or (it.get("source") or {}).get("url")
                            out.append({
                                "title": it.get("title") or (it.get("source") or {}).get("title") or url,
                                "url": url,
                                "content": it.get("snippet") or it.get("content") or "",
                                "date": it.get("published_date") or it.get("date") or "",
                                "score": it.get("score") or 0.0,
                                "domain": (url or "").split("/")[2] if url and "://" in url else ""
                            })
                        return out
                except httpx.HTTPStatusError as e:
                    last_err = e
                    break  # Wechsel auf nächsten Endpoint
                except Exception as e:
                    last_err = e
                    self._backoff(attempt)
                    continue
        # Fallback: chat/completions mit Modell (nur rudimentär für Kompatibilität)
        try:
            with httpx.Client(timeout=self.timeout) as cli:
                payload = {"model": FALLBACK_MODEL, "messages": [{"role":"user","content": f"Search the web and return 8 reputable sources for: {q}"}]}
                r = cli.post(f"{BASE}/chat/completions", headers=self.headers, json=payload)
                if r.status_code == 429:
                    return []
                r.raise_for_status()
        except Exception:
            pass
        return []
