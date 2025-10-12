
# filename: utils_sources.py
# -*- coding: utf-8 -*-
"""
Source classification & ranking helpers (Gold-Standard+)
- classify_source(url, domain?) -> (category, label, badge_class, weight)
- filter_and_rank(items) -> list[dict]  (dedup + category weight + recency)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any

_DOMAIN_RE = re.compile(r"^(?:https?://)?([^/]+)", re.I)

GOV_DOMAINS = {
    "europa.eu","bund.de","bmbf.de","bmwk.de","dlr.de","kfw.de","foerderdatenbank.de",
    "nrwbank.de","l-bank.de","bayern.de","berlin.de","ibb.de","ihk.de"
}
NEWS_DOMAINS = {
    "heise.de","golem.de","t3n.de","handelsblatt.com","faz.net","zeit.de","sueddeutsche.de",
    "spiegel.de","theverge.com","techcrunch.com","wired.com"
}
RESEARCH_DOMAINS = {
    "arxiv.org","nature.com","science.org","acm.org","ieee.org","stanford.edu","mit.edu","ox.ac.uk","uni-"
}
VENDOR_DOMAINS = {
    "openai.com","anthropic.com","deepmind.com","google.com","microsoft.com","azure.com","aws.amazon.com",
    "ai.meta.com","cohere.com","huggingface.co"
}

_CATEGORY_WEIGHT = {
    "gov": 100,
    "research": 90,
    "news": 70,
    "vendor": 60,
    "blog": 40,
    "other": 30,
}

def _domain_from(url: str) -> str:
    m = _DOMAIN_RE.search(url or "")
    host = (m.group(1) if m else "").lower()
    # strip subdomains
    parts = [p for p in host.split(":")[0].split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host

def classify_source(url: str, domain: str | None = None) -> Tuple[str,str,str,int]:
    """
    Returns (category, label, badge_class, weight)
    """
    d = (domain or _domain_from(url or "")).lower()
    cat = "other"; label = "Quelle"; badge = "badge--other"
    if any(d.endswith(g) for g in GOV_DOMAINS):
        cat, label, badge = "gov", "Amtlich/Behörde", "badge--gov"
    elif any(d.endswith(n) for n in NEWS_DOMAINS):
        cat, label, badge = "news", "Fachpresse", "badge--news"
    elif any((d.endswith(r) or r in d) for r in RESEARCH_DOMAINS):
        cat, label, badge = "research", "Studie/Forschung", "badge--research"
    elif any(d.endswith(v) for v in VENDOR_DOMAINS):
        cat, label, badge = "vendor", "Hersteller", "badge--vendor"
    elif d:
        cat, label, badge = "blog", "Blog/Portal", "badge--blog"
    weight = _CATEGORY_WEIGHT.get(cat, 10)
    return cat, label, badge, weight

def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s[:19], fmt)  # be tolerant
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None

def filter_and_rank(items: List[Dict[str,Any]], max_age_days: int | None = None) -> List[Dict[str,Any]]:
    """
    - normalizes urls/domains
    - boosts trusted domains
    - deduplicates by normalized url (domain+path without hash)
    - optional recency boost
    """
    if not items:
        return []

    # normalize & enrich
    normed = []
    seen = set()
    for it in items:
        url = (it.get("url") or it.get("link") or "").strip()
        if not url:
            continue
        norm_url = re.sub(r"#.*$", "", url)
        dom = it.get("domain") or _domain_from(norm_url)
        cat, label, badge, w = classify_source(norm_url, dom)
        dt = _parse_date(it.get("date") or it.get("published_date"))
        if norm_url in seen:
            continue
        seen.add(norm_url)
        normed.append({**it, "url": norm_url, "domain": dom, "cat": cat, "cat_label": label, "badge": badge, "_w": w, "_dt": dt})

    if not normed:
        return []

    # rank
    def _key(d):
        age_boost = 0
        if d.get("_dt"):
            age_days = (datetime.now(timezone.utc) - d["_dt"]).days
            age_boost = max(0, 90 - age_days)  # recent first
        return (d["_w"], age_boost)

    normed.sort(key=_key, reverse=True)
    return normed
