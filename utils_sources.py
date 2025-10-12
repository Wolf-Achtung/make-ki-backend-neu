# filename: utils_sources.py
# -*- coding: utf-8 -*-
"""
URL classification + ranking for report sources.
Categories map to CSS badges in the templates.
"""
from __future__ import annotations
from typing import Dict, Any, Iterable, List, Tuple
from urllib.parse import urlparse

BADGE_MAP = {
    "eu": ("EU", "badge--eu", 95),
    "gov": ("Behörde", "badge--gov", 90),
    "funding": ("Förderung", "badge--funding", 88),
    "academic": ("Wissenschaft", "badge--academic", 80),
    "media": ("Presse", "badge--media", 70),
    "vendor": ("Anbieter", "badge--vendor", 65),
    "ngo": ("NGO", "badge--ngo", 60),
    "blog": ("Blog", "badge--blog", 55),
    "web": ("Quelle", "badge--muted", 50),
}

def classify_source(url: str, domain: str | None = None) -> Tuple[str, str, str, int]:
    d = (domain or urlparse(url).netloc or "").lower()
    if d.endswith(".eu") or "europa.eu" in d:
        k = "eu"
    elif d.endswith(".gov") or d.endswith(".gouv.fr") or any(x in d for x in ["bmw", "bmbf", "kfw", "nrwbank", "ihk.de"]):
        k = "gov"
    elif any(x in d for x in ["foerder", "kfw", "nrwbank", "l-bank"]):
        k = "funding"
    elif any(x in d for x in ["arxiv.org", "acm.org", "ieee.org", "springer", "nature.com"]):
        k = "academic"
    elif any(x in d for x in ["reuters.com", "bloomberg.", "heise.de", "golem.de", "t3n.de", "zeit.de", "handelsblatt"]):
        k = "media"
    elif any(x in d for x in ["openai.com", "anthropic.com", "google.com", "microsoft.com", "sap.com", "salesforce.com"]):
        k = "vendor"
    elif any(x in d for x in ["medium.com", "substack.com", "dev.to"]):
        k = "blog"
    else:
        k = "web"
    label, badge, trust = BADGE_MAP.get(k, BADGE_MAP["web"])
    return (k, label, badge, trust)

def filter_and_rank(items: Iterable[Dict[str, Any]], dedupe: bool = True, max_per_domain: int = 3) -> List[Dict[str, Any]]:
    seen = {}
    out: List[Dict[str, Any]] = []
    for it in items:
        url = it.get("url") or ""
        dom = (it.get("domain") or "").lower() or urlparse(url).netloc.lower()
        if not url: 
            continue
        if dedupe and url in seen:
            continue
        # cap per domain
        if dedupe:
            cnt = sum(1 for x in out if (x.get("domain") or "").lower() == dom)
            if cnt >= max_per_domain:
                continue
        cat, label, badge, trust = classify_source(url, dom)
        it["domain"] = dom
        it["cat"] = cat
        it["badge"] = badge
        it["trust"] = trust
        out.append(it)
        seen[url] = True
    # sort: trust desc, then date desc (string), then title
    out.sort(key=lambda x: (x.get("trust", 0), x.get("date", ""), x.get("title","")), reverse=True)
    return out
# end of file
