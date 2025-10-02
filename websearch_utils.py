# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Unified web & API search utilities for MAKE‑KI (Gold‑Standard+).

- EU Funding: Funding & Tenders (API) + optional Fallback via Tavily
- Research: CORDIS + OpenAIRE
- News/Tools: Tavily
- Domain‑Filter (Whitelist/Blacklist), Throttle & TTL‑Cache
- Flexible query_live_items‑Signatur (branche/leistung/bundesland ODER industry/main_service/region)
- Abwärtskompatibel: tavily_search(), days_to_tavily_range()

ENV (Auszug):
  TAVILY_API_KEY
  SEARCH_INCLUDE_DOMAINS, SEARCH_EXCLUDE_DOMAINS
  SEARCH_DAYS_NEWS, SEARCH_DAYS_TOOLS, SEARCH_DAYS_FUNDING, SEARCH_MAX_RESULTS
  SEARCH_DEPTH, SEARCH_TOPIC
  EU_FUNDING_ENABLED=true|false
  EU_THROTTLE_RPM=24
  EU_CACHE_TTL=1200
  TAVILY_CACHE_TTL=900
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

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

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("websearch_utils")

ISO_FMT = "%Y-%m-%d"
DEFAULT_TIMEOUT = 20.0
USER_AGENT = "make-ki-backend/1.0 (+https://ki-sicherheit.jetzt)"

# -----------------------------------------------------------------------------
# Simple TTL cache & rate limiter
# -----------------------------------------------------------------------------
class _TTLCache:
    def __init__(self) -> None:
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str, ttl: int) -> Optional[Any]:
        if ttl <= 0:
            return None
        now = time.time()
        entry = self._store.get(key)
        if not entry:
            return None
        expires, value = entry
        if now <= expires:
            return value
        self._store.pop(key, None)
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        if ttl <= 0:
            return
        self._store[key] = (time.time() + ttl, value)


_CACHE = _TTLCache()


class _RateLimiter:
    def __init__(self, rpm: int) -> None:
        self.rpm = max(0, int(rpm))
        self.events: deque[float] = deque()

    def wait(self) -> None:
        if self.rpm <= 0:
            return
        window = 60.0
        now = time.monotonic()
        while self.events and now - self.events[0] > window:
            self.events.popleft()
        if len(self.events) >= self.rpm:
            sleep_for = window - (now - self.events[0]) + 0.01
            if sleep_for > 0:
                time.sleep(min(sleep_for, 2.0))  # kurze Backoffs
        self.events.append(time.monotonic())


def _cache_key(name: str, *args: Any, **kwargs: Any) -> str:
    try:
        return f"{name}:{json.dumps([args, kwargs], sort_keys=True, default=str)}"
    except Exception:
        return f"{name}:{repr(args)}:{repr(kwargs)}"


def _clamp_days(env_name: str, default_days: int, minimum: int = 1, maximum: int = 365) -> int:
    v = os.getenv(env_name)
    try:
        if v is None:
            return default_days
        n = int(v)
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
    return [s.strip().lower() for s in v.split(",") if s.strip()]


def _apply_domain_filters(items: List["LiveItem"]) -> List["LiveItem"]:
    include_domains = _get_domains_list("SEARCH_INCLUDE_DOMAINS")
    exclude_domains = _get_domains_list("SEARCH_EXCLUDE_DOMAINS")

    def dom(url: str) -> str:
        m = re.search(r"https?://([^/]+)/?", url)
        return m.group(1).lower() if m else ""

    out: List[LiveItem] = []
    for it in items:
        d = dom(it.url)
        if include_domains and all(not d.endswith(x) for x in include_domains):
            continue
        if exclude_domains and any(d.endswith(x) for x in exclude_domains):
            continue
        out.append(it)
    return out


@dataclass
class LiveItem:
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
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}


# -----------------------------------------------------------------------------
# EU Funding & Research
# -----------------------------------------------------------------------------
_EU_LIMITER = _RateLimiter(int(os.getenv("EU_THROTTLE_RPM", "24")))
_EU_TTL = int(os.getenv("EU_CACHE_TTL", "1200"))  # 20 min


def search_eu_funding(query: str, days: Optional[int] = None,
                      max_results: Optional[int] = None,
                      region_hint: Optional[str] = None) -> List[LiveItem]:
    """
    Funding & Tenders API. Benötigt keine Auth. Fällt bei Fehlern still auf [] zurück.
    """
    if os.getenv("EU_FUNDING_ENABLED", "true").lower() != "true":
        return []

    days = days or _clamp_days("SEARCH_DAYS_FUNDING", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    since = _since_iso(days)

    key = _cache_key("fts", query, days, max_results, region_hint)
    cached = _CACHE.get(key, _EU_TTL)
    if cached is not None:
        return cached

    _EU_LIMITER.wait()
    items: List[LiveItem] = []
    url = (
        "https://funding-tenders-api.ec.europa.eu/api/opportunities/v2/search?"
        f"size={max_results}&sort=publishedDate,desc&searchText={httpx.QueryParams({'': query}).to_str()[1:]}"
    )
    try:
        with _http_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        for rec in data.get("data", []):
            pub = (rec.get("publishedDate") or "")[:10]
            if pub and pub < since:
                continue
            deadline = None
            for dl in rec.get("deadlines") or []:
                d = (dl.get("date") or "")[:10]
                if re.match(r"\d{4}-\d{2}-\d{2}", d):
                    if not deadline or d < deadline:
                        deadline = d
            items.append(
                LiveItem(
                    kind="funding",
                    title=(rec.get("title") or "").strip(),
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
    except Exception as exc:
        logger.warning("EU FTS search failed: %s", exc)
        items = []

    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _EU_TTL)
    return items


def search_cordis(query: str, days: Optional[int] = None, max_results: Optional[int] = None) -> List[LiveItem]:
    days = days or _clamp_days("SEARCH_DAYS", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    since = _since_iso(days)

    key = _cache_key("cordis", query, days, max_results)
    cached = _CACHE.get(key, _EU_TTL)
    if cached is not None:
        return cached

    _EU_LIMITER.wait()
    items: List[LiveItem] = []
    url = "https://cordis.europa.eu/api/search"
    params = {"q": query, "num": max_results, "sort": "date:desc", "format": "json"}
    try:
        with _http_client() as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
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
    except Exception as exc:
        logger.warning("CORDIS search failed: %s", exc)
        items = []

    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _EU_TTL)
    return items


def search_openaire(query: str, days: Optional[int] = None, max_results: Optional[int] = None) -> List[LiveItem]:
    days = days or _clamp_days("SEARCH_DAYS", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    since = _since_iso(days)

    key = _cache_key("openaire", query, days, max_results)
    cached = _CACHE.get(key, _EU_TTL)
    if cached is not None:
        return cached

    _EU_LIMITER.wait()
    items: List[LiveItem] = []
    base = "https://api.openaire.eu/search/publications"
    params = {"title": query, "size": max_results, "format": "json"}
    try:
        with _http_client() as client:
            resp = client.get(base, params=params)
            resp.raise_for_status()
            data = resp.json()
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
    except Exception as exc:
        logger.warning("OpenAIRE search failed: %s", exc)
        items = []

    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _EU_TTL)
    return items

# -----------------------------------------------------------------------------
# Tavily
# -----------------------------------------------------------------------------
_TAV_TTL = int(os.getenv("TAVILY_CACHE_TTL", "900"))  # 15 min

def search_tavily(query: str, days: Optional[int] = None, max_results: Optional[int] = None) -> List[LiveItem]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.info("No TAVILY_API_KEY; skipping Tavily search")
        return []

    days = days or _clamp_days("SEARCH_DAYS", 30)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    since = _since_iso(days)

    key = _cache_key("tavily", query, days, max_results)
    cached = _CACHE.get(key, _TAV_TTL)
    if cached is not None:
        return cached

    payload: Dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.getenv("SEARCH_DEPTH", "advanced"),
        "include_domains": _get_domains_list("SEARCH_INCLUDE_DOMAINS"),
        "exclude_domains": _get_domains_list("SEARCH_EXCLUDE_DOMAINS"),
        "max_results": max_results,
        "topic": os.getenv("SEARCH_TOPIC", None),
    }
    items: List[LiveItem] = []
    try:
        with _http_client() as client:
            resp = client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
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
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        items = []

    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _TAV_TTL)
    return items

# -----------------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------------
def query_live_items(
    *,
    # flexible Benennung – unterstützt beide Varianten:
    branche: Optional[str] = None,
    industry: Optional[str] = None,
    size: Optional[str] = None,
    unternehmensgroesse: Optional[str] = None,
    leistung: Optional[str] = None,
    main_service: Optional[str] = None,
    bundesland: Optional[str] = None,
    region: Optional[str] = None,
    lang: Optional[str] = None,
    days_news: Optional[int] = None,
    days_tools: Optional[int] = None,
    days_funding: Optional[int] = None,
    max_results: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Liefert strukturierte Live‑Ergebnisse:
      { "news": [...], "tools": [...], "funding": [...], "publications": [...] }
    """
    # normalisieren
    industry = industry or branche or ""
    main_service = main_service or leistung or ""
    region = region or bundesland or None

    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    days_news = days_news or _clamp_days("SEARCH_DAYS_NEWS", 7)
    days_tools = days_tools or _clamp_days("SEARCH_DAYS_TOOLS", 30)
    days_funding = days_funding or _clamp_days("SEARCH_DAYS_FUNDING", 60)

    q_base = f"{industry} {main_service}".strip()
    q_tools = f"{q_base} tools software {size or unternehmensgroesse or ''}".strip()
    q_news = f"{q_base} KMU {region or ''}".strip()
    q_funding = f"AI {industry} {region or ''} SME funding grant".strip()

    logger.info("live-query: news='%s' tools='%s' funding='%s'", q_news, q_tools, q_funding)

    news_items = search_tavily(q_news, days=days_news, max_results=max_results)
    tool_items = search_tavily(q_tools, days=days_tools, max_results=max_results)

    # EU Quellen – F&T direkt + CORDIS/OpenAIRE als Kontext (Publikationen)
    funding_items = search_eu_funding(q_funding, days=days_funding, max_results=max_results, region_hint=region)
    pub_items = search_cordis(q_base, days=days_news, max_results=max_results // 2) + \
                search_openaire(q_base, days=days_news, max_results=max_results // 2)

    # Score‑Schwelle für News
    min_score = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0.0"))
    news_items = [it for it in news_items if (it.score or 0.0) >= min_score]

    return {
        "news": [it.to_dict() for it in news_items],
        "tools": [it.to_dict() for it in tool_items],
        "funding": [it.to_dict() for it in funding_items],
        "publications": [it.to_dict() for it in pub_items],
    }

# -----------------------------------------------------------------------------
# Compatibility helpers
# -----------------------------------------------------------------------------
def days_to_tavily_range(days: int) -> str:
    if days <= 7:
        return "day"
    if days <= 30:
        return "week"
    if days <= 90:
        return "month"
    return "year"


def tavily_search(query: str, days: int = 30,
                  include_domains: Optional[List[str]] = None,
                  max_results: int = 10) -> List[Dict[str, str]]:
    """Return dictionaries (title/url/published/snippet) for legacy code."""
    items: List[Dict[str, str]] = []
    try:
        raw = search_tavily(query, days=days, max_results=max_results)
    except Exception as exc:
        logger.warning("tavily_search wrapper failed: %s", exc)
        return items
    for it in raw:
        items.append({
            "title": it.title,
            "url": it.url,
            "published": it.published_at or "",
            "snippet": it.summary or "",
        })
    if include_domains:
        inc = [d.lower().strip() for d in include_domains if d.strip()]
        items = [x for x in items if any(x["url"].lower().endswith(d) or x["url"].lower().endswith("." + d) for d in inc)]
    return items[:max_results]
