# filename: utils_sources.py
# -*- coding: utf-8 -*-
"""
Source utilities: classification + ranking for News/Tools/Funding.
- classify_source(url, domain) -> (category, label, css_badge_class, trust_score[0..100])
- filter_and_rank(items, include_domains=None, exclude_domains=None, dedupe=True)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
import os, re, datetime

_BADGE_MAP = {
    "gov": ("Behörde/Öffentlich", "badge--gov", 95),
    "eu": ("EU/Official", "badge--gov", 95),
    "bank": ("Förderbank", "badge--gov", 90),
    "edu": ("Universität", "badge--edu", 85),
    "news": ("Fachpresse", "badge--news", 75),
    "vendor": ("Anbieter", "badge--vendor", 55),
    "community": ("Community", "badge--community", 50),
    "web": ("Web", "badge--muted", 50),
}

GOV_KEYS = ("bmwk.de","bmbf.de","dlr.de","kfw.de","nrwbank.de","l-bank.de","foerderdatenbank.de","bund.de",".gv.at",".admin.ch")
EU_KEYS = ("europa.eu","europa.eu.int","europa.europa","europa.europa.eu",".eu")
EDU_TLDS = (".edu",".ac.uk",".uni-",".uni",".ac.","fh-",".hs-")
NEWS_KEYS = ("heise.de","golem.de","t3n.de","handelsblatt.com","wired.com","techcrunch.com","theverge.com")
COMMUNITY_KEYS = ("github.com","stackoverflow.com","stackexchange.com","medium.com","substack.com","dev.to")

def _domain(url: str, provided: Optional[str] = None) -> str:
    if provided:
        return provided.lower()
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def classify_source(url: str, domain: Optional[str] = None) -> Tuple[str,str,str,int]:
    d = _domain(url or "", domain)
    if any(key in d for key in EU_KEYS):
        cat = "eu"
    elif any(key in d for key in GOV_KEYS) or d.endswith(".gov") or ".gov." in d:
        cat = "gov"
    elif any(d.endswith(tld) or tld in d for tld in EDU_TLDS):
        cat = "edu"
    elif any(key in d for key in NEWS_KEYS):
        cat = "news"
    elif any(key in d for key in COMMUNITY_KEYS):
        cat = "community"
    else:
        cat = "vendor" if any(k in (url or "") for k in ("/pricing","/features","/signup")) else "web"
    label, css, score = _BADGE_MAP.get(cat, ("Web","badge--muted",50))
    return (cat, label, css, score)

def _parse_date(s: str) -> Optional[datetime.datetime]:
    s = (s or "").strip()
    fmts = ("%Y-%m-%d","%Y/%m/%d","%d.%m.%Y","%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M:%SZ")
    for f in fmts:
        try:
            return datetime.datetime.strptime(s[:len(f)], f)
        except Exception:
            continue
    return None

def filter_and_rank(items: Iterable[Dict[str,Any]],
                    include_domains: Optional[str] = None,
                    exclude_domains: Optional[str] = None,
                    dedupe: bool = True) -> List[Dict[str,Any]]:
    """Common post-processing for search results:
       - normalize keys
       - optional domain allow/deny
       - dedupe (domain+title+url)
       - rank by trust score + recency
    """
    inc = [d.strip().lower() for d in (include_domains or os.getenv("SEARCH_INCLUDE_DOMAINS","")).split(",") if d.strip()]
    exc = [d.strip().lower() for d in (exclude_domains or os.getenv("SEARCH_EXCLUDE_DOMAINS","")).split(",") if d.strip()]

    seen: set = set()
    out: List[Dict[str,Any]] = []
    for it in items or []:
        url = (it.get("url") or it.get("link") or "").strip()
        if not url:
            continue
        dom = (it.get("domain") or "").lower() or _domain(url)
        title = (it.get("title") or it.get("name") or url).strip()
        date = (it.get("date") or it.get("published_date") or it.get("created") or "")

        if inc and not any(d in dom for d in inc):
            continue
        if exc and any(d in dom for d in exc):
            continue

        key = (dom, title[:80].lower(), url.split("#")[0])
        if dedupe and key in seen:
            continue
        seen.add(key)

        cat, label, badge, trust = classify_source(url, dom)
        it2 = {
            "title": title, "url": url, "domain": dom, "date": date,
            "category": cat, "trust": trust, "badge": badge, "label": label,
            "provider": it.get("provider") or it.get("source")
        }
        out.append(it2)

    def _score(x: Dict[str,Any]) -> float:
        trust = float(x.get("trust") or 50)
        dt = _parse_date(x.get("date") or "")
        rec = 0.0
        if dt:
            days = max(1.0, (datetime.datetime.utcnow() - dt).days or 1.0)
            rec = max(0.0, 30.0 - min(30.0, days))  # newer = larger
        return trust + 0.9*rec

    out.sort(key=_score, reverse=True)
    return out
