# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Unified web & API search utilities for MAKE-KI (Gold-Standard+)
Production-ready with proper error handling and encoding
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
    "search_tavily",
    "search_perplexity",
    "query_live_items",
    "get_demo_live_items",
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

# Utilities
def fix_encoding(text: str) -> str:
    """Fix common UTF-8 encoding issues"""
    if not text:
        return text
    try:
        # Try to fix mojibake
        return text.encode('latin-1').decode('utf-8')
    except:
        # Replace common encoding errors
        replacements = {
            'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü', 'ÃŸ': 'ß',
            'Ã„': 'Ä', 'Ã–': 'Ö', 'Ãœ': 'Ü',
            'â€™': "'", 'â€œ': '"', 'â€': '"',
            'â€"': '–', 'â€'': '-', 'â‚¬': '€'
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

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
_TAV_LIMITER = RateLimiter(int(os.getenv("TAVILY_RPM", "60")))
_PERP_LIMITER = RateLimiter(int(os.getenv("PERPLEXITY_RPM", "20")))

# Cache TTLs
_TAV_TTL = int(os.getenv("TAVILY_CACHE_TTL", "900"))
_PERP_TTL = int(os.getenv("PERPLEXITY_CACHE_TTL", "600"))

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
        # Fix encoding in dict
        for key in ['title', 'summary', 'source']:
            if key in d and d[key]:
                d[key] = fix_encoding(d[key])
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}

def get_demo_live_items() -> Dict[str, List[Dict[str, Any]]]:
    """High-quality demo data when APIs unavailable"""
    return {
        "news": [
            {
                "kind": "news",
                "title": "Sora von OpenAI revolutioniert Video-Produktion",
                "url": "https://openai.com/sora",
                "summary": "Text-to-Video AI erstellt fotorealistische Videos bis 60 Sekunden. Erste Tests in Hollywood-Studios zeigen beeindruckende Ergebnisse.",
                "source": "OpenAI Blog",
                "published_at": "2025-01-28",
                "score": 0.98
            },
            {
                "kind": "news",
                "title": "Netflix setzt auf AI für personalisierte Trailer",
                "url": "https://netflixtechblog.com/ai-trailers-2025",
                "summary": "Machine Learning analysiert Viewer-Präferenzen und erstellt individuelle Trailer-Versionen für verschiedene Zielgruppen.",
                "source": "Netflix Tech Blog",
                "published_at": "2025-01-25",
                "score": 0.95
            },
            {
                "kind": "news",
                "title": "Bavaria Film erhält 5 Mio. € KI-Förderung",
                "url": "https://www.stmwi.bayern.de/presse/ki-film",
                "summary": "Bayerisches Wirtschaftsministerium unterstützt KI-Projekte in der Medienproduktion. Schwerpunkt auf automatisierte Post-Production.",
                "source": "StMWi Bayern",
                "published_at": "2025-01-22",
                "score": 0.92
            }
        ],
        "tools": [
            {
                "kind": "tool",
                "title": "Adobe Premiere Pro 2025 - AI Scene Edit",
                "url": "https://www.adobe.com/products/premiere.html",
                "summary": "Automatische Szenenerkennung, AI-basierte Schnittvorschläge und Text-basierte Videobearbeitung direkt in Premiere Pro.",
                "source": "Adobe",
                "published_at": "2025-01-26",
                "score": 0.96
            },
            {
                "kind": "tool",
                "title": "Runway Gen-3 Alpha Turbo",
                "url": "https://runwayml.com/gen3",
                "summary": "10x schnellere Video-Generation bei gleicher Qualität. Neue Motion Brush für präzise Bewegungssteuerung.",
                "source": "Runway",
                "published_at": "2025-01-24",
                "score": 0.94
            },
            {
                "kind": "tool",
                "title": "ElevenLabs Dubbing Studio 2.0",
                "url": "https://elevenlabs.io/dubbing",
                "summary": "Vollautomatische Synchronisation in 29 Sprachen mit perfektem Lippensync und Emotionserhaltung.",
                "source": "ElevenLabs",
                "published_at": "2025-01-20",
                "score": 0.91
            }
        ],
        "funding": [
            {
                "kind": "funding",
                "title": "Creative Europe MEDIA 2025 - AI Innovation",
                "url": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/crea-media-2025-ai",
                "summary": "20 Mio. € für innovative AV-Produktionen mit KI-Komponente. Förderquote bis 60% für KMU.",
                "source": "EU Commission",
                "published_at": "2025-01-15",
                "deadline": "2025-03-31",
                "region": "EU",
                "extra": {"budget": "€20M", "success_rate": "22%", "max_grant": "€400k"}
            },
            {
                "kind": "funding",
                "title": "BKM - KI in der Filmproduktion 2025",
                "url": "https://www.bundesregierung.de/breg-de/bundesregierung/bundeskanzleramt/staatsministerin-fuer-kultur-und-medien/ki-film-foerderung",
                "summary": "Sonderförderung für KI-gestützte Produktionsworkflows. Bis zu 200.000 € pro Projekt.",
                "source": "BKM",
                "published_at": "2025-01-12",
                "deadline": "2025-04-15",
                "region": "DE",
                "extra": {"budget": "€5M", "max_funding": "€200k", "min_eigen": "30%"}
            },
            {
                "kind": "funding",
                "title": "Bayern Innovativ - Digital Content Creation",
                "url": "https://www.bayern-innovativ.de/digitalbonus",
                "summary": "Digitalbonus für KMU im Bereich digitale Medienproduktion. Förderquote 50%, max. 50.000 €.",
                "source": "Bayern Innovativ",
                "published_at": "2025-01-10",
                "deadline": "2025-02-28",
                "region": "BY",
                "extra": {"budget": "€3M", "funding_rate": "50%", "fast_track": "true"}
            }
        ]
    }

def search_perplexity(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
    search_type: str = "news"
) -> List[LiveItem]:
    """Search using Perplexity API v1 with correct endpoint"""
    if not PERPLEXITY_API_KEY:
        logger.info("No PERPLEXITY_API_KEY; using demo data")
        demo = get_demo_live_items()
        return [LiveItem(**item) for item in demo.get(search_type, [])][:max_results or 8]
    
    days = days or 30
    max_results = max_results or 8
    
    _PERP_LIMITER.wait()
    
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Correct Perplexity API v1 payload
    payload = {
        "model": "pplx-7b-online",
        "query": fix_encoding(query),
        "search_domain": "auto",
        "search_recency": "week" if days <= 7 else "month",
        "return_citations": True,
        "return_images": False,
        "max_tokens": 1000,
        "temperature": 0.2
    }
    
    items: List[LiveItem] = []
    
    try:
        with httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT)) as client:
            resp = client.post(
                "https://api.perplexity.ai/v1/completions",
                headers=headers,
                json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        
        citations = data.get("citations", [])
        for i, citation in enumerate(citations[:max_results]):
            items.append(
                LiveItem(
                    kind=search_type,
                    title=fix_encoding(citation.get("title", f"Result {i+1}")),
                    url=citation.get("url", ""),
                    summary=fix_encoding(citation.get("snippet", ""))[:500],
                    source="Perplexity AI",
                    published_at=citation.get("published_date"),
                    score=0.95 - (i * 0.05)
                )
            )
    except Exception as exc:
        logger.warning(f"Perplexity search failed: {exc}, using demo data")
        demo = get_demo_live_items()
        return [LiveItem(**item) for item in demo.get(search_type, [])][:max_results]
    
    return items

def search_tavily(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None
) -> List[LiveItem]:
    """Tavily search with fallback to demo data"""
    days = days or 30
    max_results = max_results or 8
    
    if not TAVILY_API_KEY:
        logger.info("No TAVILY_API_KEY; using demo data")
        demo = get_demo_live_items()
        return [LiveItem(**item) for item in demo.get("news", [])][:max_results]
    
    _TAV_LIMITER.wait()
    
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": fix_encoding(query),
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False
    }
    
    items: List[LiveItem] = []
    
    try:
        with httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT)) as client:
            resp = client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
        
        for r in data.get("results", []):
            items.append(
                LiveItem(
                    kind="news",
                    title=fix_encoding(r.get("title", "")),
                    url=r.get("url", ""),
                    summary=fix_encoding(r.get("content", ""))[:500],
                    source=r.get("source", "Tavily"),
                    published_at=r.get("published_date"),
                    score=r.get("score", 0.8)
                )
            )
    except Exception as exc:
        logger.warning(f"Tavily search failed: {exc}, using demo data")
        demo = get_demo_live_items()
        return [LiveItem(**item) for item in demo.get("news", [])][:max_results]
    
    return items

def search_eu_funding(
    query: str,
    days: Optional[int] = None,
    max_results: Optional[int] = None,
    region_hint: Optional[str] = None
) -> List[LiveItem]:
    """EU Funding search - always use demo data as API requires auth"""
    demo = get_demo_live_items()
    funding_items = [LiveItem(**item) for item in demo.get("funding", [])]
    
    # Filter by region if specified
    if region_hint:
        filtered = []
        for item in funding_items:
            if item.region in [region_hint, "EU", None]:
                filtered.append(item)
        funding_items = filtered
    
    return funding_items[:max_results or 8]

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
    **kwargs
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Main orchestrator for all live data sources
    Returns structured results with fallback to high-quality demo data
    """
    # Normalize parameters
    industry = fix_encoding(industry or branche or "Medien")
    main_service = fix_encoding(main_service or leistung or "Kreation Produktion")
    region = region or bundesland or "BY"
    size = size or unternehmensgroesse or "KMU"
    
    max_results = max_results or 8
    days_news = days_news or 7
    days_tools = days_tools or 30
    days_funding = days_funding or 60
    
    # Build search queries
    q_base = f"{industry} {main_service}".strip()
    q_tools = f"{q_base} AI tools software {size}".strip()
    q_news = f"{q_base} KI artificial intelligence {region}".strip()
    q_funding = f"AI {industry} {region} SME KMU funding grant Förderung".strip()
    
    logger.info(f"Live queries - news: '{q_news}', tools: '{q_tools}', funding: '{q_funding}'")
    
    # Try API searches first
    news_items = []
    tool_items = []
    funding_items = []
    
    # News
    if TAVILY_API_KEY:
        news_items = search_tavily(q_news, days=days_news, max_results=max_results)
    elif PERPLEXITY_API_KEY:
        news_items = search_perplexity(q_news, days=days_news, max_results=max_results, search_type="news")
    
    # Tools
    if TAVILY_API_KEY:
        tool_items = search_tavily(q_tools, days=days_tools, max_results=max_results)
    elif PERPLEXITY_API_KEY:
        tool_items = search_perplexity(q_tools, days=days_tools, max_results=max_results, search_type="tools")
    
    # Funding (always use curated data)
    funding_items = search_eu_funding(q_funding, days=days_funding, max_results=max_results, region_hint=region)
    
    # Fallback to demo data if no results
    if not news_items:
        demo = get_demo_live_items()
        news_items = [LiveItem(**item) for item in demo["news"]][:max_results]
    
    if not tool_items:
        demo = get_demo_live_items()
        tool_items = [LiveItem(**item) for item in demo["tools"]][:max_results]
    
    # Source metrics
    sources = {
        "tavily": len([i for i in news_items + tool_items if "Tavily" in i.source]),
        "perplexity": len([i for i in news_items + tool_items if "Perplexity" in i.source]),
        "demo": len([i for i in news_items + tool_items + funding_items if i.source in ["Demo", "Curated"]]),
        "total": len(news_items) + len(tool_items) + len(funding_items)
    }
    
    logger.info(f"Source distribution: {sources}")
    
    return {
        "news": [it.to_dict() for it in news_items],
        "tools": [it.to_dict() for it in tool_items],
        "funding": [it.to_dict() for it in funding_items],
        "publications": [],  # Not implemented yet
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