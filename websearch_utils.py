# websearch_utils.py
# -*- coding: utf-8 -*-
"""
Web-/API-Suche für Live-Updates:
- EU Funding & Tenders (FTS)
- CORDIS (EU-Forschung)
- OpenAIRE (Publikationen/Projekte)
- Tavily (Fallback für News/Tools), optional SerpAPI
Alle Ergebnisse werden auf ein gemeinsames Schema normalisiert.

ENV (siehe Railway):
    TAVILY_API_KEY, SERPAPI_KEY (optional)
    SEARCH_PROVIDER (tavily|serpapi|mixed), SEARCH_DAYS, SEARCH_DAYS_TOOLS, SEARCH_DAYS_FUNDING
    SEARCH_MAX_RESULTS, SEARCH_INCLUDE_DOMAINS, SEARCH_EXCLUDE_DOMAINS
    LIVE_NEWS_MIN_SCORE, TAVILY_CACHE_TTL
    LOG_LEVEL
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("websearch")

ISO_FMT = "%Y-%m-%d"

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "make-ki-backend/1.0 (+https://ki-sicherheit.jetzt)"

# ---- Normalisiertes Schema ---------------------------------------------------


@dataclass
class LiveItem:
    kind: str                 # 'news' | 'tool' | 'funding' | 'publication'
    title: str
    url: str
    summary: str = ""
    source: str = ""
    published_at: Optional[str] = None     # ISO date
    deadline: Optional[str] = None         # ISO date (funding)
    region: Optional[str] = None           # e.g. 'DE-BY'
    score: Optional[float] = None
    extra: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # filter Nones for compactness
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}


# ---- Utilities ---------------------------------------------------------------

def _clamp_days(env_name: str, default_days: int, minimum: int = 1, maximum: int = 365) -> int:
    val = os.getenv(env_name)
    try:
        if val is None:
            return default_days
        n = int(val)
        return max(minimum, min(maximum, n))
    except Exception:
        return default_days


def _since_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(DEFAULT_TIMEOUT),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def _get_domains_list(env_name: str) -> List[str]:
    v = os.getenv(env_name, "").strip()
    if not v:
        return []
    return [s.strip() for s in v.split(",") if s.strip()]


def _apply_domain_filters(items: List[LiveItem]) -> List[LiveItem]:
    include_domains = _get_domains_list("SEARCH_INCLUDE_DOMAINS")
    exclude_domains = _get_domains_list("SEARCH_EXCLUDE_DOMAINS")

    def domain(url: str) -> str:
        m = re.search(r"https?://([^/]+)/?", url)
        return m.group(1).lower() if m else ""

    filtered = []
    for it in items:
        dom = domain(it.url)
        if include_domains and all(not dom.endswith(d.lower()) for d in include_domains):
            continue
        if exclude_domains and any(dom.endswith(d.lower()) for d in exclude_domains):
            continue
        filtered.append(it)
    return filtered


# ---- EU Funding & Tenders (FTS) ---------------------------------------------
# Public search endpoint (no auth) documented here:
# https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities
# We call the public API used by the portal search (JSON) if available.

def search_eu_funding(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
    region_hint: Optional[str] = None,
) -> List[LiveItem]:
    days = days or _clamp_days("SEARCH_DAYS_FUNDING", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))

    since = _since_iso(days)
    items: List[LiveItem] = []
    url = (
        "https://funding-tenders-api.ec.europa.eu/api/opportunities/v2/search?"
        "size={size}&sort=publishedDate,desc&searchText={q}"
    ).format(size=max_results, q=httpx.QueryParams({"": query}).to_str()[1:])
    try:
        with _http_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("EU FTS search failed: %s", exc)
        return items

    for rec in data.get("data", []):
        pub = (rec.get("publishedDate") or "")[:10]
        if pub and pub < since:
            continue
        deadline = None
        for dl in rec.get("deadlines", []) or []:
            # choose nearest closing date
            d = (dl.get("date") or "")[:10]
            if re.match(r"\d{4}-\d{2}-\d{2}", d):
                if not deadline or d < deadline:
                    deadline = d
        items.append(
            LiveItem(
                kind="funding",
                title=rec.get("title", "").strip(),
                url="https://ec.europa.eu/info/funding-tenders/opportunities/portal/"
                    f"screen/opportunities/topic-details/{rec.get('identifier')}",
                summary=(rec.get("summary") or rec.get("objective") or "").strip(),
                source="EU Funding & Tenders",
                published_at=pub or None,
                deadline=deadline,
                region=region_hint,
                extra={"identifier": rec.get("identifier"), "programme": rec.get("programme")},
            )
        )
    return _apply_domain_filters(items)


# ---- CORDIS (EU research results/projects) ----------------------------------

def search_cordis(query: str, days: Optional[int] = None, max_results: Optional[int] = None) -> List[LiveItem]:
    days = days or _clamp_days("SEARCH_DAYS", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))
    since = _since_iso(days)
    # Open endpoint: https://cordis.europa.eu/search
    url = "https://cordis.europa.eu/api/search"
    params = {
        "q": query,
        "num": max_results,
        "sort": "date:desc",
        "format": "json",
    }
    items: List[LiveItem] = []
    try:
        with _http_client() as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("CORDIS search failed: %s", exc)
        return items

    for rec in (data.get("results") or []):
        pub = (rec.get("date") or "").split("T")[0]
        if pub and pub < since:
            continue
        items.append(
            LiveItem(
                kind="publication",
                title=(rec.get("title") or "").strip(),
                url=(rec.get("url") or "").strip(),
                summary=(rec.get("objective") or rec.get("teaser") or "").strip(),
                source="CORDIS",
                published_at=pub or None,
                extra={"programme": rec.get("programme"), "topic": rec.get("topic")},
            )
        )
    return _apply_domain_filters(items)


# ---- OpenAIRE (publications/projects) ---------------------------------------

def search_openaire(query: str, days: Optional[int] = None, max_results: Optional[int] = None) -> List[LiveItem]:
    days = days or _clamp_days("SEARCH_DAYS", 60)
    since = _since_iso(days)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))

    # OpenAIRE REST (public): publications
    base = "https://api.openaire.eu/search/publications"
    params = {"title": query, "size": max_results, "format": "json"}
    items: List[LiveItem] = []
    try:
        with _http_client() as client:
            resp = client.get(base, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("OpenAIRE search failed: %s", exc)
        return items

    def _get(o: Dict[str, Any], *keys: str) -> str:
        cur = o
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return ""
            cur = cur[k]
        return str(cur)

    for rec in (data.get("response", {}).get("results", {}).get("result", []) or []):
        md = rec.get("metadata", {})
        title = _get(md, "title", "value") or _get(md, "title")
        url = _get(md, "url") or _get(md, "bestaccesseurl", "value")
        date = (_get(md, "dateofacceptance", "value") or _get(md, "date") or "")[:10]
        if date and date < since:
            continue
        abstr = _get(md, "description", "value") or _get(md, "description")
        items.append(
            LiveItem(
                kind="publication",
                title=(title or "").strip(),
                url=(url or "").strip(),
                summary=(abstr or "").strip(),
                source="OpenAIRE",
                published_at=date or None,
            )
        )
    return _apply_domain_filters(items)


# ---- Tavily (News/Tools fallback) -------------------------------------------

def search_tavily(query: str, days: Optional[int] = None, max_results: Optional[int] = None) -> List[LiveItem]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []

    days = days or _clamp_days("SEARCH_DAYS", 30)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))
    since = _since_iso(days)

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.getenv("SEARCH_DEPTH", "advanced"),
        "include_domains": _get_domains_list("SEARCH_INCLUDE_DOMAINS"),
        "exclude_domains": _get_domains_list("SEARCH_EXCLUDE_DOMAINS"),
        "max_results": max_results,
        "topic": os.getenv("SEARCH_TOPIC", None),
    }
    try:
        with _http_client() as client:
            resp = client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return []

    items: List[LiveItem] = []
    for r in data.get("results", []):
        pub = (r.get("published_time") or "")[:10]
        if pub and pub < since:
            continue
        items.append(
            LiveItem(
                kind="news",
                title=r.get("title", ""),
                url=r.get("url", ""),
                summary=r.get("content", ""),
                source=r.get("source", "tavily"),
                published_at=pub or None,
                score=r.get("score"),
            )
        )
    return _apply_domain_filters(items)


# ---- Orchestrierung: Funding / Tools / News ---------------------------------

def query_live_items(
    *,
    industry: str,
    size: str,
    main_service: str,
    region: Optional[str] = None,
    days_news: Optional[int] = None,
    days_tools: Optional[int] = None,
    days_funding: Optional[int] = None,
    max_results: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Liefert normalisierte Items dicts: {news:[], tools:[], funding:[], publications:[]}
    Query-Strategie: Kombination von Branche + Leistung + Größe.
    """
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))
    days_news = days_news or _clamp_days("SEARCH_DAYS", 30)
    days_tools = days_tools or _clamp_days("SEARCH_DAYS_TOOLS", 60)
    days_funding = days_funding or _clamp_days("SEARCH_DAYS_FUNDING", 60)

    q_base = f"{industry} {main_service}".strip()
    q_tools = f"{q_base} tools software {size}".strip()
    q_news = f"{q_base} KMU {region or ''}".strip()
    q_funding = f"AI {industry} {region or ''} SME funding grant".strip()

    logger.info("live-query: news='%s' tools='%s' funding='%s'", q_news, q_tools, q_funding)

    news = search_tavily(q_news, days=days_news, max_results=max_results)

    funding = search_eu_funding(q_funding, days=days_funding, max_results=max_results, region_hint=region)
    pubs = search_cordis(q_base, days=days_news, max_results=max_results // 2) + \
           search_openaire(q_base, days=days_news, max_results=max_results // 2)

    # Tools via Tavily (produktreleases); optional SerpAPI könnte hier ergänzt werden.
    tools = search_tavily(q_tools, days=days_tools, max_results=max_results)

    min_score = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0.0"))
    news = [it for it in news if (it.score or 0.0) >= min_score]

    result = {
        "news": [it.to_dict() for it in news],
        "funding": [it.to_dict() for it in funding],
        "publications": [it.to_dict() for it in pubs],
        "tools": [it.to_dict() for it in tools],
    }
    return result
