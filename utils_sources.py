
# filename: utils_sources.py
# -*- coding: utf-8 -*-
"""
Utility: Source classification & ranking for Live-Layer
- classify_source(url, domain) -> (category, label, css_badge, weight)
- filter_and_rank(items, include_domains_env="SEARCH_INCLUDE_DOMAINS")
The CSS classes referenced here are defined in the pdf templates:
  .badge, .badge--gov, .badge--news, .badge--vendor, .badge--community, .badge--edu, .badge--official
"""

from __future__ import annotations
from typing import Dict, List, Tuple
import os
import re
import urllib.parse as _url

_GOV_HINTS = (
    "europa.eu","bund.de","bmbf.de","bmwk.de","bmwi.de","dlr.de","kfw.de","nrwbank.de","l-bank.de",
    "foerderdatenbank.de","ihk.de","berlin.de","ibb.de","gov","gouv","admin.ch","gv.at"
)
_NEWS_HINTS = ("heise.de","golem.de","t3n.de","theverge.com","wired.com","handelsblatt","faz.net","ft.com","reuters.com")
_EDU_HINTS  = (".edu",".ac.uk",".uni-",".uni-", "uni-", "uni-")
_VENDOR_HINTS = ("openai.com","anthropic.com","google.com","deepmind.com","microsoft.com","azure.com","aws.amazon.com",
                 "oracle.com","salesforce.com","sap.com","notion.so","atlassian.com","databricks.com","snowflake.com")
_COMMUNITY_HINTS = ("github.com","huggingface.co","medium.com","substack.com","reddit.com","stack overflow","stackoverflow.com")

def _norm_domain(url: str, domain: str | None = None) -> str:
    if domain:
        return domain.lower()
    try:
        return _url.urlparse(url).netloc.lower()
    except Exception:
        return ""

def classify_source(url: str, domain: str | None = None) -> Tuple[str, str, str, int]:
    """
    Returns: (category, human_label, css_badge_class, weight_for_ranking)
    Higher weight -> earlier in list.
    """
    d = _norm_domain(url, domain)
    u = (url or "").lower()

    def _any(hints: tuple) -> bool:
        return any(h in d or h in u for h in hints)

    if any(d.endswith(suf) for suf in (".de",".eu",".gov",".gouv.fr",".admin.ch",".gv.at")) and _any(_GOV_HINTS):
        return ("gov", "Amtlich/Behörde", "badge--gov", 90)
    if _any(_NEWS_HINTS):
        return ("news", "News/Medien", "badge--news", 70)
    if _any(_EDU_HINTS):
        return ("edu", "Wissenschaft/Uni", "badge--edu", 60)
    if _any(_VENDOR_HINTS) or re.search(r"/(product|pricing|docs|security)", u):
        return ("vendor", "Hersteller/Anbieter", "badge--vendor", 55)
    if _any(_COMMUNITY_HINTS):
        return ("community", "Community/Tech", "badge--community", 50)
    if re.match(r"^www\.", d) or "." in d:
        return ("official", "Offizielle Website", "badge--official", 40)
    return ("other", "Quelle", "badge", 10)

def _dedupe(items: List[Dict]) -> List[Dict]:
    seen = set()
    out  = []
    for it in items or []:
        url = (it.get("url") or "").split("#")[0].strip()
        if not url: 
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(it)
    return out

def _apply_include_filter(items: List[Dict]) -> List[Dict]:
    incl = (os.getenv("SEARCH_INCLUDE_DOMAINS") or "").strip()
    if not incl:
        return items
    whitelist = [d.strip().lower() for d in incl.split(",") if d.strip()]
    if not whitelist:
        return items
    out = []
    for it in items or []:
        url = it.get("url") or ""
        dom = _norm_domain(url, it.get("domain"))
        if any(dom.endswith(w) or w in dom for w in whitelist):
            out.append(it)
    return out

def filter_and_rank(items: List[Dict]) -> List[Dict]:
    items = _dedupe(items)
    items = _apply_include_filter(items)
    def _key(it: Dict) -> int:
        url = it.get("url") or ""
        dom = _norm_domain(url, it.get("domain"))
        cat, _, _, weight = classify_source(url, dom)
        score = int(it.get("score") or 0)
        # prefer gov/edu/news, then score
        return -(weight*100 + score)
    items.sort(key=_key)
    # attach computed domain/category for later rendering
    for it in items:
        url = it.get("url") or ""
        it["domain"] = _norm_domain(url, it.get("domain"))
        cat, label, badge, _ = classify_source(url, it["domain"])
        it["_category"] = cat
        it["_label"] = label
        it["_badge"] = badge
    return items
