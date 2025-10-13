# filename: websearch_utils_ext.py
# -*- coding: utf-8 -*-
"""
Optional live enrichment hook for the tool matrix.

Implements `hybrid_lookup(name: str)`:
- Prefers an existing in-project hybrid search if present (websearch_utils.search_hybrid).
- Otherwise falls back to **Tavily** (stable REST API) using TAVILY_API_KEY.
- Parses "trust center", "security", "compliance", "DPA" pages for surface-level signals.

Returned keys:
    saml_scim: "yes"/"no"/"unknown"
    dpa_url:   first credible DPA or data-processing link (or "")
    audit_export: "yes"/"no"/"unknown"

This is intentionally conservative: if nothing is found, returns {} to avoid
overwriting curated baseline values.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List
import httpx

KEYWORDS = {
    "saml_scim": ["saml", "scim", "single sign-on", "single sign on", "sso", "okta", "azure ad"],
    "dpa": ["data processing agreement", "dpa", "auftragsverarbeitung", "av-vertrag", "avv", "data processing addendum"],
    "audit_export": ["audit log export", "audit logs export", "siem", "splunk", "csv export", "export audit"],
}

def _prefer_hybrid(name: str) -> Dict[str, str]:
    try:
        from websearch_utils import search_hybrid  # type: ignore
        docs = search_hybrid(f"{name} trust center security compliance dpa saml scim")  # project-provided
        return _parse_docs(docs or [])
    except Exception:
        return {}

def _tavily_search(q: str, include_domains: List[str], max_results: int, timeout: float) -> List[Dict]:
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return []
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    body = {
        "query": q,
        "search_depth": "basic",
        "include_domains": include_domains or None,
        "max_results": max_results,
        "include_answer": False,
        "include_images": False,
    }
    url = "https://api.tavily.com/search"
    try:
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(url, json=body, headers=headers)
            if r.status_code == 200:
                data = r.json() or {}
                return data.get("results") or []
    except Exception:
        return []
    return []

def _parse_docs(docs: List[Dict]) -> Dict[str, str]:
    text_blobs = []
    candidate_links = []
    for d in docs:
        # Tavily shape: {title, url, content} ; Hybrid likely similar
        txt = " ".join([str(d.get("title") or ""), str(d.get("content") or "")])
        url = str(d.get("url") or "")
        text_blobs.append(txt.lower())
        if any(k in (txt.lower() + " " + url.lower()) for k in KEYWORDS["dpa"]):
            candidate_links.append(url)
    combined = " ".join(text_blobs)

    def found_any(words: List[str]) -> bool:
        low = combined
        return any(w in low for w in words)

    result = {}
    if found_any(KEYWORDS["saml_scim"]):
        result["saml_scim"] = "yes"
    if candidate_links:
        # prefer vendor subpages containing 'dpa' or 'auftragsverarbeitung'
        candidate_links.sort(key=lambda u: (("dpa" in u.lower() or "auftrags" in u.lower()), len(u)), reverse=True)
        result["dpa_url"] = candidate_links[0]
    if found_any(KEYWORDS["audit_export"]):
        result["audit_export"] = "yes"
    return result

def hybrid_lookup(name: str) -> Dict[str, str]:
    # try project-provided hybrid first
    ext = _prefer_hybrid(name)
    if ext:
        return ext

    include_domains = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS","").split(",")) if d.strip()]
    max_results = int(os.getenv("SEARCH_MAX_RESULTS", "8"))
    timeout = float(os.getenv("LIVE_TIMEOUT_S", "8.0"))
    q = f'{name} trust center security compliance "data processing" dpa saml scim "audit logs"'
    docs = _tavily_search(q, include_domains=include_domains, max_results=max_results, timeout=timeout)
    if not docs:
        return {}
    return _parse_docs(docs)
