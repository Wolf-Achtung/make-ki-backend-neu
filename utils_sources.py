# utils_sources.py — Source classification & ranking (Gold-Standard+)
# PEP8-compliant; no external deps.
from __future__ import annotations
from typing import Dict, List, Tuple, Any
from urllib.parse import urlparse
import re
import time
import os

GOV_DOMAINS = {
    "europa.eu","bund.de","bmwk.de","bmbf.de","kfw.de","dlr.de","l-bank.de","nrwbank.de",
    "foerderdatenbank.de","ihk.de","berlin.de","ibb.de"
}
MEDIA_DOMAINS = {"heise.de","golem.de","t3n.de","handelsblatt.com","faz.net","zeit.de","tagesschau.de"}
EDU_TLD = (".edu",".ac.","uni-",".fh-",".hs-",".ox.ac.uk",".cam.ac.uk",".ethz.ch",".tum.de")
ORG_TLD = (".org",)
VENDOR_HINTS = ("pricing","product","features","signup","docs","status","changelog","roadmap")
BADGE_MAP = {
    "gov": ("Öffentlich / Amtlich", "badge-gov", 1.00),
    "edu": ("Wissenschaft", "badge-edu", 0.95),
    "media": ("Fachpresse", "badge-media", 0.85),
    "org": ("Organisation", "badge-org", 0.80),
    "vendor": ("Anbieter", "badge-vendor", 0.65),
    "other": ("Web", "badge-web", 0.60),
}

def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        # strip 'www.'
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""

def classify_source(url: str, domain: str | None = None) -> Tuple[str,str,str,float]:
    """Return (category, label, css_badge, trust_weight)."""
    dom = (domain or _domain(url) or "").lower()

    # Government / public sector
    if any(dom.endswith(g) for g in GOV_DOMAINS):
        lab, css, w = BADGE_MAP["gov"]; return ("gov", lab, css, w)
    # Academic (.edu, .ac.*, uni-...)
    if dom.endswith(".edu") or any(x in dom for x in EDU_TLD):
        lab, css, w = BADGE_MAP["edu"]; return ("edu", lab, css, w)
    # Media
    if any(dom.endswith(m) for m in MEDIA_DOMAINS):
        lab, css, w = BADGE_MAP["media"]; return ("media", lab, css, w)
    # Non-profit / org
    if dom.endswith(".org"):
        lab, css, w = BADGE_MAP["org"]; return ("org", lab, css, w)
    # Vendor / product
    path = urlparse(url).path.lower()
    if any(h in path for h in VENDOR_HINTS):
        lab, css, w = BADGE_MAP["vendor"]; return ("vendor", lab, css, w)
    # Default
    lab, css, w = BADGE_MAP["other"]; return ("other", lab, css, w)

def _parse_date(s: str | None) -> int:
    """Rough epoch score for recency sorting; unknown -> old."""
    if not s:
        return 0
    s = s.strip()[:10]
    # YYYY-MM-DD
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            import datetime as _dt
            return int(_dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).timestamp())
        except Exception:
            return 0
    return 0

def filter_and_rank(items: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    """Dedupe + trust/ranking with optional domain include/exclude via env:
    - SEARCH_INCLUDE_DOMAINS: comma-separated allowlist (rank boost)
    - SEARCH_EXCLUDE_DOMAINS: comma-separated blocklist
    """
    include = {d.strip().lower() for d in os.getenv("SEARCH_INCLUDE_DOMAINS","").split(",") if d.strip()}
    exclude = {d.strip().lower() for d in os.getenv("SEARCH_EXCLUDE_DOMAINS","").split(",") if d.strip()}

    dedup: Dict[str, Dict[str,Any]] = {}
    for it in items or []:
        url = (it.get("url") or "").split("#")[0].strip()
        if not url:
            continue
        dom = it.get("domain") or _domain(url)
        if dom in exclude:
            continue
        key = url
        if key not in dedup:
            cat, lab, badge, w = classify_source(url, dom)
            it["domain"] = dom
            it["_cat"] = cat
            it["_badge"] = badge
            it["_w"] = w + (0.1 if dom in include else 0.0)
            it["_ts"] = _parse_date(it.get("date"))
            dedup[key] = it
        else:
            # keep earliest/best data
            prev = dedup[key]
            if it.get("date") and not prev.get("date"):
                prev["date"] = it["date"]
    ranked = sorted(dedup.values(), key=lambda x: (x.get("_w",0), x.get("_ts",0)), reverse=True)
    # strip internals
    for r in ranked:
        for k in ["_cat","_badge","_w","_ts"]:
            r.pop(k, None)
    return ranked