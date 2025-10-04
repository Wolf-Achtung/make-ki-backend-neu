# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live-Suche + CSV-Fallbacks (Gold-Standard+)

Neu:
- Tool-Scoring: EU-Host (40%) + DSGVO-Signal (30%) + Domain-Autorität (30%)
- Regionale Förderung: Filter per 'region_code' (Bundesland)
- Quellenzähler je Kachel
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
import tldextract
from typing import Any, Dict, List, Tuple

import httpx

from live_cache import cache_get, cache_set

EU_ISO = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT",
    "LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE","IS","NO","LI"
}

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.abspath(os.getenv("APP_BASE", os.getcwd())), "data"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")


# --------------------------- Utilities ---------------------------------------

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _hash_key(x: str) -> str:
    return hashlib.sha256(x.encode("utf-8")).hexdigest()


def _read_csv_rows(path: str) -> List[Dict[str, str]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [dict(r) for r in reader]
    except Exception:
        return []


def _eu_host_label(url: str) -> Tuple[str, List[str], float]:
    """
    DNS -> IP -> Country; best effort. Liefert Label, IPs, Score(0..1).
    """
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
        return ("EU‑Host" if eu else "Non‑EU", ips, 1.0 if eu else 0.0)
    except Exception:
        return ("Unknown", [], 0.5)


def _domain_authority_heuristic(url: str) -> float:
    """
    Heuristik 0..1: TLD-Wert + Domänenlänge.
    - .gov/.eu/.de/.org hohes Gewicht
    - kurze Second-Level-Domain besser (<=6)
    """
    try:
        ext = tldextract.extract(url)
        sld = ext.domain or ""
        tld = (ext.suffix or "").lower()
    except Exception:
        return 0.5
    tld_w = {
        "gov": 1.0, "eu": 0.95, "de": 0.9, "org": 0.85, "com": 0.8, "io": 0.75, "net": 0.75
    }
    # composite TLDs: ...europa.eu -> "eu"
    base_tld = tld.split(".")[-1] if tld else ""
    w_tld = tld_w.get(base_tld, 0.7)
    w_len = 1.0 if 1 <= len(sld) <= 6 else (0.85 if len(sld) <= 10 else 0.7)
    return max(0.0, min(1.0, 0.6 * w_tld + 0.4 * w_len))


def _gdpr_signal_score(text: str) -> float:
    """
    0..1 je nach Vorkommen von DSGVO/GDPR/AVV/DPA etc.
    """
    t = (text or "").lower()
    kws = ["dsgvo", "gdpr", "auftragsverarbeitung", "avv", "data processing agreement", "dpa", "eu-host", "eu hosting"]
    hits = sum(1 for k in kws if k in t)
    if hits >= 3:
        return 1.0
    if hits == 2:
        return 0.75
    if hits == 1:
        return 0.5
    return 0.2


def _score_tool(url: str, snippet: str) -> Tuple[int, str]:
    """
    Kombinierter Score 0..100:
      40% EU-Host, 30% DSGVO-Signal, 30% Domain-Autorität
    """
    label, _ips, eu_s = _eu_host_label(url)
    gdpr_s = _gdpr_signal_score(snippet)
    da_s = _domain_authority_heuristic(url)
    score = int(round(100 * (0.40 * eu_s + 0.30 * gdpr_s + 0.30 * da_s)))
    return score, label


def _card(title: str, url: str, snippet: str, extra: str = "", score: int | None = None) -> str:
    title_safe = _clean(title) or url
    snippet = _clean(snippet)
    badges = []
    if extra:
        badges.append(f"<span class='hdr-badge'>{extra}</span>")
    if score is not None:
        badges.append(f"<span class='hdr-badge'>Score {score}/100</span>")
    return (
        f"<div class='card'>"
        f"<h3 style='margin:.2rem 0'><a href='{url}' target='_blank' rel='noopener noreferrer'>{title_safe}</a></h3>"
        f"<p>{snippet}</p>{''.join(badges)}</div>"
    )


def _cards_grid(items: List[str]) -> str:
    return "<div class='grid'>" + "".join(items) + "</div>"


# ------------------------------ Live-APIs ------------------------------------

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
                urls = re.findall(r"https?://[^\s)]+", text)
                return [{"title": u, "url": u, "content": ""} for u in urls[:max_results]]
    except Exception:
        pass
    return []


# ------------------------------ CSV-Fallbacks --------------------------------

def _tools_from_csv(ctx: Dict[str, Any], limit: int = 8) -> List[str]:
    path = os.path.join(DATA_DIR, "tools.csv")
    rows = _read_csv_rows(path)
    if not rows:
        return []
    bran = (_clean(ctx.get("branche") or "")).lower()
    size = (_clean(ctx.get("size") or "")).lower()

    items: List[str] = []
    for r in rows:
        name = r.get("name") or r.get("Tool-Name") or ""
        url = r.get("homepage_url") or r.get("Website") or ""
        industry = (r.get("industry") or r.get("Branche") or "").lower()
        company_size = (r.get("company_size") or r.get("Unternehmensgröße") or "*").lower()
        one_liner = r.get("one_liner") or r.get("Kurze Beschreibung") or ""
        if not name or not url:
            continue
        ok_ind = (industry == "*") or (bran and industry and bran in industry)
        ok_size = (company_size == "*") or (size and company_size and size in company_size)
        if ok_ind and ok_size:
            sc, lbl = _score_tool(url, f"{name} {one_liner}")
            items.append(_card(name, url, one_liner, extra=lbl, score=sc))
        if len(items) >= limit:
            break
    return items


def _funding_from_csv(ctx: Dict[str, Any], limit: int = 8) -> List[str]:
    region = (_clean(ctx.get("region_code") or "")).lower()
    items: List[str] = []

    def _add(title: str, url: str, snippet: str):
        items.append(_card(title, url, snippet, extra="Data"))

    # 1) priorisiere foerderprogramme.csv
    path1 = os.path.join(DATA_DIR, "foerderprogramme.csv")
    rows = _read_csv_rows(path1)
    if rows:
        for r in rows:
            name = r.get("Programmname") or ""
            status = (r.get("Status") or "").lower()  # offen/rolling/geplant/geschlossen
            deadline = r.get("Deadline") or ""
            descr = r.get("Kurzbeschreibung") or ""
            url = r.get("Website") or ""
            reg = (r.get("Region_Code") or "").lower()  # z.B. de, be, by, ...
            if not name or not url:
                continue
            if status in {"geschlossen", "closed"}:
                continue
            if reg and region and reg not in {"de", "*"} and reg != region:
                continue
            _add(f"{name} ({deadline or 'rolling'})", url, descr)
            if len(items) >= limit:
                return items

    # 2) fallback foerdermittel.csv
    path2 = os.path.join(DATA_DIR, "foerdermittel.csv")
    rows2 = _read_csv_rows(path2)
    for r in rows2:
        name = r.get("name") or ""
        ziel = r.get("zielgruppe") or ""
        link = r.get("link") or ""
        einsatz = r.get("einsatz") or ""
        reg = (r.get("region_code") or r.get("bundesland") or "").lower()
        if not name or not link:
            continue
        if reg and region and reg not in {"de", "*"} and reg != region:
            continue
        _add(f"{name} – {ziel}", link, einsatz)
        if len(items) >= limit:
            break

    return items


# ------------------------------ Orchestrierung -------------------------------

def build_live_sections(ctx: Dict[str, Any]) -> Dict[str, Any]:
    queries = build_queries(ctx)
    cache_key = _hash_key("::".join(queries) + f"::{ctx.get('region_code','')}")
    cached = cache_get(cache_key)
    if cached:
        return cached

    news_cards: List[str] = []
    tool_cards: List[str] = []
    fund_cards: List[str] = []
    reg_cards: List[str] = []
    case_cards: List[str] = []

    # NEWS / TOOLS (Tavily)
    for q in queries[:3]:
        for res in tavily_search(q, days=60, max_results=4):
            title = res.get("title", "")
            url = res.get("url", "")
            content = res.get("content", "")
            news_cards.append(_card(title, url, content[:280]))
            sc, lbl = _score_tool(url, content)
            tool_cards.append(_card(title, url, content[:220], extra=lbl, score=sc))

    # REGULATORY (EU AI Act)
    for q in ["EU AI Act guidelines 2025 site:digital-strategy.ec.europa.eu", "AI regulation Germany 2025"]:
        for res in tavily_search(q, days=120, max_results=3):
            reg_cards.append(_card(res.get("title", ""), res.get("url", ""), res.get("content", "")[:260]))

    # CASES
    for q in ["AI case study 2025 consulting", "AI best practice Mittelstand 2025"]:
        for res in tavily_search(q, days=365, max_results=4):
            case_cards.append(_card(res.get("title", ""), res.get("url", ""), res.get("content", "")[:220]))

    # Fallbacks (CSV)
    if len(tool_cards) < 6:
        tool_cards.extend(_tools_from_csv(ctx, limit=8 - len(tool_cards)))
    if len(fund_cards) < 6:
        fund_cards.extend(_funding_from_csv(ctx, limit=8 - len(fund_cards)))

    # Mindestinhalt
    if not news_cards:
        news_cards.append("<p>Keine aktuellen News gefunden.</p>")
    if not tool_cards:
        tool_cards.append("<p>Keine passenden Tools gefunden.</p>")
    if not fund_cards:
        fund_cards.append("<p>Keine Förderprogramme gefunden.</p>")
    if not reg_cards:
        reg_cards.append("<p>Keine neuen Regulierungs‑Hinweise.</p>")
    if not case_cards:
        case_cards.append("<p>Keine Cases gefunden.</p>")

    live = {
        "news_html": _cards_grid(news_cards[:8]),
        "tools_html": _cards_grid(tool_cards[:8]),
        "funding_html": _cards_grid(fund_cards[:8]),
        "regulatory_html": _cards_grid(reg_cards[:8]),
        "case_studies_html": _cards_grid(case_cards[:8]),
        "stand": _today(),
        "counts": {
            "news": len(news_cards),
            "tools": len(tool_cards),
            "funding": len(fund_cards),
            "regulatory": len(reg_cards),
            "cases": len(case_cards),
        }
    }
    cache_set(cache_key, live)
    return live


def _today() -> str:
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d")
