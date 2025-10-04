# File: websearch_utils.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List, Tuple
import httpx

from live_cache import cache_get, cache_set

EU_ISO = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT",
    "LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE","IS","NO","LI"
}

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _hash_key(x: str) -> str:
    return hashlib.sha256(x.encode("utf-8")).hexdigest()

def build_queries(ctx: Dict[str, Any]) -> List[str]:
    parts = [
        _clean(ctx.get("branche") or ""),
        _clean(ctx.get("size") or ""),
        "KI Mittelstand Deutschland 2025",
        "EU AI Act Leitlinien 2025 site:digital-strategy.ec.europa.eu",
        "Förderprogramme Digitalisierung KI Deutschland 2025",
        "DSGVO KI Tools Unternehmen 2025",
    ]
    q = [p for p in parts if p]
    return q[:6] or ["KI Mittelstand Deutschland 2025"]

def tavily_search(query: str, days: int = 30, max_results: int = 6) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY or not query:
        return []
    try:
        with httpx.Client(timeout=18) as cli:
            r = cli.post(
                "https://api.tavily.com/search",
                json={"query": query, "search_depth": "advanced", "days": days, "max_results": max_results},
                headers={"Content-Type": "application/json", "X-Tavily-Key": TAVILY_API_KEY},
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("results", [])[:max_results]
    except Exception:
        pass
    return []

def perplexity_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY or not query:
        return []
    try:
        with httpx.Client(timeout=20) as cli:
            r = cli.post(
                "https://api.perplexity.ai/chat/completions",
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": query}],
                    "max_tokens": 600,
                },
                headers={"Authorization": f"Bearer {PERPLEXITY_API_KEY}"},
            )
            if r.status_code == 200:
                data = r.json()
                text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                # Simple URL extraction
                urls = re.findall(r"https?://[^\s)]+", text)
                return [{"title": u, "url": u, "content": ""} for u in urls[:max_results]]
    except Exception:
        pass
    return []

def _eu_host_label(url: str) -> Tuple[str, List[str]]:
    # DNS → IP → Country (best effort). Keine harten Fehler bei Timeouts.
    try:
        import dns.resolver
        from ipwhois import IPWhois
        host = re.sub(r"^https?://", "", url).split("/")[0]
        answers = dns.resolver.resolve(host, "A")
        countries = set()
        ips = []
        for rdata in answers:
            ip = rdata.to_text()
            ips.append(ip)
            try:
                info = IPWhois(ip).lookup_rdap(depth=1)
                cc = (info.get("network") or {}).get("country", "") or (info.get("asn_country_code") or "")
                if cc:
                    countries.add(cc.upper())
            except Exception:
                pass
        eu = any(c in EU_ISO for c in countries)
        return ("EU‑Host" if eu else "Non‑EU", ips)
    except Exception:
        return ("Unknown", [])

def _card(title: str, url: str, snippet: str, extra: str = "") -> str:
    title_safe = _clean(title) or url
    snippet = _clean(snippet)
    badge = f"<span class='hdr-badge'>{extra}</span>" if extra else ""
    return f"<div class='card'><h3 style='margin:.2rem 0'><a href='{url}' target='_blank' rel='noopener noreferrer'>{title_safe}</a></h3><p>{snippet}</p>{badge}</div>"

def _cards_grid(items: List[str]) -> str:
    return "<div class='grid'>" + "".join(items) + "</div>"

def build_live_sections(ctx: Dict[str, Any]) -> Dict[str, Any]:
    # Cache‑Key basiert auf den Queries
    queries = build_queries(ctx)
    cache_key = _hash_key("::".join(queries))
    cached = cache_get(cache_key)
    if cached:
        return cached

    news_cards, tool_cards, fund_cards, reg_cards, case_cards = [], [], [], [], []

    # NEWS / TOOLS / FUNDING / REGULATORY / CASES
    for q in queries[:3]:
        for res in tavily_search(q, days=60, max_results=4):
            label, _ips = _eu_host_label(res.get("url", ""))
            news_cards.append(_card(res.get("title", ""), res.get("url", ""), res.get("content", "")[:280]))
            tool_cards.append(_card(res.get("title", ""), res.get("url", ""), res.get("content", "")[:220], extra=label))
    for q in ["EU AI Act guidelines 2025 site:digital-strategy.ec.europa.eu", "AI regulation Germany 2025"]:
        for res in tavily_search(q, days=120, max_results=3):
            reg_cards.append(_card(res.get("title", ""), res.get("url", ""), res.get("content", "")[:260]))
    for q in ["Förderprogramm KI Deutschland 2025 site:foerderdatenbank.de", "Digital Jetzt 2025 site:bmwk.de"]:
        for res in tavily_search(q, days=365, max_results=5):
            fund_cards.append(_card(res.get("title", ""), res.get("url", ""), res.get("content", "")[:220]))
    for q in ["AI case study 2025 consulting", "AI best practice Mittelstand 2025"]:
        for res in tavily_search(q, days=365, max_results=4):
            case_cards.append(_card(res.get("title", ""), res.get("url", ""), res.get("content", "")[:220]))

    live = {
        "news_html": _cards_grid(news_cards[:8]) if news_cards else "<p>Keine aktuellen News gefunden.</p>",
        "tools_html": _cards_grid(tool_cards[:8]) if tool_cards else "<p>Keine passenden Tools gefunden.</p>",
        "funding_html": ("<ul>" + "".join(
            [f"<li><a href='{q}' target='_blank' rel='noopener noreferrer'>{q}</a></li>" for q in queries[:3]]
        ) + "</ul>") if not fund_cards else _cards_grid(fund_cards[:8]),
        "regulatory_html": _cards_grid(reg_cards[:8]) if reg_cards else "<p>Keine neuen Regulierungs‑Hinweise.</p>",
        "case_studies_html": _cards_grid(case_cards[:8]) if case_cards else "<p>Keine Cases gefunden.</p>",
        "stand": _today(),
    }
    cache_set(cache_key, live)
    return live

def _today() -> str:
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d")
