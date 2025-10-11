
# filename: perplexity_client.py
# -*- coding: utf-8 -*-
"""
Perplexity API Client (Gold-Standard+)

- Enforces JSON responses via `response_format = json_schema`
- Clean headers, retries on 429/5xx, fail-fast on 400/422
- Structured logging
- **Model guard:** If PPLX_MODEL is "", "auto", "best", "default" or contains "-online", omit the model field (Best‑Mode).

Env:
  PPLX_API_KEY       : required (or PERPLEXITY_API_KEY)
  PPLX_MODEL         : optional; default AUTO (omit field)
  PPLX_TIMEOUT_SEC   : default 30
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

import httpx

log = logging.getLogger("perplexity")

def _model_effective() -> Optional[str]:
    name = (os.getenv("PPLX_MODEL") or "").strip()
    if not name:
        return None
    low = name.lower()
    if low in {"auto", "best", "default", "none"}:
        return None
    if "online" in low:
        # legacy names like sonar-medium-online are no longer valid
        return None
    return name

@dataclass
class PerplexityClient:
    api_key: Optional[str] = None
    model: Optional[str] = _model_effective()
    timeout_sec: float = float(os.getenv("PPLX_TIMEOUT_SEC", os.getenv("PPLX_TIMEOUT", "30")))
    base_url: str = "https://api.perplexity.ai/chat/completions"
    temperature: float = 0.3
    top_p: float = 0.9
    max_tokens: int = 700
    enable_backoff: bool = True

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            log.warning("PerplexityClient initialised without API key – skipping requests.")
        else:
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
        if not self.api_key:
            return []
        if not isinstance(schema, Mapping) or not schema:
            raise ValueError("search_json requires a non-empty schema mapping")

        safe_query = (query or "").strip()
        if not safe_query:
            return []
        if len(safe_query) > 2000:
            safe_query = safe_query[:2000] + " …"

        schema_obj = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {k: {"type": v} for k, v in schema.items()},
                    },
                }
            },
            "required": ["items"],
        }

        system_msg = system or (
            "You are a precise research agent. Return ONLY JSON. No explanations."
        )

        payload: Dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": safe_query},
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"schema": schema_obj}},
        }
        # Model guard
        if self.model:
            payload["model"] = self.model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update({k: v for k, v in extra_headers.items() if isinstance(k, str)})

        backoff_delays = [0.5, 1.2, 2.0] if self.enable_backoff else [0.0]

        last_err: Optional[str] = None
        for attempt, delay in enumerate(backoff_delays, start=1):
            if delay:
                time.sleep(delay)
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    resp = client.post(self.base_url, headers=headers, json=payload)
                # Retry without model if invalid
                if resp.status_code == 400 and "invalid_model" in (resp.text or "").lower() and "model" in payload:
                    log.warning("Perplexity invalid_model -> retrying without model")
                    payload.pop("model", None)
                    with httpx.Client(timeout=self.timeout_sec) as client:
                        resp = client.post(self.base_url, headers=headers, json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    content = self._extract_content(data)
                    items = self._safe_parse_items(content)
                    if clamp_items and items:
                        items = items[:max_items]
                    log.info("Perplexity ok [%s] items=%s", self.model or "auto", len(items))
                    return items
                elif resp.status_code in (400, 401, 403, 404, 422):
                    log.warning("Perplexity %s on attempt %s: %s", resp.status_code, attempt, self._short(resp.text))
                    return []
                else:
                    last_err = f"HTTP {resp.status_code}: {self._short(resp.text)}"
                    log.warning("Perplexity %s; attempt=%s; will retry if allowed", resp.status_code, attempt)
            except Exception as exc:
                last_err = str(exc)
                log.exception("Perplexity request failed on attempt %s: %s", attempt, exc)

        if last_err:
            log.warning("Perplexity ultimately failed: %s", last_err)
        return []

    # helpers

    @staticmethod
    def _extract_content(data: Mapping[str, Any]) -> Optional[str]:
        try:
            choices = data.get("choices") or []
            if not choices:
                return None
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [seg.get("text") if isinstance(seg, dict) else str(seg) for seg in content]
                return "".join(p for p in parts if p)
        except Exception:
            return None
        return None

    @staticmethod
    def _safe_parse_items(content: Optional[str]) -> List[Dict[str, Any]]:
        if not content:
            return []
        try:
            obj = json.loads(content)
            items = obj.get("items")
            if isinstance(items, list):
                return [it for it in items if isinstance(it, dict)]
        except Exception:
            log.warning("Perplexity returned non-JSON content: %s", PerplexityClient._short(content, 160))
        return []

    @staticmethod
    def _short(text: str, limit: int = 400) -> str:
        s = str(text or "")
        return s if len(s) <= limit else s[: limit - 1] + "…"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client = PerplexityClient()
    schema = {"title": "string", "source": "string", "url": "string", "date": "string"}
    res = client.search_json(
        "Aktuelle KI-Förderprogramme in Berlin (letzte 60 Tage). Nenne Titel, Quelle, URL, Datum.",
        schema=schema,
        max_items=5,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
