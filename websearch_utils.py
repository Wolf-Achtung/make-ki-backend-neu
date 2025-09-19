# websearch_utils.py — HF-FINAL 2025-09-19
from __future__ import annotations
import os, time, logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlencode
import httpx

log = logging.getLogger("websearch")
TAVILY_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
SERPAPI_KEY = (os.getenv("SERPAPI_KEY") or "").strip()

# Simple TTL cache
_CACHE: Dict[Tuple, Tuple[float, List[Dict[str, Any]]]] = {}
_TTL = int(os.getenv("WEBSEARCH_TTL", "3600"))

def _cache_get(key: Tuple) -> Optional[List[Dict[str, Any]]]:
    now = time.time()
    item = _CACHE.get(key)
    if not item:
        return None
    ts, val = item
    if now - ts > _TTL:
        _CACHE.pop(key, None)
        return None
    return val

def _cache_set(key: Tuple, val: List[Dict[str, Any]]):
    _CACHE[key] = (time.time(), val)

def _normalize_links(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in items or []:
        out.append({
            "title": it.get("title") or it.get("name") or "",
            "url": it.get("url") or it.get("link") or "",
            "snippet": it.get("snippet") or it.get("content") or it.get("description") or "",
            "date": it.get("published_date") or it.get("date") or "",
            "source": it.get("source") or it.get("domain") or "",
        })
    # dedupe by url
    seen = set()
    uniq = []
    for x in out:
        u = x["url"]
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(x)
    return uniq

def _tavily_search(query: str, lang: str, num: int, recency_days: int) -> List[Dict[str, Any]]:
    if not TAVILY_KEY:
        raise RuntimeError("TAVILY_API_KEY missing")
    payload = {
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "include_domains": None,
        "max_results": num,
        "days": recency_days
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TAVILY_KEY}"}
    r = httpx.post("https://api.tavily.com/search", json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    return _normalize_links(data.get("results", []))

def _serpapi_search(query: str, lang: str, num: int, recency_days: int) -> List[Dict[str, Any]]:
    if not SERPAPI_KEY:
        return []
    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "hl": "de" if lang.startswith("de") else "en",
        "gl": "de" if lang.startswith("de") else "us",
        "tbs": "qdr:m",  # last month
        "api_key": SERPAPI_KEY,
    }
    url = f"https://serpapi.com/search.json?{urlencode(params)}"
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    items = []
    for it in (data.get("organic_results") or []):
        items.append({
            "title": it.get("title"),
            "url": it.get("link"),
            "snippet": it.get("snippet"),
            "date": it.get("date"),
            "source": it.get("source"),
        })
    return _normalize_links(items)

def search_links(query: str, lang: str = "de", num: int = 5, recency_days: int = 31) -> List[Dict[str, Any]]:
    """Tavily-first, SerpAPI fallback. Stable signature used by gpt_analyze."""
    key = ("v2", query.strip(), lang[:2], num, recency_days)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        items = _tavily_search(query, lang, num, recency_days)
    except Exception as e:
        log.warning("tavily failed: %s", e)
        try:
            items = _serpapi_search(query, lang, num, recency_days)
        except Exception as e2:
            log.error("serpapi fallback failed: %s", e2)
            items = []
    items = items[:num]
    _cache_set(key, items)
    return items

def live_query_for(ctx: Dict[str, Any], lang: str = "de") -> str:
    meta = (ctx or {}).get("meta", {})
    industry = meta.get("industry") or meta.get("branche") or ""
    size = (meta.get("company_size") or meta.get("unternehmensgroesse") or "").lower()
    product = meta.get("main_product") or meta.get("hauptleistung") or ""
    country = meta.get("hq_country") or "de" if lang.startswith("de") else "us"

    # kompakte Query für Tools & Förderung, gefiltert nach Branche × Größe × Hauptleistung
    if lang.startswith("de"):
        return f"""{industry} {product} Mittelstand {size} 
(„KI Förderung“ OR „Zuschuss KI“ OR „Förderprogramm KI“ OR „KI Tool“ OR „KI Software“)
site:.de"""
    else:
        return f"""{industry} {product} SME {size} 
("AI grant" OR "AI subsidy" OR "AI program" OR "AI tool" OR "AI software")"""

def render_live_box_html(title: str, links: List[Dict[str, Any]], lang: str = "de") -> str:
    if not links:
        return ""
    lab = "Neu seit" if lang.startswith("de") else "New since"
    html = [f'<section class="live-box"><h3>{lab} {title.split()[-2]} {title.split()[-1]}</h3><ul>']
    for it in links:
        t = (it.get("title") or "").strip()
        u = (it.get("url") or "").strip()
        s = (it.get("snippet") or "").strip()
        d = (it.get("date") or "").strip()
        src = (it.get("source") or "").strip()
        meta = " · ".join([x for x in (d, src) if x])
        html.append(f'<li><a href="{u}">{t}</a><div class="meta">{meta}</div><p>{s}</p></li>')
    html.append("</ul></section>")
    return "\n".join(html)
