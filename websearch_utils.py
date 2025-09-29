# websearch_utils.py — Live Updates (News/Tools/Förderungen) mit Tavily
# Gold-Standard+: sauberes Caching, robuste Defaults, HTML-Renderer
# Stand: 2025-09-29

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

log = logging.getLogger("websearch")

# ---------------------------------------------------------------------------
# Konfiguration via ENV
# ---------------------------------------------------------------------------
TAVILY_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
PROVIDER = (os.getenv("SEARCH_PROVIDER") or "tavily").strip().lower()

# Zeitfenster & Ergebnisse
DAYS_GENERIC = int(os.getenv("SEARCH_DAYS", "30"))
DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "90"))
MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "6"))
DEPTH = (os.getenv("SEARCH_DEPTH") or "advanced").strip()

# Domain-Filter (Whitelist/Blacklist, komma-separiert)
INCLUDE_DOMAINS = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS") or "").split(",") if d.strip()]
EXCLUDE_DOMAINS = [d.strip() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS") or "").split(",") if d.strip()]

# Throttling / Cache
CACHE_TTL = int(os.getenv("TAVILY_CACHE_TTL", "3600"))
_THROTTLE_PER_REPORT = float(os.getenv("SEARCH_THROTTLE_PER_REPORT", "0.0"))

# ---------------------------------------------------------------------------
# Einfacher TTL-Cache
# ---------------------------------------------------------------------------
_CACHE: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}


def _cache_get(key: Tuple[Any, ...]) -> Optional[Any]:
    now = time.time()
    hit = _CACHE.get(key)
    if not hit:
        return None
    ts, val = hit
    if now - ts <= CACHE_TTL:
        return val
    _CACHE.pop(key, None)
    return None


def _cache_set(key: Tuple[Any, ...], val: Any) -> None:
    _CACHE[key] = (time.time(), val)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
def _tavily_search(query: str, num: int, recency_days: int) -> List[Dict[str, Any]]:
    if not TAVILY_KEY:
        raise RuntimeError("TAVILY_API_KEY missing")
    payload = {
        "query": query,
        "search_depth": DEPTH,
        "include_answer": False,
        "max_results": num,
        "days": recency_days,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TAVILY_KEY}"}
    with httpx.Client(timeout=30) as client:
        r = client.post("https://api.tavily.com/search", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    results = data.get("results", [])
    out: List[Dict[str, Any]] = []
    for it in results:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        domain = url.split("/")[2] if "://" in url else url
        if INCLUDE_DOMAINS and not any(d for d in INCLUDE_DOMAINS if d in domain):
            continue
        if EXCLUDE_DOMAINS and any(d for d in EXCLUDE_DOMAINS if d in domain):
            continue
        out.append(
            {
                "title": (it.get("title") or "").strip(),
                "url": url,
                "snippet": (it.get("content") or "").strip()[:260],
                "date": (it.get("published_date") or "").strip(),
                "source": domain,
                "score": float(it.get("score") or 0),
            }
        )
    return out


def _search(query: str, num: int, recency_days: int) -> List[Dict[str, Any]]:
    key = ("search", PROVIDER, query, num, recency_days, tuple(INCLUDE_DOMAINS), tuple(EXCLUDE_DOMAINS))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    if _THROTTLE_PER_REPORT > 0:
        time.sleep(_THROTTLE_PER_REPORT)

    if PROVIDER == "tavily":
        results = _tavily_search(query, num, recency_days)
    else:
        # Fallback: benutze trotzdem Tavily (einziger aktivierter Provider)
        results = _tavily_search(query, num, recency_days)

    _cache_set(key, results)
    return results


# ---------------------------------------------------------------------------
# HTML-Renderer
# ---------------------------------------------------------------------------
def _make_link_list_html(title: str, links: List[Dict[str, Any]], lang: str) -> str:
    if not links:
        return ""
    label = "Quellen (aktuell)" if lang.startswith("de") else "Sources (recent)"
    html = [f'<section class="info-box tip"><div class="info-box-title">{title}</div>']
    html.append('<ul style="margin:0;padding-left:16px">')
    for it in links:
        t = (it.get("title") or it.get("url") or "").strip()
        u = (it.get("url") or "").strip()
        s = (it.get("snippet") or "").strip()
        meta_items = [x for x in [(it.get("date") or "").strip(), (it.get("source") or "").strip()] if x]
        meta = " · ".join(meta_items)
        html.append(
            f'<li style="margin:6px 0;"><a href="{u}">{t}</a>'
            + (f'<div style="color:#6B7280;font-size:9pt">{meta}</div>' if meta else "")
            + (f"<p style='margin:4px 0 0 0'>{s}</p>" if s else "")
            + "</li>"
        )
    html.append(f"</ul><div style='margin-top:6px;color:#6B7280;font-size:9pt'>{label}</div></section>")
    return "\n".join(html)


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------
def collect_recent_items(ctx: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """
    Liefert für das übergebene Kontext-Objekt HTML-Blöcke und optionale Tabellen:
      - news_html
      - tools_rich_html  (Links)
      - funding_rich_html (Links)
      - tools_table (optional, sofern erkannt)
      - foerderprogramme_table (optional)
    Steuerung erfolgt über ENV-Variablen (siehe Kopf).
    """
    branche = (ctx.get("branche") or "KI").strip()
    region = (ctx.get("bundesland") or "").strip()
    topic_override = (os.getenv("SEARCH_TOPIC") or "").strip()

    # Query-Strings
    news_q = topic_override or (f"{branche} KI News" if lang.startswith("de") else f"{branche} AI news")
    tools_q = f"{branche} AI tools" if not lang.startswith("de") else f"{branche} KI Tools"
    fund_q = f"{branche} Förderprogramm {region}" if lang.startswith("de") else f"{branche} funding program {region or 'DE'}"

    news = _search(news_q, MAX_RESULTS, DAYS_GENERIC)
    tools = _search(tools_q, MAX_RESULTS, DAYS_TOOLS)
    funds = _search(fund_q, MAX_RESULTS, DAYS_FUNDING)

    out: Dict[str, Any] = {}
    if news:
        out["news_html"] = _make_link_list_html("Aktuelle Nachrichten" if lang.startswith("de") else "Latest News", news, lang)
    if tools:
        out["tools_rich_html"] = _make_link_list_html("Neue/aktuelle Tools", tools, lang)
        # Optionale 2-Spalten-Tabelle mit Toolname/Link
        out["tools_table"] = [{"name": i.get("title") or "Tool", "url": i.get("url")} for i in tools]
    if funds:
        out["funding_rich_html"] = _make_link_list_html("Aktuelle Förderoptionen", funds, lang)
        out["foerderprogramme_table"] = [{"name": i.get("title") or "Programm", "url": i.get("url")} for i in funds]

    return out
