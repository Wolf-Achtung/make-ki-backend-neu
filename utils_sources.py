# filename: utils_sources.py
# -*- coding: utf-8 -*-
"""
Source classification & ranking utilities for Live‑Layer.
- classify_source(url, domain) -> (category, label, css_badge, weight)
- filter_and_rank(items) -> de‑duplicated, trust‑weighted, recency‑aware list
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

TRUST_MAP: Dict[str, Tuple[str, str, str, int]] = {
    # domain : (category, label, css_badge, weight)
    # Officials / public sector / banks
    "europa.eu": ("official", "EU", "badge-official", 90),
    "ec.europa.eu": ("official", "EU", "badge-official", 90),
    "foerderdatenbank.de": ("official", "Bund", "badge-official", 85),
    "bmwk.de": ("official", "BMWK", "badge-official", 85),
    "bmbf.de": ("official", "BMBF", "badge-official", 85),
    "dlr.de": ("official", "DLR", "badge-official", 80),
    "kfw.de": ("official", "KfW", "badge-official", 85),
    "l-bank.de": ("official", "L‑Bank", "badge-official", 78),
    "nrwbank.de": ("official", "NRW.BANK", "badge-official", 78),
    "ihk.de": ("official", "IHK", "badge-official", 75),
    "berlin.de": ("official", "Land Berlin", "badge-official", 78),
    "ibb.de": ("official", "IBB", "badge-official", 78),
    # Tech/press
    "heise.de": ("news", "Heise", "badge-news", 70),
    "golem.de": ("news", "Golem", "badge-news", 68),
    "t3n.de": ("news", "t3n", "badge-news", 65),
}

CAT_FALLBACKS = [
    (r"(^|\.)uni\.", ("research", "Uni", "badge-research", 60)),
    (r"(^|\.)(fh|hs)-", ("research", "Hochschule", "badge-research", 58)),
    (r"(^|\.)(gov|gouv|gob)\.", ("official", "Regierung", "badge-official", 80)),
]

def _domain_from_url(url: str) -> str:
    try:
        return re.split(r"/+", url.split("://", 1)[-1])[0].lower()
    except Exception:
        return ""

def classify_source(url: str, domain: str | None = None) -> Tuple[str, str, str, int]:
    """Return (category, label, css_badge, weight)."""
    dom = (domain or _domain_from_url(url)).lower()
    if dom in TRUST_MAP:
        return TRUST_MAP[dom]
    for pat, tpl in CAT_FALLBACKS:
        if re.search(pat, dom):
            return tpl
    if dom.endswith(".de") or dom.endswith(".eu"):
        return ("vendor", "DE/EU", "badge-vendor", 50)
    return ("unknown", "Web", "badge-unknown", 40)

def _parse_date(d: str | None) -> datetime | None:
    if not d:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(d[:len(fmt)], fmt)
        except Exception:
            continue
    return None

def filter_and_rank(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedupe + rank by trust, recency and optional score."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items or []:
        url = (it.get("url") or "").split("#")[0].strip()
        if not url or url in seen:
            continue
        seen.add(url)
        dom = it.get("domain") or _domain_from_url(url)
        cat, label, badge, weight = classify_source(url, dom)
        when = _parse_date(it.get("date") or it.get("published_date"))
        score = float(it.get("score") or 0.0)
        rank = weight + score
        if when:
            # Favor recent items
            delta_days = (datetime.utcnow() - when).days
            rank += max(0, 60 - min(delta_days, 60)) * 0.5
        it.update({"domain": dom, "category": cat, "badge_label": label, "badge": badge, "_rank": rank})
        out.append(it)
    out.sort(key=lambda x: x.get("_rank", 0), reverse=True)
    return out
