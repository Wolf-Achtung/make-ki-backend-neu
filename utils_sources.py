# utils_sources.py
# -*- coding: utf-8 -*-
"""
Source classification & ranking utilities (Gold-Standard+)
- classify_source(url, domain) -> (category, label, css_badge, weight)
- filter_and_rank(items) -> normalized + deduped + ranked list
Items schema tolerated:
  {title, url, domain?, date?, score?}
"""
from __future__ import annotations
from urllib.parse import urlparse
from typing import Dict, Any, List, Tuple
import re

TRUST_WEIGHTS = {
    "gov": 1.00,
    "eu": 0.98,
    "edu": 0.95,
    "org": 0.93,
    "news": 0.90,
    "vendor": 0.85,
    "blog": 0.80,
    "other": 0.70,
}

BADGE_CSS = {
    "gov": "badge--gov",
    "eu": "badge--eu",
    "edu": "badge--edu",
    "org": "badge--org",
    "news": "badge--news",
    "vendor": "badge--vendor",
    "blog": "badge--blog",
    "other": "badge--other",
}

def _netloc(url_or_domain: str) -> str:
    s = (url_or_domain or "").strip()
    if not s:
        return ""
    if "://" in s:
        try:
            return urlparse(s).netloc.lower()
        except Exception:
            return ""
    return s.lower()

def classify_source(url: str, domain: str | None = None) -> Tuple[str, str, str, float]:
    """
    Heuristics for trust class.
    Returns: (category, human_label, css_badge, weight)
    """
    dom = _netloc(domain or url)
    if not dom:
        return ("other", "Quelle", BADGE_CSS["other"], TRUST_WEIGHTS["other"])

    # EU/government
    if dom.endswith(".eu") or dom.endswith(".europa.eu") or any(part in dom for part in ["ec.europa.eu", "europa.eu"]):
        return ("eu", "EU‑Quelle", BADGE_CSS["eu"], TRUST_WEIGHTS["eu"])
    if re.search(r"\.(gov|gv\.at|admin\.ch)$", dom) or dom.endswith(".bund.de") or "bmwk.de" in dom or "bmbf.de" in dom or "nrwbank.de" in dom:
        return ("gov", "Behörde", BADGE_CSS["gov"], TRUST_WEIGHTS["gov"])

    # Academia / org / news / vendor / blogs
    if dom.endswith(".edu") or ".uni-" in dom or dom.startswith("uni-") or ".ac." in dom:
        return ("edu", "Hochschule", BADGE_CSS["edu"], TRUST_WEIGHTS["edu"])
    if dom.endswith(".org"):
        return ("org", "Organisation", BADGE_CSS["org"], TRUST_WEIGHTS["org"])
    if any(k in dom for k in ["heise.de", "golem.de", "t3n.de", "wired.com", "theverge.com", "ft.com", "handelsblatt.com"]):
        return ("news", "Fachpresse", BADGE_CSS["news"], TRUST_WEIGHTS["news"])
    if any(k in dom for k in ["aws.amazon.com","azure.microsoft.com","microsoft.com","openai.com","anthropic.com","google.com","deepmind.com","mistral.ai","aleph-alpha.com"]):
        return ("vendor", "Anbieter", BADGE_CSS["vendor"], TRUST_WEIGHTS["vendor"])
    if any(k in dom for k in ["medium.com","substack.com","dev.to","hashnode.com","github.io"]):
        return ("blog", "Blog", BADGE_CSS["blog"], TRUST_WEIGHTS["blog"])

    return ("other", "Quelle", BADGE_CSS["other"], TRUST_WEIGHTS["other"])

def _norm_item(it: Dict[str, Any]) -> Dict[str, Any]:
    url = (it.get("url") or "").strip()
    title = (it.get("title") or it.get("name") or url) or ""
    domain = (it.get("domain") or _netloc(url)) or ""
    date = (it.get("date") or it.get("published_date") or it.get("last_updated") or "")[:10]
    out = {"title": title, "url": url, "domain": domain, "date": date}
    # compute weight
    cat, _, _, w = classify_source(url, domain)
    score = float(it.get("score") or 0.0)
    out["_rank"] = (w * 100.0) + score
    out["_cat"] = cat
    return out

def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        url = (it.get("url") or "").split("#")[0]
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(it)
    return out

def filter_and_rank(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
    normed = [_norm_item(x) for x in items if x]
    normed = _dedupe(normed)
    normed.sort(key=lambda x: x.get("_rank", 0.0), reverse=True)
    # strip internals
    for x in normed:
        x.pop("_rank", None); x.pop("_cat", None)
    return normed
