# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Perplexity API Client (Gold-Standard+)
- JSON-schema forcing, model guard, retry on invalid_model
- Conservative timeouts and structured logging via prints (service logs will capture stdout)
Env:
  PPLX_API_KEY / PERPLEXITY_API_KEY
  PPLX_MODEL   (leave empty for Best-Mode; 'auto','best','default' or any '*-online' are treated as None)
  PPLX_TIMEOUT_SEC (default 30)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional
import httpx
import os
import time
import json

def _effective_model(name: Optional[str]) -> Optional[str]:
    n = (name or "").strip()
    if not n or n.lower() in {"auto", "best", "default", "none"}:
        return None
    if "online" in n.lower():
        return None
    return n

@dataclass
class PerplexityClient:
    api_key: Optional[str] = None
    model: Optional[str] = _effective_model(os.getenv("PPLX_MODEL"))
    timeout_sec: float = float(os.getenv("PPLX_TIMEOUT_SEC", os.getenv("PPLX_TIMEOUT", "30")))
    base_url: str = "https://api.perplexity.ai/chat/completions"
    temperature: float = 0.3
    top_p: float = 0.9
    max_tokens: int = 700
    enable_backoff: bool = True

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
        if self.api_key:
            self.api_key = self.api_key.strip()

    def search_json(
        self,
        query: str,
        *,
        schema: Mapping[str, str],
        system: Optional[str] = None,
        max_items: int = 6,
        clamp_items: bool = True,
        extra_headers: Optional[Mapping[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        if not (self.api_key or "").strip():
            return []
        if not isinstance(schema, Mapping) or not schema:
            raise ValueError("search_json requires a non-empty schema mapping")

        schema_obj = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {k: {"type": v} for k, v in schema.items()},
                        "required": list(schema.keys()),
                        "additionalProperties": True,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        }

        system_msg = system or "You are a precise research agent. Return ONLY JSON, no explanations."
        payload: Dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": query[:2000]},
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"schema": schema_obj}},
        }
        model_eff = _effective_model(self.model)
        if model_eff:
            payload["model"] = model_eff

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update({k: v for k, v in extra_headers.items() if isinstance(k, str)})

        delays = [0.5, 1.2, 2.0] if self.enable_backoff else [0.0]
        last_err = None
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                time.sleep(delay)
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    resp = client.post(self.base_url, headers=headers, json=payload)

                if resp.status_code == 400 and "invalid_model" in (resp.text or "").lower():
                    # retry once without model
                    payload.pop("model", None)
                    with httpx.Client(timeout=self.timeout_sec) as client:
                        resp = client.post(self.base_url, headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
                    try:
                        obj = json.loads(content) if isinstance(content, str) else content
                        items = obj.get("items") or []
                        if clamp_items:
                            items = items[:max_items]
                        print(json.dumps({"evt": "perplexity_ok", "items": len(items)}, ensure_ascii=False))
                        return [it for it in items if isinstance(it, dict)]
                    except Exception as exc:
                        last_err = f"parse_error: {exc}"
                        print(json.dumps({"evt": "perplexity_parse_error", "error": str(exc)}, ensure_ascii=False))
                        return []
                elif resp.status_code in (401, 403, 404, 422):
                    print(json.dumps({"evt": "perplexity_fail", "status": resp.status_code}, ensure_ascii=False))
                    return []
                else:
                    last_err = f"http_{resp.status_code}"
                    print(json.dumps({"evt": "perplexity_retry", "status": resp.status_code, "attempt": attempt}, ensure_ascii=False))
            except Exception as exc:
                last_err = f"error:{type(exc).__name__}"
                print(json.dumps({"evt": "perplexity_error", "msg": str(exc)}, ensure_ascii=False))

        if last_err:
            print(json.dumps({"evt": "perplexity_final_fail", "error": last_err}, ensure_ascii=False))
        return []
