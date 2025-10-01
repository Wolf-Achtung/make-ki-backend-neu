# websearch_utils.py
# -*- coding: utf-8 -*-
"""
Unified web and API search utilities for MAKE‑KI.

This module exposes a common interface for searching various sources of
information (EU funding, EU research projects, publications and
general news/tools via Tavily).  All results are normalised into a
`LiveItem` dataclass.  The functions have been written with resilience
in mind: network errors are caught and logged, missing environment
variables lead to graceful fallbacks, and optional filters are applied
to restrict results to trusted domains when desired.

Key functions include:

* ``search_eu_funding`` – fetch calls from the EU Funding & Tenders API
* ``search_cordis`` – search the CORDIS projects endpoint
* ``search_openaire`` – query OpenAIRE for publications
* ``search_tavily`` – wrapper around the Tavily API for news/tools
* ``query_live_items`` – orchestrate the above searches based on a
  company briefing (industry, size, service and region)
* ``tavily_search`` and ``days_to_tavily_range`` – compatibility
  helpers for older code

Environment variables such as ``TAVILY_API_KEY`` and
``SEARCH_INCLUDE_DOMAINS`` control the behaviour of the searches.

This file is intentionally standalone so that modules like
``gpt_analyze`` can import it without depending on the rest of the
project structure.  It closely mirrors the functionality of the
original ``websearch_utils.py`` found in the project directory, with
minor adaptations for PEP‑8 compliance and improved logging.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

__all__ = [
    "LiveItem",
    "search_eu_funding",
    "search_cordis",
    "search_openaire",
    "search_tavily",
    "query_live_items",
    "days_to_tavily_range",
    "tavily_search",
]

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

ISO_FMT = "%Y-%m-%d"

DEFAULT_TIMEOUT = 15.0
USER_AGENT = "make-ki-backend/1.0 (+https://ki-sicherheit.jetzt)"


@dataclass
class LiveItem:
    """Structure representing a normalised search result.

    :param kind: category of the result ("news", "tool", "funding", "publication")
    :param title: headline or name of the item
    :param url: canonical URL pointing to the item
    :param summary: short description or snippet
    :param source: source label (e.g. "EU Funding & Tenders")
    :param published_at: ISO date when the item was published
    :param deadline: ISO date of a funding deadline
    :param region: regional hint (e.g. "DE-BY")
    :param score: relevance score (optional)
    :param extra: additional metadata as a dictionary
    """

    kind: str
    title: str
    url: str
    summary: str = ""
    source: str = ""
    published_at: Optional[str] = None
    deadline: Optional[str] = None
    region: Optional[str] = None
    score: Optional[float] = None
    extra: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the dataclass to a dictionary, omitting empty fields."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "", [], {}, [])}


def _clamp_days(env_name: str, default_days: int, minimum: int = 1, maximum: int = 365) -> int:
    """Clamp a day count from an environment variable into a sane range."""
    val = os.getenv(env_name)
    try:
        if val is None:
            return default_days
        n = int(val)
        return max(minimum, min(maximum, n))
    except Exception:
        return default_days


def _since_iso(days: int) -> str:
    """Return an ISO date string ``days`` ago from now (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _http_client() -> httpx.Client:
    """Instantiate a HTTP client with default headers and timeout."""
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
    """Filter items based on include/exclude domain lists."""
    include_domains = _get_domains_list("SEARCH_INCLUDE_DOMAINS")
    exclude_domains = _get_domains_list("SEARCH_EXCLUDE_DOMAINS")

    def domain(url: str) -> str:
        m = re.search(r"https?://([^/]+)/?", url)
        return m.group(1).lower() if m else ""

    filtered: List[LiveItem] = []
    for it in items:
        dom = domain(it.url)
        if include_domains and all(not dom.endswith(d.lower()) for d in include_domains):
            continue
        if exclude_domains and any(dom.endswith(d.lower()) for d in exclude_domains):
            continue
        filtered.append(it)
    return filtered


def search_eu_funding(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
    region_hint: Optional[str] = None,
) -> List[LiveItem]:
    """Query the EU Funding & Tenders API for calls matching ``query``.

    :param query: free text search terms
    :param days: lookback period in days (environment default if None)
    :param max_results: maximum number of results to return
    :param region_hint: optional region hint (e.g. 'DE-BY') added to each item
    :return: list of ``LiveItem`` instances
    """
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


def search_cordis(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
) -> List[LiveItem]:
    """Search CORDIS (EU research results/projects) for ``query``."""
    days = days or _clamp_days("SEARCH_DAYS", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))
    since = _since_iso(days)
    url = "https://cordis.europa.eu/api/search"
    params: Dict[str, Any] = {
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

    for rec in data.get("results") or []:
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


def search_openaire(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
) -> List[LiveItem]:
    """Query OpenAIRE for publications matching ``query``."""
    days = days or _clamp_days("SEARCH_DAYS", 60)
    since = _since_iso(days)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))

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
        cur: Any = o
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


def search_tavily(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
) -> List[LiveItem]:
    """Call the Tavily API for news or tools matching ``query``.

    Tavily requires ``TAVILY_API_KEY`` to be set; if not, an empty list
    is returned.  Domain filtering and result limiting are applied based
    on the environment variables ``SEARCH_INCLUDE_DOMAINS`` and
    ``SEARCH_MAX_RESULTS``.

    :param query: free text search term
    :param days: recency in days
    :param max_results: maximum number of items to return
    :return: list of ``LiveItem`` instances
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.info("No TAVILY_API_KEY; skipping Tavily search")
        return []

    days = days or _clamp_days("SEARCH_DAYS", 30)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "10"))
    since = _since_iso(days)

    payload: Dict[str, Any] = {
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
    """Orchestrate multiple searches based on the company context.

    :param industry: industry name (Branche)
    :param size: company size (e.g. KMU)
    :param main_service: main service field (Hauptleistung)
    :param region: optional region code (e.g. 'DE-BE') for funding
    :param days_news: recency window for news
    :param days_tools: recency window for tools
    :param days_funding: recency window for funding calls
    :param max_results: maximum items per category
    :return: mapping from category to list of dictionaries (for JSON serialization)
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

    news_items = search_tavily(q_news, days=days_news, max_results=max_results)
    funding_items = search_eu_funding(q_funding, days=days_funding, max_results=max_results, region_hint=region)
    pub_items = search_cordis(q_base, days=days_news, max_results=max_results // 2) + search_openaire(q_base, days=days_news, max_results=max_results // 2)
    tool_items = search_tavily(q_tools, days=days_tools, max_results=max_results)

    min_score = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0.0"))
    news_items = [it for it in news_items if (it.score or 0.0) >= min_score]

    return {
        "news": [it.to_dict() for it in news_items],
        "funding": [it.to_dict() for it in funding_items],
        "publications": [it.to_dict() for it in pub_items],
        "tools": [it.to_dict() for it in tool_items],
    }


# -------------------------------------------------------------------------
# Backwards compatibility helpers
# -------------------------------------------------------------------------

def days_to_tavily_range(days: int) -> str:
    """Map a recency window in days to Tavily API tokens.

    Tavily recognises the strings ``day``, ``week``, ``month`` and
    ``year`` as shorthand for different time horizons.  This helper
    facilitates legacy code that expects this function in
    ``websearch_utils``.
    """
    if days <= 7:
        return "day"
    if days <= 30:
        return "week"
    if days <= 90:
        return "month"
    return "year"


def tavily_search(
    query: str,
    days: int = 30,
    include_domains: Optional[List[str]] = None,
    max_results: int = 10,
) -> List[Dict[str, str]]:
    """Compatibility wrapper returning simple dictionaries.

    This helper calls :func:`search_tavily` and coerces the
    ``LiveItem`` instances into plain dictionaries.  It exists for
    backward compatibility with older modules that import
    ``tavily_search`` directly.

    :param query: search term
    :param days: recency in days
    :param include_domains: optional list of domain suffixes to whitelist
    :param max_results: maximum number of dictionaries to return
    :return: list of dictionaries with keys ``title``, ``url``, ``published`` and ``snippet``
    """
    items: List[Dict[str, str]] = []
    try:
        raw_items = search_tavily(query, days=days, max_results=max_results)
    except Exception as exc:
        logger.warning("tavily_search wrapper failed: %s", exc)
        return items
    for it in raw_items:
        # search_tavily returns LiveItem instances
        if hasattr(it, "title"):
            title = getattr(it, "title", "")
            url = getattr(it, "url", "")
            published = getattr(it, "published_at", None) or ""
            snippet = getattr(it, "summary", "")
        elif isinstance(it, dict):
            title = it.get("title") or it.get("name") or ""
            url = it.get("url") or it.get("link") or ""
            published = it.get("published") or it.get("date") or it.get("published_at") or ""
            snippet = it.get("snippet") or it.get("summary") or it.get("description") or ""
        else:
            continue
        items.append(
            {
                "title": str(title).strip(),
                "url": str(url).strip(),
                "published": str(published).strip(),
                "snippet": str(snippet).strip(),
            }
        )
    # Apply optional include_domains filter
    if include_domains:
        filtered: List[Dict[str, str]] = []
        for itm in items:
            url = itm.get("url", "").lower()
            domain_match = False
            for d in include_domains:
                d = d.lower().strip()
                if d and (url.endswith(d) or url.endswith("." + d)):
                    domain_match = True
                    break
            if domain_match:
                filtered.append(itm)
        items = filtered
    return items[:max_results]