# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Minimal Perplexity client wrapper with model guard and structured-output fallback.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, List
import os, httpx, time, json

API_URL = os.getenv("PPLX_URL", "https://api.perplexity.ai/chat/completions")
TIMEOUT = float(os.getenv("PPLX_TIMEOUT","30"))
MODEL = (os.getenv("PPLX_MODEL") or "").strip()
if MODEL.lower() in {"auto","best","default","", "none"} or "online" in MODEL.lower():
    MODEL = ""  # let platform choose

class PerplexityError(RuntimeError):
    pass

def chat(messages: List[Dict[str,str]], *, response_format: Optional[Dict[str,Any]] = None,
         model: Optional[str] = MODEL or None, temperature: float = 0.1, max_tokens: int = 900) -> Dict[str,Any]:
    key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or ""
    if not key:
        raise PerplexityError("Missing PPLX_API_KEY / PERPLEXITY_API_KEY")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body: Dict[str, Any] = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if response_format:
        body["response_format"] = response_format
    if model:
        body["model"] = model
    delays = [0.0, 0.6, 1.2, 2.4]
    start = time.monotonic()
    last_exc: Optional[Exception] = None
    with httpx.Client(timeout=TIMEOUT) as cli:
        for i, d in enumerate(delays, start=1):
            if d: time.sleep(d)
            try:
                r = cli.post(API_URL, headers=headers, json=body)
                if r.status_code in (408,429,502,503) and i < len(delays):
                    continue
                if r.status_code == 400 and "invalid model" in (r.text or "").lower():
                    body.pop("model", None)  # retry auto
                    r = cli.post(API_URL, headers=headers, json=body)
                if r.status_code == 400 and response_format:
                    # retry without schema
                    body.pop("response_format", None)
                    r = cli.post(API_URL, headers=headers, json=body)
                r.raise_for_status()
                return r.json()
            except Exception as exc:
                last_exc = exc
                continue
    raise PerplexityError(f"request failed after retries: {last_exc}")
# end of file
