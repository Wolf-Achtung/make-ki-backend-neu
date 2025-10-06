# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid live search (Tavily + Perplexity) mit 7->30d-Fallback, Whitelist, Dedupe.
Rückgabe: [{title,url,source,date}]
"""
from __future__ import annotations
import datetime as dt
import json
import logging
import os
import re
from typing import Any, Dict, List, Tuple
import httpx

log = logging.getLogger("websearch_utils")
log.setLevel(logging.INFO)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "pplx-70b-online")

CFG_DIR = os.getenv("CFG_DIR", os.path.join(os.getcwd(), "config"))
LIVE_QUERIES_PATH = os.getenv("LIVE_QUERIES_PATH", os.path.join(CFG_DIR, "live_queries.json"))

ENV_INCLUDE = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS", "") or "").split(",") if d.strip()]
ENV_EXCLUDE = [d.strip() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS", "") or "").split(",") if d.strip()]
LIVE_TIMEOUT_S = float(os.getenv("LIVE_TIMEOUT_S", "8.0"))

def _strip_json_comments(s: str) -> str:
    # Entfernt //.. und /*..*/ und trailing commas rudimentär
    s = re.sub(r"\/\*.*?\*\/", "", s, flags=re.DOTALL)
    s = re.sub(r"^\s*\/\/.*?$", "", s, flags=re.MULTILINE)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s

def _load_whitelist(branche: str) -> Dict[str, Any]:
    """
    Lädt aus config/live_queries.json:
    {
      "default": { "include_domains": [], "queries": { "news": ["..."], "tools": [], "funding": [] } },
      "beratung": { ... }
    }
    """
    try:
        with open(LIVE_QUERIES_PATH, "r", encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(_strip_json_comments(raw) or "{}")
        out = data.get(branche) or data.get("default") or {}
        return {
            "include_domains": list({*ENV_INCLUDE, *out.get("include_domains", [])}),
            "queries": out.get("queries", {}),
        }
    except Exception as exc:
        log.warning("live_queries.json read failed: %s", exc)
        return {"include_domains": ENV_INCLUDE, "queries": {}}

def _days_to_tavily(days: int) -> str:
    # Tavily time_range: 'd7'/'d30'/...
    d = 7 if days <= 7 else (30 if days <= 30 else days)
    return f"d{d}"

def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""

def _tavily_search(q: str, days: int, include: List[str], exclude: List[str], max_results: int) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": q,
        "search_depth": os.getenv("SEARCH_DEPTH", "basic"),
        "max_results": max_results,
        "include_domains": include or None,  # nie []
        "exclude_domains": exclude or None,
        "topic": os.getenv("SEARCH_TOPIC", "news"),
        "time_range": _days_to_tavily(days),
    }
    try:
        with httpx.Client(timeout=LIVE_TIMEOUT_S) as cli:
            r = cli.post(url, json=payload)
            if r.status_code == 400 and days < 30:
                # Fallback: weniger Query-Wörter, 30 Tage, ohne Include-Liste
                payload["query"] = " ".join(q.split()[:8])
                payload["time_range"] = "d30"
                payload["include_domains"] = None
                r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            items = []
            for it in data.get("results", []):
                items.append({
                    "title": it.get("title") or it.get("url"),
                    "url": it.get("url"),
                    "source": it.get("website") or _domain(it.get("url") or ""),
                    "date": it.get("published_date") or "",
                })
            return items
    except Exception as exc:
        log.warning("Tavily failed: %s", exc)
        return []

def _perplexity_search(q: str, days: int, max_results: int) -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY:
        return []
    url = "https://api.perplexity.ai/chat/completions"
    since = (dt.date.today() - dt.timedelta(days=min(30, max(7, days)))).isoformat()
    sys = (
        "You are a web research assistant. Return a concise JSON array of items "
        "with keys: title, url, source, date (ISO), strictly from reputable sources."
    )
    user = f"Find up-to-date {q}. Consider only results since {since}. Respond with pure JSON."
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        "temperature": 0,
        "top_p": 1,
    }
    try:
        with httpx.Client(timeout=LIVE_TIMEOUT_S) as cli:
            r = cli.post(url, json=payload)
            if r.status_code == 400 and days < 30:
                # Simplify prompt and implicit 30d window
                payload["messages"][-1]["content"] = f"Find recent {q}. Respond with pure JSON."
                r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            txt = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "[]"
            # Perplexity kann mit Backticks antworten → entfernen
            txt = re.sub(r"```json|```", "", txt).strip()
            items = json.loads(txt)
            out = []
            for it in items[: max_results]:
                out.append({
                    "title": it.get("title") or it.get("url"),
                    "url": it.get("url"),
                    "source": it.get("source") or _domain(it.get("url") or ""),
                    "date": it.get("date") or "",
                })
            return out
    except Exception as exc:
        log.warning("Perplexity failed: %s", exc)
        return []

def _dedupe_merge(a: List[Dict[str, Any]], b: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for lst in (a, b):
        for it in lst:
            u = (it.get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            out.append(it)
            if len(out) >= max_items:
                return out
    return out

def _queries_for(topic: str, b: Dict[str, Any], wl: Dict[str, Any]) -> List[str]:
    base = wl.get("queries", {}).get(topic) or []
    # Kontextschärfung aus Briefing
    extra = []
    branche = b.get("branche") or ""
    hl = b.get("hauptleistung") or ""
    if topic == "news":
        extra.append(f"{branche} KI Digitalisierung Deutschland")
    elif topic == "tools":
        extra.append("KI Tools EU hosting DSGVO")
    elif topic == "funding":
        extra.append(f"Förderung {b.get('bundesland_code','DE')} KI Digitalisierung Mittelstand Frist")
    # Hauptleistung leicht andeuten
    if hl:
        extra.append(hl)
    # Entdoppeln
    seen = set()
    result = []
    for q in base + extra:
        q = " ".join(q.split())
        if q and q not in seen:
            seen.add(q)
            result.append(q)
    return result or ["KI Digitalisierung Deutschland"]

def hybrid_search(topic: str, briefing: Dict[str, Any], days: int, max_items: int) -> List[Dict[str, Any]]:
    """Kombiniert Tavily + Perplexity, 7->30d-Fallback passiert in den Unterfunktionen."""
    wl = _load_whitelist(briefing.get("branche") or "default")
    include = wl.get("include_domains", [])
    queries = _queries_for(topic, briefing, wl)

    tav_all: List[Dict[str, Any]] = []
    pplx_all: List[Dict[str, Any]] = []
    for q in queries[:3]:  # maximal 3 Queries pro Topic
        tav = _tavily_search(q, days=days, include=include, exclude=ENV_EXCLUDE, max_results=max_items)
        pplx = _perplexity_search(q, days=days, max_results=max_items)
        tav_all.extend(tav)
        pplx_all.extend(pplx)

    merged = _dedupe_merge(tav_all, pplx_all, max_items=max_items)
    return merged
