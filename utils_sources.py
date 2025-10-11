# filename: utils_sources.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple
import re
from urllib.parse import urlparse

def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlparse(url)
        netloc = parts.netloc.lower()
        path = re.sub(r"/+", "/", parts.path or "/")
        return f"{parts.scheme}://{netloc}{path}".rstrip("/")
    except Exception:
        return url.strip()

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def dedupe_items(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        url = normalize_url(it.get("url") or "")
        dom = it.get("domain") or get_domain(url)
        title = (it.get("title") or it.get("name") or it.get("url") or "").strip().lower()
        key = (dom, title) if title else (dom, url)
        if key in seen:
            continue
        seen.add(key)
        it["url"] = url
        it["domain"] = dom
        out.append(it)
    return out
