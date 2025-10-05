# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live-Layer (News, Tools, Förderungen) mit Tavily + Perplexity Merge
- Primär Tavily (schnell, solide Treffer)
- Sekundär Perplexity (ergänzende Quellen)
- De-Dup, Re-Rank, Fallback von 7 auf 30 Tage
- Berlin-Badge für Förderungen (berlin.de, ibb.de, investitionsbank-berlin.de)
- Robuste Timeouts/Fehlerbehandlung, keine harten Abhängigkeiten

Ausgabeformat (Dictionary):
{
  "window_days": 7|30,
  "news":    [{"title","url","source","date","snippet","score"}],
  "tools":   [{"title","url","source","date","snippet","score","eu_hint": bool}],
  "funding": [{"title","url","source","date","snippet","score","berlin_badge": bool}],
}
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import httpx

log = logging.getLogger("websearch_utils")
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# --- Konfiguration per ENV ---
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "").strip()

LIVE_TIMEOUT_S = float(os.getenv("LIVE_TIMEOUT_S", "8.0"))
LIVE_PRIMARY_DAYS = int(os.getenv("LIVE_NEWS_DAYS", "7"))
LIVE_FALLBACK_MAX_DAYS = int(os.getenv("LIVE_FALLBACK_MAX_DAYS", "30"))  # du wolltest 30 als Fallback
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "5"))

# Optional: harte Domaingewichte für Re-Rank
TRUST_WEIGHT = {
    # Förderungen/Bund/Land
    "foerderdatenbank.de": 1.00,
    "bafa.de": 0.95,
    "bund.de": 0.95,
    "bmwk.de": 0.90,
    "berlin.de": 0.95,
    "ibb.de": 0.95,
    # News/Tech
    "heise.de": 0.85,
    "golem.de": 0.80,
    "t3n.de": 0.75,
    "handelsblatt.com": 0.80,
    "wired.com": 0.70,
    "theverge.com": 0.65,
    # Tools
    "nextcloud.com": 0.85,
    "matomo.org": 0.85,
    "jitsi.org": 0.75,
    "odoo.com": 0.75,
    "huggingface.co": 0.75,
    "github.com": 0.70,
    "producthunt.com": 0.65,
}

EU_TLDS = (".de", ".eu", ".fr", ".nl", ".it", ".es", ".se", ".fi", ".dk", ".pl", ".at", ".be", ".ie", ".pt", ".gr", ".cz", ".sk", ".hu", ".lt", ".lv", ".ee", ".ro", ".bg", ".hr", ".si", ".lu", ".mt", ".cy")


# -------------------------- HTTP Hilfsfunktionen -----------------------------

def _client() -> httpx.Client:
    return httpx.Client(timeout=LIVE_TIMEOUT_S, follow_redirects=True)


def _trim_url(u: str) -> str:
    """
    Entfernt UTM-Parameter & Tracking, normalisiert Pfad.
    """
    try:
        p = urlparse(u)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        clean = p._replace(query=urlencode(q), fragment="")
        # Doppelte Slashes, Trailing slash normalisieren
        path = re.sub(r"/{2,}", "/", clean.path or "/")
        clean = clean._replace(path=path.rstrip("/") or "/")
        return urlunparse(clean)
    except Exception:
        return u


def _domain(u: str) -> str:
    try:
        return urlparse(u).netloc.lower()
    except Exception:
        return ""


def _today_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def _days_to_range(days: int) -> str:
    return "d7" if days <= 7 else "d30"


def _parse_date(s: Optional[str]) -> str:
    if not s:
        return _today_iso()
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        # try common formats
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                return dt.datetime.strptime(s[:10], fmt).date().isoformat()
            except Exception:
                continue
    return _today_iso()


# -------------------------- Tavily / Perplexity ------------------------------

def _tavily_search(query: str, days: int, max_results: int = 6) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "time_range": _days_to_range(days),
        "max_results": max(1, min(10, max_results)),
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        with _client() as client:
            r = client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json() or {}
            out: List[Dict[str, Any]] = []
            for item in data.get("results", []) or []:
                out.append({
                    "title": (item.get("title") or "").strip() or (item.get("url") or ""),
                    "url": _trim_url(item.get("url") or ""),
                    "source": _domain(item.get("url") or ""),
                    "date": _parse_date(item.get("published_date")),
                    "snippet": (item.get("content") or "")[:300],
                    "engine": "tavily",
                })
            return out
    except Exception as e:
        log.warning("Tavily failed: %s", e)
        return []


def _perplexity_search(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    """
    Sehr robuster Parser für Perplexity: nutzt citations[], fällt sonst auf URL-Erkennung im Text zurück.
    """
    if not PERPLEXITY_API_KEY:
        return []
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": os.getenv("PPLX_MODEL", "sonar-small-online"),
        "temperature": 0.0,
        "return_images": False,
        "top_p": 0.9,
        "search_recency_filter": "month",
        "messages": [
            {"role": "system", "content": "Answer briefly. Provide citations. Focus on trustworthy, official sources in DE/EU if available."},
            {"role": "user", "content": f"Find 6 most relevant sources for: {query}. Return answer with citations."}
        ],
    }
    try:
        with _client() as client:
            r = client.post("https://api.perplexity.ai/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            data = r.json() or {}
    except Exception as e:
        log.warning("Perplexity failed: %s", e)
        return []

    # 1) preferred: citations field (list[str])
    cites = []
    try:
        cites = data["choices"][0]["message"].get("citations") or []
    except Exception:
        cites = []
    out: List[Dict[str, Any]] = []
    # 2) fallback: URL regex on content
    if not cites:
        content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "")
        cites = re.findall(r"https?://[^\s\]\)>\}]+", content)

    for url in cites[:max_results]:
        out.append({
            "title": "",  # unbekannt, wird später ggf. durch Tavily ergänzt
            "url": _trim_url(url),
            "source": _domain(url),
            "date": _today_iso(),
            "snippet": "",
            "engine": "perplexity",
        })
    return out


# -------------------------- Merge / Scoring ----------------------------------

def _is_berlin_funding(u: str) -> bool:
    d = _domain(u)
    return d.endswith("berlin.de") or d == "ibb.de" or "investitionsbank-berlin" in d


def _eu_hint(u: str) -> bool:
    d = _domain(u)
    return d.endswith(EU_TLDS)  # heuristisch


def _dedup(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        key = (_trim_url(it.get("url", "")), (it.get("title") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _recency_score(date_iso: str, window_days: int) -> float:
    try:
        d = dt.datetime.fromisoformat(date_iso).date()
    except Exception:
        d = dt.date.today()
    days = max(0, (dt.date.today() - d).days)
    # 1.0 (heute) .. 0.0 (>= window_days)
    return max(0.0, 1.0 - (days / float(max(1, window_days))))


def _trust_score(u: str) -> float:
    return TRUST_WEIGHT.get(_domain(u), 0.5)


def _query_boost(title: str, query: str) -> float:
    t = (title or "").lower()
    q = (query or "").lower()
    score = 0.0
    for tok in re.findall(r"[a-zäöüß]{4,}", q):
        if tok in t:
            score += 0.1
    return min(0.3, score)


def _rank(items: List[Dict[str, Any]], window_days: int, query: str) -> List[Dict[str, Any]]:
    for it in items:
        rs = _recency_score(it.get("date") or _today_iso(), window_days)
        ts = _trust_score(it.get("url", ""))
        qb = _query_boost(it.get("title", "") or it.get("source", ""), query)
        it["score"] = round(0.55 * ts + 0.35 * rs + 0.10 * qb, 4)
    items.sort(key=lambda x: (-x.get("score", 0.0), x.get("title", "")))
    return items


def _augment_titles_with_tavily(items: List[Dict[str, Any]], days: int) -> None:
    """
    Optional: wenn Perplexity-URLs ohne Titel kamen, versuche minimalen Tavily-Abgleich.
    """
    if not TAVILY_API_KEY:
        return
    missing = [it for it in items if not it.get("title")]
    if not missing:
        return
    # Sparsam: höchstens 3 Pings
    for it in missing[:3]:
        q = f"site:{_domain(it['url'])}"
        hits = _tavily_search(q, days=days, max_results=3)
        # Setze ersten halbwegs passenden Titel
        for h in hits:
            if _domain(h["url"]) == _domain(it["url"]):
                it["title"] = h["title"] or it["url"]
                it["snippet"] = it["snippet"] or h.get("snippet", "")
                break


# -------------------------- Öffentliche API ----------------------------------

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Kontext:
      - branche: "Beratung & Dienstleistungen" (oder Label)
      - size: "1" / "2-10" / "11-100+"
      - country: "DE"
      - region_code: z. B. "BE"
    """
    branche = (context.get("branche") or "").strip() or "Beratung & Dienstleistungen"
    region = (context.get("region_code") or "").strip().upper()
    country = (context.get("country") or "DE").strip().upper()

    # Queries (kurz & präzise)
    q_news = f'{branche} KI ("Künstliche Intelligenz" OR "Generative KI") site:de'
    q_tools = f'EU-geeignete KI Tools OR Open-Source KI {country} {branche}'
    # Berlin optional präzisieren
    q_funding = f'Förderprogramme KI Digitalisierung {country} {"Berlin " + region if region == "BE" else ""}'

    # --- Erst 7 Tage
    window = LIVE_PRIMARY_DAYS
    news = _tavily_search(q_news, days=window, max_results=8)
    tools = _tavily_search(q_tools, days=window, max_results=8)
    funding = _tavily_search(q_funding, days=window, max_results=8)

    # Perplexity ergänzen, wenn konfiguriert
    if len(news) < 5:
        news += _perplexity_search(q_news, max_results=6)
    if len(funding) < 3:
        funding += _perplexity_search(q_funding, max_results=6)
    if len(tools) < 3:
        tools += _perplexity_search(q_tools, max_results=6)

    # --- Fallback auf 30 Tage, falls zu wenig
    def too_thin(lst: List[Dict[str, Any]], min_count: int) -> bool:
        return len(lst) < min_count

    if window < LIVE_FALLBACK_MAX_DAYS and (
        too_thin(news, 2) or too_thin(funding, 2) or too_thin(tools, 2)
    ):
        window = LIVE_FALLBACK_MAX_DAYS
        news += _tavily_search(q_news, days=window, max_results=8)
        funding += _tavily_search(q_funding, days=window, max_results=8)
        tools += _tavily_search(q_tools, days=window, max_results=8)

    # Titel ggf. ergänzen
    _augment_titles_with_tavily(news, days=window)
    _augment_titles_with_tavily(funding, days=window)
    _augment_titles_with_tavily(tools, days=window)

    # De-Dup
    news = _dedup(news)
    tools = _dedup(tools)
    funding = _dedup(funding)

    # Ranking
    news = _rank(news, window_days=window, query=q_news)[:LIVE_MAX_ITEMS]
    tools = _rank(tools, window_days=window, query=q_tools)[:LIVE_MAX_ITEMS]
    funding = _rank(funding, window_days=window, query=q_funding)[:LIVE_MAX_ITEMS]

    # Attribute
    for t in tools:
        t["eu_hint"] = _eu_hint(t.get("url", ""))
    for f in funding:
        f["berlin_badge"] = _is_berlin_funding(f.get("url", ""))

    return {
        "window_days": window,
        "news": news,
        "tools": tools,
        "funding": funding,
    }
