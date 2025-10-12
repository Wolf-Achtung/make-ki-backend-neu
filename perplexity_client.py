# perplexity_client.py
# -*- coding: utf-8 -*-
"""
Minimal Perplexity Chat Completions client (optional).
Use Cases: if you need reasoning/grounded chat, pick a Sonar model.
For pure link discovery, use websearch_utils.perplexity_search instead.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import os
import httpx

PPLX_BASE = "https://api.perplexity.ai"

def chat(messages: List[Dict[str, str]], model: Optional[str] = None, temperature: float = 0.2, timeout: float = 30.0) -> str:
    api_key = (os.getenv("PERPLEXITY_API_KEY") or "").strip()
    if not api_key:
        return ""
    mdl = (model or os.getenv("PPLX_MODEL") or "sonar").strip()
    # Valid model names as of 2025-10: sonar, sonar-pro, sonar-deep-research, sonar-reasoning, sonar-reasoning-pro
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": mdl, "messages": messages, "temperature": float(temperature)}
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(f"{PPLX_BASE}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except Exception:
        return ""
