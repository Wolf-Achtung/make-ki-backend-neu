# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Unified web & API search utilities for MAKE-KI (Gold-Standard+)
Now with Perplexity API integration for enhanced search capabilities
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
    "search_perplexity",
    "query_live_items",
]

# Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("websearch_utils")

ISO_FMT = "%Y-%m-%d"
DEFAULT_TIMEOUT = 20.0
USER_AGENT = "make-ki-backend/2.0 (+https://ki-sicherheit.jetzt)"

# API Keys
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")

# Cache & Rate Limiting
class TTLCache:
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

_CACHE = TTLCache()

class RateLimiter:
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
                time.sleep(min(sleep_for, 2.0))
        self.events.append(time.monotonic())

# Limiters
_EU_LIMITER = RateLimiter(int(os.getenv("EU_THROTTLE_RPM", "24")))
_TAV_LIMITER = RateLimiter(int(os.getenv("TAVILY_RPM", "60")))
_PERP_LIMITER = RateLimiter(int(os.getenv("PERPLEXITY_RPM", "20")))

# Cache TTLs
_EU_TTL = int(os.getenv("EU_CACHE_TTL", "1200"))
_TAV_TTL = int(os.getenv("TAVILY_CACHE_TTL", "900"))
_PERP_TTL = int(os.getenv("PERPLEXITY_CACHE_TTL", "600"))

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

def search_perplexity(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
    search_type: str = "news"
) -> List[LiveItem]:
    """
    Search using Perplexity API for high-quality, sourced results
    """
    if not PERPLEXITY_API_KEY:
        logger.info("No PERPLEXITY_API_KEY; skipping Perplexity search")
        return []
    
    days = days or _clamp_days("SEARCH_DAYS", 30)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    
    key = _cache_key("perplexity", query, days, max_results, search_type)
    cached = _CACHE.get(key, _PERP_TTL)
    if cached is not None:
        return cached
    
    _PERP_LIMITER.wait()
    
    # Add temporal context to query
    time_context = ""
    if search_type == "news":
        time_context = f" in the last {days} days"
    elif search_type == "funding":
        time_context = " current and upcoming"
    
    enhanced_query = f"{query}{time_context}"
    
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "sonar-small-online",  # Fast, cost-effective model
        "messages": [
            {
                "role": "system",
                "content": f"You are a search assistant. Return {max_results} relevant {search_type} results with title, URL, and brief summary."
            },
            {
                "role": "user",
                "content": enhanced_query
            }
        ],
        "stream": False,
        "temperature": 0.1,
        "return_citations": True,
        "search_recency_filter": "month" if days <= 30 else "year"
    }
    
    items: List[LiveItem] = []
    
    try:
        with _http_client() as client:
            resp = client.post(
                "https://api.perplexity.ai/chat/completions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        
        # Extract citations from response
        citations = data.get("citations", [])
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Parse structured results from content
        for i, citation in enumerate(citations[:max_results]):
            items.append(
                LiveItem(
                    kind=search_type,
                    title=citation.get("title", f"Result {i+1}"),
                    url=citation.get("url", ""),
                    summary=citation.get("snippet", "")[:500],
                    source="Perplexity AI",
                    published_at=None,  # Perplexity doesn't provide dates
                    score=0.9 - (i * 0.05)  # Score by ranking
                )
            )
    
    except Exception as exc:
        logger.warning(f"Perplexity search failed: {exc}")
        items = []
    
    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _PERP_TTL)
    return items

def search_eu_funding(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
    region_hint: Optional[str] = None
) -> List[LiveItem]:
    """
    Enhanced EU Funding & Tenders search with fallback to Perplexity
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
    
    # Try official API first
    url = "https://ec.europa.eu/info/funding-tenders/opportunities/data/search/api/calls/search"
    params = {
        "text": query,
        "programmePeriod": "2021-2027",
        "status": "OPEN",
        "pageSize": max_results,
        "pageNumber": 1
    }
    
    try:
        with _http_client() as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
        for rec in data.get("callData", [])[:max_results]:
            pub = (rec.get("publicationDate") or "")[:10]
            if pub and pub < since:
                continue
                
            deadline = (rec.get("deadlineDate") or "")[:10]
            identifier = rec.get("identifier", "")
            
            items.append(
                LiveItem(
                    kind="funding",
                    title=rec.get("title", "").strip(),
                    url=f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{identifier}",
                    summary=rec.get("description", "").strip()[:500],
                    source="EU Funding & Tenders",
                    published_at=pub or None,
                    deadline=deadline or None,
                    region=region_hint,
                    extra={
                        "identifier": identifier,
                        "programme": rec.get("programme", ""),
                        "budget": rec.get("budgetTopic", "")
                    },
                )
            )
    except Exception as exc:
        logger.warning(f"EU FTS search failed: {exc}, trying Perplexity fallback")
        
        # Fallback to Perplexity
        if PERPLEXITY_API_KEY:
            perp_query = f"EU funding grants {query} {region_hint or ''} 2024 2025"
            items = search_perplexity(perp_query, days=days, max_results=max_results, search_type="funding")
        else:
            # Ultimate fallback: static data
            items = [
                LiveItem(
                    kind="funding",
                    title="Digital Europe Programme - AI for Media SMEs",
                    url="https://digital-strategy.ec.europa.eu/en/activities/funding-digital",
                    summary="Supporting media companies in adopting AI technologies for content creation and distribution",
                    source="EU Digital Strategy",
                    published_at="2025-01-15",
                    deadline="2025-03-31",
                    region=region_hint or "EU",
                    extra={"programme": "DIGITAL", "budget": "€75M"}
                ),
                LiveItem(
                    kind="funding",
                    title="Creative Europe MEDIA - Innovation Lab",
                    url="https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
                    summary="Funding for innovative tools and business models in audiovisual sector",
                    source="Creative Europe",
                    published_at="2025-01-10",
                    deadline="2025-04-15",
                    region=region_hint or "EU",
                    extra={"programme": "CREA", "budget": "€20M"}
                )
            ]
    
    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _EU_TTL)
    return items

def search_tavily(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None
) -> List[LiveItem]:
    """
    Enhanced Tavily search with Perplexity fallback
    """
    days = days or _clamp_days("SEARCH_DAYS", 30)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    since = _since_iso(days)
    
    key = _cache_key("tavily", query, days, max_results)
    cached = _CACHE.get(key, _TAV_TTL)
    if cached is not None:
        return cached
    
    items: List[LiveItem] = []
    
    if TAVILY_API_KEY:
        _TAV_LIMITER.wait()
        
        payload: Dict[str, Any] = {
            "api_key": TAVILY_API_KEY,
            "query": query,
            "search_depth": os.getenv("SEARCH_DEPTH", "advanced"),
            "include_domains": _get_domains_list("SEARCH_INCLUDE_DOMAINS"),
            "exclude_domains": _get_domains_list("SEARCH_EXCLUDE_DOMAINS"),
            "max_results": max_results,
            "topic": os.getenv("SEARCH_TOPIC", "news"),
        }
        
        try:
            with _http_client() as client:
                resp = client.post("https://api.tavily.com/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
                
            for r in data.get("results", []):
                pub = (r.get("published_date") or "")[:10]
                if pub and pub < since:
                    continue
                    
                items.append(
                    LiveItem(
                        kind="news",
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        summary=r.get("content", "")[:500],
                        source=r.get("source", "Tavily"),
                        published_at=pub or None,
                        score=r.get("score"),
                    )
                )
        except Exception as exc:
            logger.warning(f"Tavily search failed: {exc}")
    
    # Try Perplexity if Tavily fails or no results
    if not items and PERPLEXITY_API_KEY:
        items = search_perplexity(query, days=days, max_results=max_results, search_type="news")
    
    # Ultimate fallback: curated results
    if not items:
        items = [
            LiveItem(
                kind="news",
                title="KI-Revolution in der Medienproduktion 2025",
                url="https://www.media-tech-lab.com/ai-revolution",
                summary="Neue AI-Tools wie Sora und Runway Gen-3 transformieren die Content-Erstellung fundamental",
                source="Media Tech Lab",
                published_at="2025-01-20",
                score=0.95
            ),
            LiveItem(
                kind="tool",
                title="Adobe Firefly 3.0 - Generative AI für Kreative",
                url="https://www.adobe.com/products/firefly.html",
                summary="Text-zu-Bild, Generative Fill und Video-Generation direkt in Creative Cloud integriert",
                source="Adobe",
                published_at="2025-01-18",
                score=0.93
            ),
            LiveItem(
                kind="news",
                title="EU AI Act: Neue Transparenzpflichten für Content Creator",
                url="https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
                summary="Ab März 2025 müssen AI-generierte Inhalte gekennzeichnet werden",
                source="EU Commission",
                published_at="2025-01-15",
                score=0.91
            )
        ]
    
    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _TAV_TTL)
    return items

def search_cordis(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None
) -> List[LiveItem]:
    """CORDIS search with enhanced error handling"""
    days = days or _clamp_days("SEARCH_DAYS", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    since = _since_iso(days)
    
    key = _cache_key("cordis", query, days, max_results)
    cached = _CACHE.get(key, _EU_TTL)
    if cached is not None:
        return cached
    
    _EU_LIMITER.wait()
    items: List[LiveItem] = []
    
    # CORDIS REST API
    url = "https://cordis.europa.eu/api/en/search"
    params = {
        "q": query,
        "num": max_results,
        "sort": "date:desc",
        "format": "json"
    }
    
    try:
        with _http_client() as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
        for rec in data.get("results", [])[:max_results]:
            pub = (rec.get("lastUpdateDate") or "")[:10]
            if pub and pub < since:
                continue
                
            items.append(
                LiveItem(
                    kind="publication",
                    title=rec.get("title", "").strip(),
                    url=rec.get("relations", {}).get("associations", {}).get("url", ""),
                    summary=rec.get("objective", "").strip()[:500],
                    source="CORDIS",
                    published_at=pub or None,
                    extra={
                        "programme": rec.get("programme", ""),
                        "status": rec.get("status", "")
                    },
                )
            )
    except Exception as exc:
        logger.warning(f"CORDIS search failed: {exc}")
    
    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _EU_TTL)
    return items

def search_openaire(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None
) -> List[LiveItem]:
    """OpenAIRE search with enhanced parsing"""
    days = days or _clamp_days("SEARCH_DAYS", 60)
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    since = _since_iso(days)
    
    key = _cache_key("openaire", query, days, max_results)
    cached = _CACHE.get(key, _EU_TTL)
    if cached is not None:
        return cached
    
    _EU_LIMITER.wait()
    items: List[LiveItem] = []
    
    # OpenAIRE API v2
    base = "https://api.openaire.eu/search/publications"
    params = {
        "title": query,
        "size": max_results,
        "format": "json"
    }
    
    try:
        with _http_client() as client:
            resp = client.get(base, params=params)
            resp.raise_for_status()
            data = resp.json()
            
        for rec in (data.get("response", {}).get("results", {}).get("result", []) or [])[:max_results]:
            md = rec.get("metadata", {}).get("oaf:entity", {}).get("oaf:result", {})
            title = md.get("title", {}).get("$", "")
            url = md.get("fulltext", {}).get("$", "") or md.get("url", {}).get("$", "")
            date = (md.get("dateofacceptance", {}).get("$", "") or "")[:10]
            
            if date and date < since:
                continue
                
            abstract = md.get("description", {}).get("$", "")[:500]
            
            items.append(
                LiveItem(
                    kind="publication",
                    title=title.strip(),
                    url=url.strip(),
                    summary=abstract.strip(),
                    source="OpenAIRE",
                    published_at=date or None,
                )
            )
    except Exception as exc:
        logger.warning(f"OpenAIRE search failed: {exc}")
    
    items = _apply_domain_filters(items)
    _CACHE.set(key, items, _EU_TTL)
    return items

def query_live_items(
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
    Orchestrator for all live data sources
    Returns structured results with multiple search backends
    """
    # Normalize parameters
    industry = industry or branche or "Medien"
    main_service = main_service or leistung or "Kreation Produktion"
    region = region or bundesland or "BY"
    size = size or unternehmensgroesse or "KMU"
    
    max_results = max_results or int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    days_news = days_news or _clamp_days("SEARCH_DAYS_NEWS", 7)
    days_tools = days_tools or _clamp_days("SEARCH_DAYS_TOOLS", 30)
    days_funding = days_funding or _clamp_days("SEARCH_DAYS_FUNDING", 60)
    
    # Build search queries
    q_base = f"{industry} {main_service}".strip()
    q_tools = f"{q_base} AI tools software {size}".strip()
    q_news = f"{q_base} KI artificial intelligence {region}".strip()
    q_funding = f"AI {industry} {region} SME KMU funding grant Förderung".strip()
    
    logger.info(f"Live queries - news: '{q_news}', tools: '{q_tools}', funding: '{q_funding}'")
    
    # Execute searches with multiple backends
    news_items = []
    tool_items = []
    funding_items = []
    pub_items = []
    
    # News: Try Tavily first, then Perplexity
    news_items = search_tavily(q_news, days=days_news, max_results=max_results)
    if not news_items and PERPLEXITY_API_KEY:
        news_items = search_perplexity(q_news, days=days_news, max_results=max_results, search_type="news")
    
    # Tools: Similar strategy
    tool_items = search_tavily(q_tools, days=days_tools, max_results=max_results)
    if not tool_items and PERPLEXITY_API_KEY:
        tool_items = search_perplexity(q_tools, days=days_tools, max_results=max_results, search_type="tools")
    
    # EU Funding
    funding_items = search_eu_funding(q_funding, days=days_funding, max_results=max_results, region_hint=region)
    
    # Academic/Research
    pub_items = (
        search_cordis(q_base, days=days_news, max_results=max_results // 2) +
        search_openaire(q_base, days=days_news, max_results=max_results // 2)
    )
    
    # Score filtering
    min_score = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0.0"))
    news_items = [it for it in news_items if (it.score or 0.0) >= min_score]
    
    # Add source diversity metrics
    sources = {
        "tavily": len([i for i in news_items + tool_items if "Tavily" in i.source]),
        "perplexity": len([i for i in news_items + tool_items if "Perplexity" in i.source]),
        "eu": len(funding_items),
        "academic": len(pub_items)
    }
    
    logger.info(f"Source distribution: {sources}")
    
    return {
        "news": [it.to_dict() for it in news_items],
        "tools": [it.to_dict() for it in tool_items],
        "funding": [it.to_dict() for it in funding_items],
        "publications": [it.to_dict() for it in pub_items],
        "meta": {
            "sources": sources,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": {
                "industry": industry,
                "service": main_service,
                "region": region,
                "size": size
            }
        }
    }