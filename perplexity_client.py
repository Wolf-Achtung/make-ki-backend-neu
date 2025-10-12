
# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Minimal Perplexity client (Gold-Standard+)
- avoids invalid 'model=auto' on chat/completions
- provides search() helper
"""

from __future__ import annotations
import os, httpx
from typing import Any, Dict, Optional

PPLX_KEY = (os.getenv("PERPLEXITY_API_KEY") or os.getenv("PPLX_API_KEY") or "").strip()

class PerplexityClient:
    def __init__(self, api_key: Optional[str] = None, timeout: float = 15.0):
        self.api_key = api_key or PPLX_KEY
        self.timeout = timeout
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "KI-Ready-Client/1.0"
        }

    def search(self, query: str, top_k: int = 8, time_window: Optional[str] = None) -> Dict[str,Any]:
        if not self.api_key:
            return {"results": []}
        payload: Dict[str, Any] = {"query": query, "top_k": max(1, min(12, int(top_k))), "include_sources": True}
        if time_window:
            payload["time"] = time_window
        with httpx.Client(timeout=self.timeout) as cli:
            r = cli.post("https://api.perplexity.ai/search", headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()

    def chat(self, prompt: str, model: Optional[str] = None, max_tokens: int = 800) -> Dict[str,Any]:
        if not self.api_key:
            return {"choices": []}
        model = (model or os.getenv("PPLX_MODEL") or "").strip()
        # explicit guard: never pass bogus placeholders
        if not model or model.lower() in {"auto", "best", "default"}:
            model = "sonar-large"
        payload = {"model": model, "messages": [{"role":"user","content": prompt}], "max_tokens": int(max_tokens)}
        with httpx.Client(timeout=self.timeout) as cli:
            r = cli.post("https://api.perplexity.ai/chat/completions", headers=self.headers, json=payload)
            r.raise_for_status()
            return r.json()
