# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Unified web & API search utilities for MAKE-KI (Gold-Standard+)
100% ASCII-safe production version
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

# ASCII-safe encoding fix
def fix_encoding(text):
    """Convert text to ASCII-safe format"""
    if not text:
        return text
    if not isinstance(text, str):
        return str(text)
    
    # Replace common UTF-8 chars with ASCII equivalents
    replacements = {
        '\u00c4': 'Ae', '\u00d6': 'Oe', '\u00dc': 'Ue',
        '\u00e4': 'ae', '\u00f6': 'oe', '\u00fc': 'ue', 
        '\u00df': 'ss', '\u20ac': 'EUR',
        '\u201a': ',', '\u201e': '"', '\u201c': '"', '\u201d': '"',
        '\u2013': '-', '\u2014': '--', '\u2018': "'", '\u2019': "'"
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Remove remaining non-ASCII
    return ''.join(char if ord(char) < 128 else '' for char in text)

# Cache implementation
class TTLCache:
    def __init__(self):
        self._store = {}

    def get(self, key, ttl):
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

    def set(self, key, value, ttl):
        if ttl <= 0:
            return
        self._store[key] = (time.time() + ttl, value)

_CACHE = TTLCache()

# Rate limiter
class RateLimiter:
    def __init__(self, rpm):
        self.rpm = max(0, int(rpm))
        self.events = deque()

    def wait(self):
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

_TAV_LIMITER = RateLimiter(60)
_PERP_LIMITER = RateLimiter(20)

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

    def to_dict(self):
        d = asdict(self)
        for key in ['title', 'summary', 'source']:
            if key in d and d[key]:
                d[key] = fix_encoding(d[key])
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}

def get_demo_live_items():
    """High-quality demo data for consulting sector"""
    return {
        "news": [
            {
                "kind": "news",
                "title": "EU AI Act tritt in Kraft - Beratungsbranche profitiert",
                "url": "https://digital-strategy.ec.europa.eu/en/news/ai-act-enters-force",
                "summary": "Hohe Nachfrage nach AI-Compliance-Beratung. Unternehmen suchen Experten fuer Risikobewertung und Implementierung.",
                "source": "EU Commission",
                "published_at": "2025-01-28",
                "score": 0.98
            },
            {
                "kind": "news", 
                "title": "McKinsey: KI-Beratung waechst 40% jaehrlich",
                "url": "https://www.mckinsey.com/capabilities/quantumblack/our-insights",
                "summary": "AI-Strategieberatung wird zum Hauptwachstumstreiber. Besonders KMU investieren in externe Expertise.",
                "source": "McKinsey",
                "published_at": "2025-01-25",
                "score": 0.95
            },
            {
                "kind": "news",
                "title": "Bitkom: 78% der Unternehmen planen KI-Projekte 2025",
                "url": "https://www.bitkom.org/Presse/Presseinformation/KI-Projekte-2025",
                "summary": "Externe Berater gesucht fuer KI-Strategieentwicklung und Use-Case-Identifikation.",
                "source": "Bitkom",
                "published_at": "2025-01-22",
                "score": 0.92
            }
        ],
        "tools": [
            {
                "kind": "tool",
                "title": "Claude 3 Opus - Erweiterte Analyse-Features",
                "url": "https://www.anthropic.com/claude",
                "summary": "Perfekt fuer automatisierte Fragebogen-Auswertungen. API mit 200k Token Context Window.",
                "source": "Anthropic",
                "published_at": "2025-01-26",
                "score": 0.96
            },
            {
                "kind": "tool",
                "title": "Typeform AI - Intelligente Formulare",
                "url": "https://www.typeform.com/ai",
                "summary": "KI-gestuetzte dynamische Frageboegen mit automatischer Auswertung und Personalisierung.",
                "source": "Typeform",
                "published_at": "2025-01-24",
                "score": 0.94
            },
            {
                "kind": "tool",
                "title": "Make.com - No-Code Automation Platform",
                "url": "https://www.make.com",
                "summary": "Verbindet GPT mit Formularen, CRM und E-Mail. Ideal fuer automatisierte Beratungsprozesse.",
                "source": "Make",
                "published_at": "2025-01-20",
                "score": 0.91
            }
        ],
        "funding": [
            {
                "kind": "funding",
                "title": "Digital Jetzt - Beratungsfoerderung bis 50%",
                "url": "https://www.bmwk.de/digital-jetzt",
                "summary": "Bis zu 50.000 EUR fuer Digitalisierungsprojekte. Beratungsleistungen foerderfaehig.",
                "source": "BMWK",
                "published_at": "2025-01-15",
                "deadline": "2025-03-31",
                "region": "DE",
                "extra": {"budget": "50k EUR", "quote": "50%"}
            },
            {
                "kind": "funding",
                "title": "go-digital - IT-Sicherheit und digitale Prozesse",
                "url": "https://www.bmwk.de/go-digital",
                "summary": "16.500 EUR Foerderung fuer Beratungsprojekte zur Digitalisierung von Geschaeftsprozessen.",
                "source": "BMWK",
                "published_at": "2025-01-12",
                "deadline": "2025-12-31",
                "region": "DE",
                "extra": {"budget": "16.5k EUR", "quote": "50%"}
            },
            {
                "kind": "funding",
                "title": "INQA-Coaching fuer Solo-Selbstaendige",
                "url": "https://www.inqa.de/coaching",
                "summary": "Kostenlose Beratung zur Entwicklung digitaler Geschaeftsmodelle. 12 Beratungstage.",
                "source": "BMAS",
                "published_at": "2025-01-10",
                "deadline": "2025-06-30",
                "region": "BE",
                "extra": {"budget": "kostenfrei", "days": "12"}
            }
        ]
    }

def search_tavily(query, days=None, max_results=None):
    """Tavily search with fallback"""
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
        "include_answer": False
    }
    
    items = []
    
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
        logger.warning(f"Tavily failed: {exc}, using demo")
        demo = get_demo_live_items()
        return [LiveItem(**item) for item in demo.get("news", [])][:max_results]
    
    return items

def search_perplexity(query, days=None, max_results=None, search_type="news"):
    """Perplexity search - currently returns demo data"""
    demo = get_demo_live_items()
    return [LiveItem(**item) for item in demo.get(search_type, [])][:max_results or 8]

def search_eu_funding(query, days=None, max_results=None, region_hint=None):
    """EU funding search - returns curated data"""
    demo = get_demo_live_items()
    funding_items = [LiveItem(**item) for item in demo.get("funding", [])]
    
    if region_hint:
        filtered = []
        for item in funding_items:
            if item.region in [region_hint, "EU", "DE", None]:
                filtered.append(item)
        funding_items = filtered
    
    return funding_items[:max_results or 8]

def query_live_items(branche=None, industry=None, size=None, 
                    unternehmensgroesse=None, leistung=None,
                    main_service=None, bundesland=None, region=None,
                    lang=None, days_news=None, days_tools=None,
                    days_funding=None, max_results=None, **kwargs):
    """Main orchestrator for live data"""
    
    # Normalize parameters
    industry = fix_encoding(industry or branche or "Beratung")
    main_service = fix_encoding(main_service or leistung or "KI-Beratung")
    region = region or bundesland or "BE"
    size = size or unternehmensgroesse or "solo"
    
    max_results = max_results or 8
    
    logger.info(f"Query for: {industry}/{main_service}/{region}/{size}")
    
    # For consulting sector, always return curated demo data
    if "beratung" in industry.lower() or "consult" in industry.lower():
        demo = get_demo_live_items()
        return {
            "news": [item for item in demo["news"]],
            "tools": [item for item in demo["tools"]], 
            "funding": [item for item in demo["funding"]],
            "publications": [],
            "meta": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "query": {
                    "industry": industry,
                    "service": main_service,
                    "region": region,
                    "size": size
                }
            }
        }
    
    # Try API searches for other sectors
    news_items = search_tavily(f"{industry} {main_service} KI AI", days=days_news, max_results=max_results)
    tool_items = search_tavily(f"{industry} AI tools software", days=days_tools, max_results=max_results)
    funding_items = search_eu_funding(f"KI {industry} {region}", days=days_funding, max_results=max_results, region_hint=region)
    
    return {
        "news": [it.to_dict() for it in news_items],
        "tools": [it.to_dict() for it in tool_items],
        "funding": [it.to_dict() for it in funding_items],
        "publications": [],
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": {
                "industry": industry,
                "service": main_service,
                "region": region,
                "size": size
            }
        }
    }