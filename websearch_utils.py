# filename: backend/websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid Live Search (Tavily + Perplexity) – robust gegen 400/401.
- Minimaler Tavily-Payload (query, max_results, time_range)
- Doppelte Header-Variante (x-api-key ODER Bearer)
- Query-Trim (≤350 Zeichen; ≤24 Wörter)
- Perplexity mit Modell-Fallback und robustem JSON-Parsing
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("websearch_utils")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    log.addHandler(h)
log.setLevel(logging.INFO)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

# konservative Fallbackliste; Logs zeigten 400 auf 'sonar-small'
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


def _headers_json(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    base = {"Content-Type": "application/json"}
    if extra:
        base.update(extra)
    return base


def _tavily_headers_variants() -> List[Dict[str, str]]:
    return [
        _headers_json({"x-api-key": TAVILY_API_KEY}),
        _headers_json({"Authorization": f"Bearer {TAVILY_API_KEY}"}),
    ]


def _tavily_payload(query: str, max_results: int, days: int) -> Dict[str, Any]:
    # Minimaler, API-stabiler Body
    return {
        "query": query,
        "max_results": max(1, min(int(max_results), 20)),
        "time_range": _time_range_from_days(days),
        "include_answer": False,
    }


def _tavily_search(query: str, max_results: int, days: int) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        raise RuntimeError("Tavily API key missing")
    url = "https://api.tavily.com/search"
    payload = _tavily_payload(query, max_results, days)
    last_error = None
    with httpx.Client(timeout=HTTP_TIMEOUT) as cli:
        for headers in _tavily_headers_variants():
            try:
                r = cli.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json() or {}
                results = data.get("results") or data.get("data") or []
                out: List[Dict[str, Any]] = []
                for it in results[:max_results]:
                    out.append({
                        "title": it.get("title") or it.get("name") or it.get("url"),
                        "url": it.get("url"),
                        "snippet": it.get("content") or it.get("snippet") or "",
                        "date": it.get("published_date") or it.get("date") or "",
                        "source": "Tavily",
                    })
                return out
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("Tavily failed: %s – %s", getattr(exc, "response", None), getattr(exc, "request", None))
                continue
    if last_error:
        raise last_error
    return []


def _pplx_messages(query: str, days: int, max_results: int, country: Optional[str]) -> List[Dict[str, str]]:
    since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
    sys = ("You are a research assistant. Return ONLY a compact JSON array of items "
           "[{title,url,date}] – no prose, no markdown.")
    user = f"Query: {query}\nMax items: {max_results}\nCountry: {country or 'any'}\nSince: {since}"
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _pplx_search(query: str, max_results: int, days: int, country: Optional[str]) -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY:
        raise RuntimeError("Perplexity API key missing")
    url = "https://api.perplexity.ai/chat/completions"
    headers = _headers_json({"Authorization": f"Bearer {PERPLEXITY_API_KEY}"})
    last_error = None
    with httpx.Client(timeout=HTTP_TIMEOUT) as cli:
        for model in PPLX_MODELS:
            try:
                payload = {"model": model, "messages": _pplx_messages(query, days, max_results, country),
                           "max_tokens": 400, "temperature": 0.0}
                r = cli.post(url, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json() or {}
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "[]"
                try:
                    arr = json.loads(content)
                except Exception:
                    # Notfall: Links parsen, wenn kein valides JSON zurückkommt
                    urls = re.findall(r"https?://[^\s)>\]]+", content)
                    arr = [{"title": u, "url": u, "date": ""} for u in urls]
                out: List[Dict[str, Any]] = []
                for it in arr[:max_results]:
                    out.append({
                        "title": it.get("title") or it.get("url"),
                        "url": it.get("url"),
                        "snippet": "",
                        "date": it.get("date") or "",
                        "source": "Perplexity",
                    })
                return out
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
    Tavily → Perplexity → 30‑Tage‑Fallback, Query-Trim & Dedupe.
    """
    topic = (topic or "news").lower()
    b = briefing or {}
    # kurze, robuste Query
    base = f"{b.get('branche_label','')} {b.get('hauptleistung','')}".strip()
    if topic == "tools":
        q = _trim_query(f"{base} KI Tools DSGVO EU AI Act KMU 2025")
    elif topic == "funding":
        q = _trim_query(f"{base} Förderprogramme Zuschuss Berlin Bund Mittelstand 2025")
    else:
        q = _trim_query(f"{base} KI News 2025 DSGVO EU AI Act Deutschland")

    items: List[Dict[str, Any]] = []

    # 7‑Tage Fenster
    try:
        items = _tavily_search(q, max_results, short_days)
    except Exception as exc:
        log.warning("Tavily short failed: %s", exc)

    if not items:
        try:
            items = _pplx_search(q, max_results, short_days, country)
        except Exception as exc:
            log.warning("Perplexity short failed: %s", exc)

    # 30‑Tage Fallback
    if not items:
        try:
            items = _tavily_search(q, max_results, long_days)
        except Exception as exc:
            log.warning("Tavily long failed: %s", exc)

    if not items:
        try:
            items = _pplx_search(q, max_results, long_days, country)
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


# Abwärtskompatibel
def hybrid_search(*args, **kwargs):
    return hybrid_live_search(*args, **kwargs)
