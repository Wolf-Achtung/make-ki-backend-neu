# filename: utils_sources.py
# -*- coding: utf-8 -*-
"""
Source classification + ranking utilities.
- classify_source(url, domain) -> (category, label, css_badge, score_weight)
- filter_and_rank(items) -> dedup + trusted-first + recency
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Any
from urllib.parse import urlparse
import os, re, datetime as dt

INCLUDE_DOMAINS = {d.strip().lower() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_INCLUDE_DOMAINS") else []) if d.strip()}
EXCLUDE_DOMAINS = {d.strip().lower() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_EXCLUDE_DOMAINS") else []) if d.strip()}

TRUST_RULES = [
    (re.compile(r"\.(gov|bund|gob)\."), ("gov","Behörde","badge-gov", 6.0)),
    (re.compile(r"(europa\.eu|ec\.europa\.eu)"), ("eu","EU","badge-eu", 6.0)),
    (re.compile(r"(bmwk\.de|bmbf\.de|kfw\.de|dlr\.de|ihk\.de|foerderdatenbank\.de)"), ("gov","Behörde","badge-gov", 5.5)),
    (re.compile(r"(heise\.de|golem\.de|t3n\.de|handelsblatt\.com|faz\.net)"), ("media","Fachpresse","badge-media", 3.0)),
    (re.compile(r"(github\.com|docs\.)"), ("docs","Dokumentation","badge-docs", 2.0)),
]

def _domain_of(url: str, domain_hint: str | None = None) -> str:
    if domain_hint:
        return domain_hint.lower()
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def classify_source(url: str, domain_hint: str | None = None) -> Tuple[str,str,str,float]:
    dom = _domain_of(url, domain_hint)
    for pat, tup in TRUST_RULES:
        if pat.search(dom):
            return tup
    if dom.endswith(".de"):
        return ("de","Deutschland","badge-de",1.0)
    if dom:
        return ("web","Web","badge-web",0.5)
    return ("unk","Unbekannt","badge-unk",0.1)

def _score(item: Dict[str,Any]) -> float:
    url = (item.get("url") or "")
    dom = (item.get("domain") or _domain_of(url))
    cat, _, _, w = classify_source(url, dom)
    weight = w
    # Include/Exclude
    if INCLUDE_DOMAINS and dom:
        if any(dom.endswith(x) or x in dom for x in INCLUDE_DOMAINS):
            weight += 3.0
        else:
            weight -= 2.0
    if EXCLUDE_DOMAINS and dom and any(x in dom for x in EXCLUDE_DOMAINS):
        weight -= 10.0
    # Recency bonus
    when = (item.get("date") or item.get("published_date") or "")[:10]
    try:
        ts = dt.datetime.strptime(when, "%Y-%m-%d").timestamp()
        age_days = (dt.datetime.utcnow().timestamp() - ts)/86400.0
        if age_days < 8: weight += 1.0
        elif age_days < 31: weight += 0.5
    except Exception:
        pass
    return weight

def filter_and_rank(items: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    if not items: return []
    out, seen = [], set()
    for it in items:
        url = (it.get("url") or "").split("#")[0]
        if not url or url in seen: 
            continue
        dom = it.get("domain") or _domain_of(url)
        if EXCLUDE_DOMAINS and any(x in dom for x in EXCLUDE_DOMAINS):
            continue
        it["domain"] = dom
        seen.add(url)
        out.append(it)
    out.sort(key=_score, reverse=True)
    return out
