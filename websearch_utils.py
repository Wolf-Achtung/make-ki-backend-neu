# -*- coding: utf-8 -*-
"""
Hybrid Live Search for Tavily + Perplexity
Gold-Standard+ (2025-10-07)

- Sanitizes and trims queries to avoid 400 on Tavily (<= 350 chars, ~12 words).
- Correct Perplexity headers/body; supports query, max_results (1..20), country.
- 7-day window with 30-day fallback. Normalizes items and deduplicates by URL.
- Defensive error handling with structured logging for QA.
- Backward-compat alias: hybrid_search(topic, briefing, days, max_items) -> List[items]

Env:
  TAVILY_API_KEY
  PERPLEXITY_API_KEY
  PERPLEXITY_MODEL (default: sonar-small-online)
  DEFAULT_COUNTRY (default: DE)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

LOG = logging.getLogger("websearch_utils")
LOG.setLevel(logging.INFO)

TAVILY_ENDPOINT = "https://api.tavily.com/search"
PPLX_ENDPOINT = "https://api.perplexity.ai/chat/completions"

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
PPLX_API_KEY = os.getenv("PERPLEXITY_API_KEY", "").strip()
PPLX_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-small-online")
DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", "DE")

HTTP_TIMEOUT = float(os.getenv("LIVE_HTTP_TIMEOUT", "20"))

# ---------- Helpers ----------

def _first_n_words(s: str, n: int = 12) -> str:
    if not isinstance(s, str):
        return ""
    words = s.strip().split()
    return " ".join(words[:n])

def _clip(s: str, max_len: int = 350) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s.strip())
    if len(s) <= max_len:
        return s
    return s[:max_len].rstrip()

def _today_iso() -> str:
    return date.today().isoformat()

def _fallback_dates(days: int) -> Tuple[str, str]:
    since = date.today() - timedelta(days=days)
    return since.isoformat(), _today_iso()

def _dedupe(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        url = (it.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(it)
    return out


@dataclass
class SearchItem:
    title: str
    url: str
    snippet: str = ""
    date: str = ""
    source: str = ""
    provider: str = ""  # "tavily" or "perplexity"

# ---------- Query builder ----------

def build_queries(topic: str, briefing: Dict[str, Any]) -> List[str]:
    """Compact, precise queries to reduce noise and avoid 400s."""
    branche = (briefing.get("branche_label") or briefing.get("branche") or "").strip()
    region = (briefing.get("bundesland_code") or DEFAULT_COUNTRY).strip() or DEFAULT_COUNTRY
    haupt = _first_n_words(briefing.get("hauptleistung") or "", 12)

    base: List[str] = []
    if topic == "news":
        base = [
            f"{branche} KI News {region}",
            f"{branche} KI Trends {region}",
            f"{branche} KI Regulatorik EU AI Act {region}",
        ]
    elif topic == "tools":
        base = [
            f"{branche} KI Tools {region}",
            f"beste KI Werkzeuge KMU {region}",
        ]
    elif topic == "funding":
        base = [
            f"KI Förderprogramme {region}",
            f"{branche} Digitalisierung Förderung {region}",
        ]
    else:
        base = [f"{branche} KI {topic} {region}"]

    if haupt:
        base = [f"{q} für {haupt}" for q in base]

    # Trim to safe length for Tavily
    return [_clip(q, 350) for q in base if q.strip()]

# ---------- Tavily ----------

def _tavily_request_json(payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    with httpx.Client(timeout=HTTP_TIMEOUT) as client:
        r = client.post(TAVILY_ENDPOINT, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()

def _tavily_search_once(query: str, max_results: int, days: int) -> List[SearchItem]:
    """Try multiple auth styles to be robust across deployments."""
    if not TAVILY_API_KEY:
        LOG.warning("Tavily: Kein API-Key gesetzt – überspringe.")
        return []

    payload = {
        "query": query,
        "max_results": max(1, min(max_results, 20)),  # defensive bound
        "search_depth": "basic",
        # einige Deployments erwarten 'time_range' in Tagen (Format "d7")
        "time_range": f"d{max(1, min(days, 365))}",
        "include_answer": False,
    }

    headers_variants = [
        {"Content-Type": "application/json", "Authorization": f"Bearer {TAVILY_API_KEY}"},
        {"Content-Type": "application/json", "x-api-key": TAVILY_API_KEY},
    ]

    errors: List[str] = []
    for headers in headers_variants:
        try:
            data = _tavily_request_json(payload, headers)
            results = data.get("results") or data.get("data") or []
            items: List[SearchItem] = []
            for r in results:
                items.append(SearchItem(
                    title=(r.get("title") or "").strip(),
                    url=(r.get("url") or r.get("link") or "").strip(),
                    snippet=(r.get("content") or r.get("snippet") or "").strip(),
                    date=(r.get("published_date") or r.get("date") or "").strip(),
                    source=(r.get("source") or "").strip(),
                    provider="tavily",
                ))
            return [asdict(x) for x in items if x.url and x.title]
        except httpx.HTTPStatusError as e:
            text = e.response.text[:200]
            LOG.warning("Tavily failed: %s – %s", e, text)
            errors.append(f"{e} :: {text}")
            # 400 häufig: zu lange Query → Caller erhält Chance, Fallback zu nutzen.
            time.sleep(0.2)
        except Exception as e:  # noqa
            LOG.warning("Tavily error: %s", e)
            errors.append(str(e))
            time.sleep(0.2)

    LOG.debug("Tavily alle Varianten fehlgeschlagen: %s", "; ".join(errors))
    return []

def tavily_search(queries: List[str], max_results: int, days: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for q in queries:
        if not q:
            continue
        items.extend(_tavily_search_once(q, max_results=max_results, days=days))
        if len(items) >= max_results:
            break
    return _dedupe(items)[:max_results]

# ---------- Perplexity ----------

def _parse_pplx_json(text: str) -> List[Dict[str, Any]]:
    """Best-effort parsing of a JSON array in model output."""
    text = text.strip()
    # direct JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict) and "items" in obj and isinstance(obj["items"], list):
            return obj["items"]
    except Exception:
        pass
    # find first [...] block
    m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []

def perplexity_search(queries: List[str], max_results: int, days: int,
                      country: str = DEFAULT_COUNTRY) -> List[Dict[str, Any]]:
    if not PPLX_API_KEY:
        LOG.warning("Perplexity: Kein API-Key gesetzt – überspringe.")
        return []

    since, _ = _fallback_dates(days)

    headers = {
        "Authorization": f"Bearer {PPLX_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    items: List[Dict[str, Any]] = []

    for q in queries:
        payload = {
            "model": PPLX_MODEL,
            "temperature": 0,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a web research assistant. "
                        "Return ONLY a JSON array of objects with: "
                        "title, url, snippet, date, source. "
                        f"Country filter: {country}. Time window: since {since}. "
                        "No prose, no markdown, no additional text."
                    ),
                },
                {"role": "user", "content": q},
            ],
        }
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT) as client:
                r = client.post(PPLX_ENDPOINT, headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                content = (
                    (data.get("choices") or [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                arr = _parse_pplx_json(content)
                for o in arr:
                    items.append({
                        "title": (o.get("title") or "").strip(),
                        "url": (o.get("url") or "").strip(),
                        "snippet": (o.get("snippet") or o.get("summary") or "").strip(),
                        "date": (o.get("date") or "").strip(),
                        "source": (o.get("source") or "").strip(),
                        "provider": "perplexity",
                    })
        except httpx.HTTPStatusError as e:
            LOG.warning("Perplexity failed: %s – %s", e, e.response.text[:200])
            if e.response.status_code in (401, 403, 429, 500):
                time.sleep(0.5)
        except Exception as e:  # noqa
            LOG.warning("Perplexity error: %s", e)
            time.sleep(0.2)

        if len(items) >= max_results:
            break

    return _dedupe(items)[:max_results]

# ---------- Hybrid orchestrator ----------

def hybrid_live_search(
    topic: str,
    briefing: Dict[str, Any],
    country: str = DEFAULT_COUNTRY,
    short_days: int = 7,
    long_days: int = 30,
    max_results: int = 10,
    prefer: str = "tavily",  # or "perplexity" / "balanced"
) -> Dict[str, Any]:
    """
    Run Tavily + Perplexity. Try short window first; if empty or underfilled, use long window.
    Returns: {"items": [...], "stand": YYYY-MM-DD, "provider_stats": {...}}
    """
    stand = _today_iso()
    queries = build_queries(topic, briefing)

    def collect(days: int) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        stats = {"tavily": 0, "perplexity": 0}
        all_items: List[Dict[str, Any]] = []
        order = {
            "tavily": tavily_search(queries, max_results=max_results, days=days),
            "perplexity": perplexity_search(queries, max_results=max_results, days=days, country=country),
        }
        seq = ["tavily", "perplexity"] if prefer == "tavily" else \
              ["perplexity", "tavily"] if prefer == "perplexity" else \
              ["tavily", "perplexity"]

        for name in seq:
            items = order[name]
            stats[name] = len(items)
            all_items.extend(items)

        all_items = _dedupe(all_items)
        return all_items[:max_results], stats

    items, stats = collect(short_days)
    if len(items) < max_results // 2:
        more, stats2 = collect(long_days)
        items = _dedupe(items + more)[:max_results]
        stats = {k: stats.get(k, 0) + stats2.get(k, 0) for k in set(stats) | set(stats2)}

    return {"items": items, "stand": stand, "provider_stats": stats}

# ---------- Backward-compat alias ----------

def hybrid_search(topic: str, briefing: Dict[str, Any], days: int, max_items: int) -> List[Dict[str, Any]]:
    """
    Backward compatible wrapper expected by some callers:
      - 'days' becomes short window; long window defaults to max(30, days).
      - Returns a list of items (not the dict with stats/stand).
    """
    res = hybrid_live_search(
        topic=topic,
        briefing=briefing,
        country=(briefing.get("bundesland_code") or DEFAULT_COUNTRY),
        short_days=max(1, min(days, 30)),
        long_days=max(30, days),
        max_results=max_items,
        prefer=os.getenv("LIVE_PREFER", "tavily"),
    )
    return res.get("items", [])
