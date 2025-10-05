# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live-Sektionen (News/Tools/Förderungen) mit optionalem Tavily/Perplexity.
- Wenn Keys fehlen oder SEARCH_PROVIDER='off': liefert deaktivierte Sektion mit sauberem Hinweis.
- Mit Keys: holt kompakte, aktuelle Ergebnisse + Quellenliste (Fußnoten-Stil).
"""

from __future__ import annotations
import os, time
from typing import Any, Dict, List
import re

try:
    import httpx  # type: ignore
    _http_ok = True
except Exception:
    _http_ok = False

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid").strip().lower()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "").strip()

SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "7"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "30"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "8"))

INCLUDE_DOMAINS = [d.strip() for d in os.getenv("SEARCH_INCLUDE_DOMAINS", "").split(",") if d.strip()]
EXCLUDE_DOMAINS = [d.strip() for d in os.getenv("SEARCH_EXCLUDE_DOMAINS", "").split(",") if d.strip()]

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
            # wenn Whitelist gesetzt ist, nur Whitelist zulassen
            continue
        out.append(it)
    return out

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
            out.append({"title": title, "url": url, "published": published, "score": score})
        return _filter_items(out)
    except Exception:
        return []

def _static_tools() -> List[Dict[str, Any]]:
    # Minimaler, geprüfter EU‑Stack als Fallback
    return [
        {"name": "Nextcloud", "desc": "On-Prem/DE‑Cloud für Files/Collab", "url": "https://nextcloud.com", "eu_host": True},
        {"name": "Matomo", "desc": "Web Analytics (self-hosted/EU)", "url": "https://matomo.org", "eu_host": True},
        {"name": "Jitsi Meet", "desc": "Videokonferenzen (self-hosted/EU möglich)", "url": "https://jitsi.org", "eu_host": True},
        {"name": "Odoo", "desc": "ERP/CRM – On‑Prem möglich", "url": "https://www.odoo.com", "eu_host": True},
    ]

def _static_funding() -> List[Dict[str, Any]]:
    return [
        {"name": "Digital Jetzt", "desc": "Investitionen in digitale Technologien", "url": "https://www.bmwk.de/Redaktion/DE/Dossier/digital-jetzt.html"},
        {"name": "go-digital", "desc": "Beratung: IT‑Sicherheit, Markterschließung, Prozesse", "url": "https://www.bmwi.de/Redaktion/DE/Dossier/go-digital.html"},
        {"name": "ZIM", "desc": "FuE‑Projekte für KMU", "url": "https://www.zim.de"},
    ]

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    # Deaktiviert & sauberer Hinweis
    if SEARCH_PROVIDER in {"off", "none"} or (not TAVILY_API_KEY and not PERPLEXITY_API_KEY):
        return {
            "enabled": False,
            "note": "Live‑Updates deaktiviert (API‑Keys nicht gesetzt).",
            "news": [], "tools": _static_tools(), "funding": _static_funding(),
            "sources": [],
        }

    q_base = f"{context.get('branche') or ''} {context.get('size') or ''} Deutschland"
    news = _tavily_search(f"news {q_base}", SEARCH_DAYS_NEWS)
    tools = _tavily_search(f"tools {q_base}", SEARCH_DAYS_TOOLS)
    fund = _tavily_search(f"Förderung {q_base}", SEARCH_DAYS_FUNDING)

    # Quellenliste (Fußnoten)
    sources = []
    for it in (news + tools + fund):
        dom = _domain(it.get("url",""))
        if not dom:
            continue
        sources.append({
            "id": len(sources) + 1,
            "title": it.get("title") or it.get("name") or dom,
            "domain": dom,
            "url": it.get("url"),
            "date": it.get("published") or "",
        })

    return {
        "enabled": True,
        "note": "",
        "news": news[:SEARCH_MAX_RESULTS],
        "tools": tools[:SEARCH_MAX_RESULTS] if tools else _static_tools(),
        "funding": fund[:SEARCH_MAX_RESULTS] if fund else _static_funding(),
        "sources": sources,
    }
