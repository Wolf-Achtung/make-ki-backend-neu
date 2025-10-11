# filename: utils_sources.py
# -*- coding: utf-8 -*-
"""
Utilities for handling live sources (Gold-Standard+)
- dedupe_items: de-duplicate by URL (sans query) or title
- parse_domain: extract domain from URL
- classify_source: assign category + badge + trust score
- filter_and_rank: apply include/exclude filters and rank sources by trust/date

Environment (optional):
  SEARCH_INCLUDE_DOMAINS  : comma-separated whitelist of domains/substrings
  SEARCH_EXCLUDE_DOMAINS  : comma-separated blacklist of domains/substrings
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple
from datetime import datetime
import os

__all__ = [
    "parse_domain",
    "dedupe_items",
    "classify_source",
    "filter_and_rank",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_csv_env(name: str) -> List[str]:
    raw = os.getenv(name, "") or ""
    out: List[str] = []
    for part in raw.split(","):
        p = part.strip().lower()
        if p:
            out.append(p)
    return out

INCLUDES = _split_csv_env("SEARCH_INCLUDE_DOMAINS")
EXCLUDES = _split_csv_env("SEARCH_EXCLUDE_DOMAINS")


def parse_domain(url: str) -> str:
    """Extract host part from URL."""
    if not url:
        return ""
    u = url.strip()
    if "://" in u:
        u = u.split("://", 1)[1]
    u = u.split("/", 1)[0]
    return u.lower()


def dedupe_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """De-duplicate by canonicalized URL (without query) or title."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items or []:
        url = (it.get("url") or "").split("?")[0].strip().lower()
        title = (it.get("title") or "").strip().lower()
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        if not it.get("domain"):
            it["domain"] = parse_domain(it.get("url") or "")
        out.append(it)
    return out

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

EU_DOMAINS = {"europa.eu", "ec.europa.eu"}
FEDERAL_DE = {"bmwk.de", "bmwi.de", "bmbf.de", "bafin.de", "bund.de", "foerderdatenbank.de"}
STATE_BANKS = {"l-bank.de", "nrwbank.de", "ibb.de", "nbank.de", "isb.rlp.de",
               "investitionsbank.sachsen-anhalt.de", "wtsh.de", "aufbaubank-thueringen.de"}
CHAMBERS = {"ihk.de", "hwk.de"}
ACADEMIC_HINTS = {"uni-", "fh-", "tu-", ".uni-", ".fh.", ".hs-", ".htw-", ".tum.de", "dlr.de", "dfki.de", "fraunhofer.de", "mpg.de"}
MEDIA_HINTS = {"heise.de", "golem.de", "t3n.de", "handelsblatt.com", "faz.net", "sueddeutsche.de", "zeit.de"}
VENDOR_HINTS = {"openai.com", "microsoft.com", "google.com", "aws.amazon.com", "oracle.com", "ibm.com",
                "sap.com", "notion.so", "zapier.com", "n8n.io", "deepl.com", "aleph-alpha.com"}


def classify_source(url: str, domain: Optional[str] = None) -> Tuple[str, str, str, int]:
    """
    Classify a source into a coarse trust category.
    Returns: (category, label, css_badge_class, trust_score[0..100])
    """
    d = (domain or parse_domain(url)).lower()

    if not d:
        return ("unknown", "Quelle", "badge--muted", 30)

    if d in EU_DOMAINS or d.endswith(".eu"):
        return ("eu", "EU", "badge--eu", 95)

    if d in FEDERAL_DE or d.endswith(".bund.de"):
        return ("gov", "Bund", "badge--gov", 92)

    if any(d.endswith(s) for s in STATE_BANKS) or ("bank" in d and d.endswith(".de")):
        return ("funding", "Förderbank", "badge--funding", 88)

    if any(d.endswith(s) for s in CHAMBERS):
        return ("chamber", "IHK/HWK", "badge--gov", 84)

    if any(h in d for h in ACADEMIC_HINTS) or d.endswith(".edu") or d.endswith(".ac.uk"):
        return ("academic", "Forschung", "badge--academic", 82)

    if any(h in d for h in MEDIA_HINTS):
        return ("media", "Fachpresse", "badge--media", 78)

    if any(h in d for h in VENDOR_HINTS):
        return ("vendor", "Anbieter", "badge--vendor", 70)

    if d.endswith(".gov") or ".gov." in d:
        return ("gov", "Gov", "badge--gov", 90)

    if d.endswith(".org"):
        return ("ngo", "Verband/NGO", "badge--ngo", 65)

    if d.endswith(".io") or d.endswith(".dev") or d.endswith(".me") or "blog" in d:
        return ("blog", "Blog/Agentur", "badge--blog", 55)

    trust = 60 if d.endswith(".de") else 55
    return ("web", "Web", "badge--muted", trust)


def _parse_date(s: str) -> datetime:
    if not s:
        return datetime.min
    ss = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(ss[:len(fmt)], fmt)
        except Exception:
            continue
    return datetime.min


def filter_and_rank(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply INCLUDE/EXCLUDE filters and rank by (trust desc, date desc).
    Items are enriched with classification fields.
    """
    out: List[Dict[str, Any]] = []
    for it in items or []:
        url = (it.get("url") or "")
        dom = (it.get("domain") or parse_domain(url)).lower()

        # Exclude by blacklist
        if EXCLUDES and any(dom.endswith(x) or x in dom for x in EXCLUDES):
            continue

        # If whitelist present: include only if matched
        if INCLUDES and not any(dom.endswith(x) or x in dom for x in INCLUDES):
            continue

        cat, label, badge, trust = classify_source(url, dom)
        it["domain"] = dom
        it["source_category"] = cat
        it["source_label"] = label
        it["source_badge"] = badge
        it["source_trust"] = trust
        out.append(it)

    out = dedupe_items(out)
    out.sort(key=lambda x: (int(x.get("source_trust") or 0), _parse_date(x.get("date") or "")), reverse=True)
    return out
