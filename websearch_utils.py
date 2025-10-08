# filename: backend/websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid Live Search (Tavily + Perplexity) – robust gegenüber 400/401,
mit Query-Trim, Zeitraum-Mapping und Header-Fallbacks.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

log = logging.getLogger("websearch_utils")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    log.addHandler(h)
log.setLevel(logging.INFO)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

# Perplexity Modelle: Fallback-Liste (Log zeigte invalid_model für 'sonar-small-online')
PPLX_MODELS = [os.getenv("PERPLEXITY_MODEL", "sonar-small"), "sonar", "sonar-medium"]

HTTP_TIMEOUT = float(os.getenv("LIVE_HTTP_TIMEOUT", "20"))
MAX_RESULTS_DEFAULT = int(os.getenv("LIVE_MAX_RESULTS", "6"))


def _trim_query(q: str, limit_chars: int = 350, limit_words: int = 24) -> str:
    q = (q or "").strip()
    q = re.sub(r"\s+", " ", q)
    words = q.split(" ")
    q = " ".join(words[:limit_words])
    return q[:limit_chars]


def _time_range_from_days(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


def _http_headers_json(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    base = {"Content-Type": "application/json"}
    if extra:
        base.update(extra)
    return base


def _tavily_headers() -> List[Dict[str, str]]:
    # Beide Varianten unterstützen (einige Setups erwarten x-api-key, andere Bearer)
    return [
        _http_headers_json({"x-api-key": TAVILY_API_KEY}),
        _http_headers_json({"Authorization": f"Bearer {TAVILY_API_KEY}"}),
    ]


def _tavily_payload(query: str, max_results: int, days: int, topic: str, country: Optional[str]) -> Dict[str, Any]:
    return {
        "query": query,
        "topic": topic if topic in ("news", "general") else "general",
        "max_results": max(1, min(int(max_results), 20)),
        "time_range": _time_range_from_days(days),  # <-- exakt wie API verlangt
        **({"search_depth": "basic"}),              # konservativ gegen 400er
        **({"include_domains": []}),
        **({"exclude_domains": []}),
        **({"include_answer": False}),
        **({"country": country} if country else {}),
    }


def _tavily_search(query: str, max_results: int, days: int, topic: str, country: Optional[str]) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        raise RuntimeError("Tavily API key missing")
    url = "https://api.tavily.com/search"
    payload = _tavily_payload(query, max_results, days, topic, country)
    last_error = None
    with httpx.Client(timeout=HTTP_TIMEOUT) as cli:
        for headers in _tavily_headers():
            try:
                r = cli.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json() or {}
                results = data.get("results") or data.get("data") or []
                items = []
                for it in results[:max_results]:
                    items.append(
                        {
                            "title": it.get("title") or it.get("name") or it.get("url"),
                            "url": it.get("url"),
                            "snippet": it.get("content") or it.get("snippet") or "",
                            "date": it.get("published_date") or it.get("date") or "",
                            "source": "Tavily",
                        }
                    )
                return items
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("Tavily failed: %s – %s", getattr(exc, "response", None), getattr(exc, "request", None))
                continue
    if last_error:
        raise last_error
    return []


def _pplx_messages(query: str, days: int, max_results: int, country: Optional[str]) -> List[Dict[str, str]]:
    # kompaktes Schema → JSON-Liste mit title/url/date zurückgeben
    since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    sys = (
        "You are a web research assistant. "
        "Return a concise JSON array with items: title, url, date (YYYY-MM-DD if available). "
        "No prose, no markdown, JSON only."
    )
    user = f"Query: {query}\nMax items: {max_results}\nCountry: {country or 'any'}\nSince: {since}"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _pplx_search(query: str, max_results: int, days: int, topic: str, country: Optional[str]) -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY:
        raise RuntimeError("Perplexity API key missing")
    url = "https://api.perplexity.ai/chat/completions"
    headers = _http_headers_json({"Authorization": f"Bearer {PERPLEXITY_API_KEY}"})
    messages = _pplx_messages(query, days, max_results, country)

    with httpx.Client(timeout=HTTP_TIMEOUT) as cli:
        last_error = None
        for model in PPLX_MODELS:
            try:
                payload = {"model": model, "messages": messages, "max_tokens": 400, "temperature": 0.0}
                r = cli.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json() or {}
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "[]"
                try:
                    arr = json.loads(content)
                except Exception:
                    # Notfall: rudimentäre Link-Extraktion
                    urls = re.findall(r"https?://[^\s)>\]]+", content)
                    arr = [{"title": u, "url": u, "date": ""} for u in urls]
                items = []
                for it in arr[:max_results]:
                    items.append(
                        {
                            "title": it.get("title") or it.get("url"),
                            "url": it.get("url"),
                            "snippet": "",
                            "date": it.get("date") or "",
                            "source": "Perplexity",
                        }
                    )
                return items
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("Perplexity failed for model %s: %s", model, getattr(exc, "response", None))
                continue
    if last_error:
        raise last_error
    return []


def hybrid_live_search(
    topic: str,
    briefing: Optional[Dict[str, Any]] = None,
    short_days: int = 7,
    long_days: int = 30,
    max_results: int = MAX_RESULTS_DEFAULT,
    country: Optional[str] = "DE",
) -> Dict[str, Any]:
    """
    Orchestriert Tavily→Perplexity mit Fallback (+ 30-Tage Fallback),
    trimmt Queries und dedupliziert Ergebnisse.
    """
    topic = topic or "news"
    q_base = f"{briefing.get('branche_label','')} {briefing.get('hauptleistung','')}".strip() if briefing else ""
    if topic == "tools":
        q = _trim_query(f"{q_base} KI-Tools DSGVO EU AI Act {briefing.get('unternehmensgroesse_label','')}")
    elif topic == "funding":
        q = _trim_query(f"{q_base} Förderprogramme Zuschuss Berlin Bund Mittelstand 2025")
    else:
        q = _trim_query(f"{q_base} KI News 2025 DSGVO EU AI Act")

    items: List[Dict[str, Any]] = []

    # 1) kurzer Zeitraum
    try:
        items = _tavily_search(q, max_results, short_days, "news", country)
    except Exception as exc:
        log.warning("Tavily short failed: %s", exc)

    if not items:
        try:
            items = _pplx_search(q, max_results, short_days, topic, country)
        except Exception as exc:
            log.warning("Perplexity short failed: %s", exc)

    # 2) 30-Tage-Fallback
    if not items:
        try:
            items = _tavily_search(q, max_results, long_days, "news", country)
        except Exception as exc:
            log.warning("Tavily long failed: %s", exc)

    if not items:
        try:
            items = _pplx_search(q, max_results, long_days, topic, country)
        except Exception as exc:
            log.warning("Perplexity long failed: %s", exc)

    # Dedupe
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for it in items:
        u = (it.get("url") or "").split("#")[0]
        if not u or u in seen:
            continue
        seen.add(u)
        deduped.append(it)

    return {"items": deduped[:max_results], "query": q, "from": "hybrid"}
    

# Abwärtskompatibler Alias (falls alter Code noch 'hybrid_search' ruft)
def hybrid_search(*args, **kwargs):
    return hybrid_live_search(*args, **kwargs)
