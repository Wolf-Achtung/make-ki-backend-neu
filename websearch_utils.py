"""
websearch_utils.py — Tavily‑first (SerpAPI Fallback) + simple TTL cache
Exposed helpers:
  - search_links(query, topic=None, days=None, max_results=None, include_domains=None, exclude_domains=None, lang="de", country="de")
  - live_query_for(ctx: dict, lang: str) -> str
  - render_live_box_html(title: str, links: list[dict], lang: str = "de") -> str
"""
from __future__ import annotations
import os, time, logging, httpx
from typing import Any, Dict, List, Optional, Tuple

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [websearch] %(message)s")
log = logging.getLogger("websearch")

# Environment
TAVILY_API_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
SERPAPI_KEY    = (os.getenv("SERPAPI_KEY") or "").strip()
SEARCH_DAYS    = int(os.getenv("SEARCH_DAYS", "14"))
SEARCH_DEPTH   = (os.getenv("SEARCH_DEPTH", "basic") or "basic").lower()  # "basic" | "advanced"
SEARCH_MAX     = int(os.getenv("SEARCH_MAX_RESULTS", "5"))
INC_DOMAINS    = [s.strip() for s in (os.getenv("SEARCH_INCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_INCLUDE_DOMAINS") else []) if s.strip()]
EXC_DOMAINS    = [s.strip() for s in (os.getenv("SEARCH_EXCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_EXCLUDE_DOMAINS") else []) if s.strip()]

# Simple in‑memory TTL cache
_CACHE : Dict[Tuple[Any, ...], Tuple[float, List[Dict[str,Any]]]] = {}
_TTL   = int(os.getenv("REPORT_CACHE_TTL_SECONDS", "1800"))  # default 30 min

def _now() -> float:
    return time.time()

def _ckey(**kw) -> Tuple[Any, ...]:
    parts = tuple(sorted(kw.items()))
    return parts

def _cache_get(key):
    try:
        ts, data = _CACHE.get(key, (0, []))
        if (_now() - ts) < _TTL and data:
            return data
    except Exception:
        pass
    return None

def _cache_set(key, data):
    try:
        _CACHE[key] = (_now(), data)
    except Exception:
        pass

# -------------------- providers --------------------
def _tavily(query: str, *, topic: Optional[str], days: int, max_results: int,
            include: Optional[List[str]], exclude: Optional[List[str]], lang: str, country: str) -> List[Dict[str,Any]]:
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY missing")
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": SEARCH_DEPTH,
        "max_results": max_results,
        "include_domains": include or [],
        "exclude_domains": exclude or [],
        "days": days,
        "topic": topic or "news",
        "include_answer": False,
        "include_raw_content": False,
    }
    # Tavily does not support lang/country directly in all plans, but keep for symmetry
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json() or {}
    except Exception as e:
        log.warning("tavily failed: %s", e)
        raise

    results = []
    for item in (data.get("results") or []):
        results.append({
            "title": item.get("title") or item.get("query") or "—",
            "url": item.get("url") or "",
            "source": item.get("source") or "",
            "date": item.get("published_date") or item.get("timestamp") or "",
            "snippet": item.get("content") or item.get("snippet") or "",
        })
        if len(results) >= max_results:
            break
    return results

def _serpapi(query: str, *, days: int, max_results: int, lang: str, country: str) -> List[Dict[str,Any]]:
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY missing")
    params = {
        "engine": "google",
        "q": query,
        "num": max_results,
        "api_key": SERPAPI_KEY,
        "hl": "de" if lang.startswith("de") else "en",
        "gl": "de" if country.lower() in ("de","germany") else "us",
    }
    # recency: last month by default
    params["tbs"] = "qdr:m" if days and days <= 31 else ""

    with httpx.Client(timeout=20.0) as client:
        r = client.get("https://serpapi.com/search.json", params=params)
        r.raise_for_status()
        data = r.json() or {}

    results = []
    for item in (data.get("news_results") or data.get("organic_results") or []):
        results.append({
            "title": item.get("title") or "—",
            "url": item.get("link") or item.get("url") or "",
            "source": item.get("source") or item.get("displayed_link") or "",
            "date": item.get("date") or "",
            "snippet": item.get("snippet") or item.get("content") or "",
        })
        if len(results) >= max_results:
            break
    return results

# ---------------- public helpers -------------------
def search_links(query: str, *, topic: Optional[str] = None, days: Optional[int] = None,
                 max_results: Optional[int] = None, include_domains: Optional[List[str]] = None,
                 exclude_domains: Optional[List[str]] = None, lang: str = "de", country: str = "de") -> List[Dict[str,Any]]:
    """Returns a list[dict] with keys: title, url, source, date, snippet.
    Tries Tavily first; on failure or empty result, falls back to SerpAPI.
    Results are cached (TTL). The function accepts a 'lang' keyword argument
    to keep the call signature stable for callers.
    """
    q = (query or "").strip()
    if not q:
        return []

    d = int(days or SEARCH_DAYS or 14)
    k = int(max_results or SEARCH_MAX or 5)
    inc = include_domains if include_domains is not None else INC_DOMAINS
    exc = exclude_domains if exclude_domains is not None else EXC_DOMAINS

    key = _ckey(provider="mixed", q=q, topic=topic or "", d=d, k=k, inc=tuple(inc), exc=tuple(exc), lang=lang, country=country)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    results: List[Dict[str,Any]] = []
    # Tavily first
    try:
        results = _tavily(q, topic=topic, days=d, max_results=k, include=inc, exclude=exc, lang=lang, country=country)
    except Exception:
        results = []
    # Fallback to SerpAPI if needed
    if not results:
        try:
            results = _serpapi(q, days=d, max_results=k, lang=lang, country=country)
        except Exception as e:
            log.warning("serpapi failed: %s", e)
            results = []

    _cache_set(key, results)
    return results

def live_query_for(ctx: Dict[str,Any], lang: str = "de") -> str:
    """Build a sector-aware query from context dict (industry, size, primary_product, location)."""
    industry = (ctx.get("industry") or "").strip()
    size     = (ctx.get("size") or "").strip()
    product  = (ctx.get("primary_product") or ctx.get("hauptleistung") or "").strip()
    loc      = (ctx.get("location") or "").strip()

    if lang.startswith("de"):
        base = "Förderung KI OR Zuschuss KI OR Programm KI OR Tool KI OR Software KI"
        terms = " ".join([industry, product, size, loc]).strip()
        q = f"{terms} ({base})".strip()
        q = f"{q} site:de"
    else:
        base = "funding AI OR grant AI OR program AI OR tool AI OR software AI"
        terms = " ".join([industry, product, size, loc]).strip()
        q = f"{terms} ({base})".strip()
    return q

def render_live_box_html(title: str, links: List[Dict[str,Any]], lang: str = "de") -> str:
    if not links:
        return ""
    cap = title or ("Neu seit {month}" if lang.startswith("de") else "New since {month}")
    items = []
    for it in links:
        t  = (it.get("title") or "—").strip()
        u  = (it.get("url") or "#").strip()
        s  = (it.get("source") or "").strip()
        d  = (it.get("date") or "").strip()
        meta = " · ".join([p for p in [s, d] if p])
        items.append(f'<li><a href="{u}">{t}</a>' + (f' <span class="meta">{meta}</span>' if meta else '') + '</li>')
    html = f"""
    <div class="live-box">
      <div class="live-title">{cap}</div>
      <ul class="live-list">
        {''.join(items)}
      </ul>
    </div>
    """
    return html