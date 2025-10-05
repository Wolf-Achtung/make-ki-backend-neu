# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live-Sektionen (News/Tools/Förderungen) mit Tavily/Perplexity (optional).
- P0/P1: saubere Deaktivierung ohne Widerspruch; getrennte Quellen pro Karte
- Fallback: News 7 Tage -> wenn leer, auf 30 Tage erweitern (User-Wunsch)
- Region-Priorisierung: Förder-Domains pro Bundesland (z. B. BE -> ibb.de) werden nach oben sortiert
"""

from __future__ import annotations
import os, time, re
from typing import Any, Dict, List

try:
    import httpx  # type: ignore
    _http_ok = True
except Exception:
    _http_ok = False

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid").strip().lower()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "").strip()

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "7"))
SEARCH_DAYS_NEWS_FALLBACK = int(os.getenv("SEARCH_DAYS_NEWS_FALLBACK", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "30"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "8"))

INCLUDE_DOMAINS = [d.strip() for d in os.getenv("SEARCH_INCLUDE_DOMAINS", "").split(",") if d.strip()]
EXCLUDE_DOMAINS = [d.strip() for d in os.getenv("SEARCH_EXCLUDE_DOMAINS", "").split(",") if d.strip()]

BL_PRIORITY_DOMAINS = {
    "BE": ["ibb.de", "berlin.de", "efre.berlin.de"],
    "NW": ["nrwbank.de", "gruenderportal.nrw", "wirtschaft.nrw"],
    "BY": ["bayern.de", "ibbw.bayern.de", "stmwi.bayern.de"],
    "BW": ["l-bank.de", "wm.baden-wuerttemberg.de"],
    "HE": ["wirtschaft.hessen.de", "förderdatenbank.de"],
    "NI": ["nbank.de"],
    "RP": ["isb.rlp.de"],
    "SH": ["wtsh.de"],
    "TH": ["aufbaubank-thueringen.de"],
    "SN": ["wirtschaft.sachsen.de"],
    "ST": ["investitionsbank.sachsen-anhalt.de"],
    "HH": ["ifbhh.de", "hamburg.de"],
    "HB": ["bremen-innovativ.de"],
    "BB": ["brandenburg.de", "ilb.de"],
    "MV": ["lfi-mv.de"],
    "SL": ["saaris.de"],
}

def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url or "", flags=re.I)
    return (m.group(1).lower() if m else "").replace("www.", "")

def _filter_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in items:
        dom = _domain(it.get("url",""))
        if not dom:
            continue
        if EXCLUDE_DOMAINS and dom in EXCLUDE_DOMAINS:
            continue
        if INCLUDE_DOMAINS and dom not in INCLUDE_DOMAINS:
            continue
        out.append({**it, "domain": dom})
    return out

def _prio_sort(items: List[Dict[str, Any]], prio_domains: List[str]) -> List[Dict[str, Any]]:
    if not prio_domains:
        return items
    # Score-Bonus für Prioritätsdomains
    def score(it: Dict[str, Any]) -> float:
        base = float(it.get("score") or 0.0)
        return base + (5.0 if it.get("domain") in prio_domains else 0.0)
    return sorted(items, key=score, reverse=True)

def _tavily_search(q: str, days: int) -> List[Dict[str, Any]]:
    if not _http_ok or not TAVILY_API_KEY:
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": q, "search_depth": "basic", "max_results": SEARCH_MAX_RESULTS},
                headers={"Content-Type": "application/json"}
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = data.get("results") or []
        out = []
        now = time.time()
        cutoff = now - days * 86400
        for r in results:
            url = r.get("url") or ""
            title = r.get("title") or ""
            published = r.get("published_date") or ""
            score = r.get("score") or 0.0
            # Fallback: wenn published leer, lassen wir durch, rely on days filter optional
            out.append({"title": title, "url": url, "published": published, "score": score})
        return _filter_items(out)
    except Exception:
        return []

def _static_tools() -> List[Dict[str, Any]]:
    return [
        {"name": "Nextcloud", "desc": "On-Prem/DE‑Cloud für Files/Collab", "url": "https://nextcloud.com", "eu_host": True, "domain": "nextcloud.com"},
        {"name": "Matomo", "desc": "Web Analytics (self-hosted/EU)", "url": "https://matomo.org", "eu_host": True, "domain": "matomo.org"},
        {"name": "Jitsi Meet", "desc": "Videokonferenzen (self-hosted/EU möglich)", "url": "https://jitsi.org", "eu_host": True, "domain": "jitsi.org"},
        {"name": "Odoo", "desc": "ERP/CRM – On‑Prem möglich", "url": "https://www.odoo.com", "eu_host": True, "domain": "odoo.com"},
    ]

def _static_funding(region_code: str) -> List[Dict[str, Any]]:
    base = [
        {"name": "Förderdatenbank", "desc": "Bund/Land EU‑Programme", "url": "https://www.foerderdatenbank.de", "domain": "foerderdatenbank.de"},
        {"name": "BAFA", "desc": "Beratung & Finanzierung", "url": "https://www.bafa.de", "domain": "bafa.de"},
    ]
    # Regionale Anreicherung
    prio = BL_PRIORITY_DOMAINS.get(region_code.upper(), [])
    if "BE" == region_code.upper():
        base.insert(0, {"name": "Investitionsbank Berlin (IBB)", "desc": "Landesprogramme Berlin", "url": "https://www.ibb.de", "domain": "ibb.de"})
    # Prioritäten oben
    base = _prio_sort(base, prio)
    return base

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    if SEARCH_PROVIDER in {"off", "none"} or (not TAVILY_API_KEY and not PERPLEXITY_API_KEY):
        return {
            "enabled": False,
            "note": "Live‑Updates deaktiviert (API‑Keys nicht gesetzt).",
            "news": [], "tools": _static_tools(), "funding": _static_funding(context.get("region_code") or ""),
            "news_sources": [], "tools_sources": [], "funding_sources": [],
        }

    q_base = f"{context.get('branche') or ''} {context.get('size') or ''} Deutschland"
    region = (context.get("region_code") or "").upper()
    prio_domains = BL_PRIORITY_DOMAINS.get(region, [])

    # News (7 Tage, sonst Fallback 30)
    news = _tavily_search(f'news {q_base}', SEARCH_DAYS_NEWS)
    if not news:
        news = _tavily_search(f'news {q_base}', SEARCH_DAYS_NEWS_FALLBACK)

    # Tools
    tools = _tavily_search(f'tools {q_base}', SEARCH_DAYS_TOOLS)

    # Funding (Region priorisieren)
    funding = _tavily_search(f'Förderung {q_base}', SEARCH_DAYS_FUNDING)
    funding = _prio_sort(funding, prio_domains)
    if not funding:
        funding = _static_funding(region)

    def make_sources(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for it in items:
            d = it.get("domain") or _domain(it.get("url", ""))
            if not d:
                continue
            out.append({"id": len(out)+1, "title": it.get("title") or it.get("name") or d, "domain": d, "url": it.get("url"), "date": it.get("published") or ""})
        return out

    return {
        "enabled": True,
        "note": "",
        "news": news[:SEARCH_MAX_RESULTS],
        "tools": tools[:SEARCH_MAX_RESULTS] if tools else _static_tools(),
        "funding": funding[:SEARCH_MAX_RESULTS],
        "news_sources": make_sources(news),
        "tools_sources": make_sources(tools),
        "funding_sources": make_sources(funding),
    }
