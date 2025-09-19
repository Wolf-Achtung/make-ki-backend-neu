# websearch_utils.py  — Tavily-first (SerpAPI fallback) + TTL cache
from __future__ import annotations
import os, time, logging, httpx, urllib.parse
from typing import List, Dict, Optional, Tuple

log = logging.getLogger("websearch")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if not log.handlers:
    logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [websearch] %(message)s")

TAVILY_API_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
SERPAPI_KEY    = (os.getenv("SERPAPI_KEY") or "").strip()

SEARCH_DAYS        = int(os.getenv("SEARCH_DAYS", "30"))
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "5"))
SEARCH_DEPTH       = os.getenv("SEARCH_DEPTH", "basic")  # basic|advanced
SEARCH_TOPIC       = os.getenv("SEARCH_TOPIC", "") or None
INCLUDE_DOMAINS    = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS", "") or "").split(",") if d.strip()]
EXCLUDE_DOMAINS    = [d.strip() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS", "") or "").split(",") if d.strip()]

CACHE_TTL = int(os.getenv("REPORT_CACHE_TTL_SECONDS", "600"))
_CACHE: Dict[Tuple, Tuple[float, list]] = {}

def _cache_get(key: Tuple) -> Optional[list]:
    hit = _CACHE.get(key)
    if not hit: return None
    ts, data = hit
    if time.time() - ts < CACHE_TTL:
        return data
    _CACHE.pop(key, None)
    return None

def _cache_put(key: Tuple, data: list) -> None:
    _CACHE[key] = (time.time(), data)

def _norm_links(items: list) -> list:
    out = []
    for it in items or []:
        title   = it.get("title") or it.get("name") or it.get("source") or ""
        url     = it.get("url") or it.get("link") or ""
        snippet = it.get("content") or it.get("snippet") or ""
        date    = it.get("published_date") or it.get("date") or ""
        if url and title:
            out.append({"title": title.strip(), "url": url.strip(), "snippet": (snippet or "").strip(), "date": (date or "").strip()})
    return out[:SEARCH_MAX_RESULTS]

def _tavily(query: str, *, days: int, max_results: int, depth: str, topic: Optional[str],
            include_domains: Optional[list], exclude_domains: Optional[list]) -> list:
    if not TAVILY_API_KEY:
        raise RuntimeError("Tavily key missing")
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": depth if depth in ("basic","advanced") else "basic",
        "include_domains": include_domains or None,
        "exclude_domains": exclude_domains or None,
        "topic": topic,
        "days": days
    }
    with httpx.Client(timeout=30) as cx:
        r = cx.post("https://api.tavily.com/search", json=payload)
        r.raise_for_status()
        data = r.json()
    return _norm_links(data.get("results", []))

def _serpapi(query: str, *, days: int, max_results: int, lang: str) -> list:
    if not SERPAPI_KEY:
        return []
    # Zeitfilter (z. B. letzte 30 Tage): qdr:m (Monat) – wir bleiben konservativ
    tbs = "qdr:m" if days and days <= 31 else ""
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": max_results,
        "hl": "de" if lang.startswith("de") else "en",
        "gl": "de" if lang.startswith("de") else "us",
        "tbs": tbs
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    with httpx.Client(timeout=30) as cx:
        r = cx.get(url)
        r.raise_for_status()
        data = r.json()
    items = data.get("organic_results", []) or []
    return _norm_links(items)

def search_links(query: str, *, lang: str="de", days: int=SEARCH_DAYS, max_results: int=SEARCH_MAX_RESULTS,
                 depth: str=SEARCH_DEPTH, topic: Optional[str]=SEARCH_TOPIC,
                 include_domains: Optional[list]=INCLUDE_DOMAINS, exclude_domains: Optional[list]=EXCLUDE_DOMAINS,
                 **kwargs) -> list:
    """
    Tavily-first; SerpAPI fallback. Accepts extra kwargs defensively.
    Returns: list of {title, url, snippet, date}
    """
    key = ("links", query, lang, days, max_results, depth, topic, tuple(include_domains or []), tuple(exclude_domains or []))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        links = _tavily(query, days=days, max_results=max_results, depth=depth, topic=topic,
                        include_domains=include_domains, exclude_domains=exclude_domains)
    except Exception as e:
        log.warning("tavily failed: %s", e)
        links = _serpapi(query, days=days, max_results=max_results, lang=lang)
    _cache_put(key, links)
    return links

def live_query_for(ctx: dict, *, lang: str="de") -> str:
    branche = (ctx.get("branche") or ctx.get("industry") or "").strip()
    size    = (ctx.get("groesse") or ctx.get("company_size") or "").strip()
    offer   = (ctx.get("hauptleistung") or ctx.get("hauptprodukt") or ctx.get("main_offer") or "").strip()
    if lang.startswith("de"):
        base = f"{branche} {offer} Mittelstand {size}".strip()
        suffix = "(Förderung KI OR Zuschuss KI OR Programm KI OR Tool KI OR Software KI)"
        return " ".join(x for x in [base, suffix] if x)
    else:
        base = f"{branche} {offer} SME {size}".strip()
        suffix = "(grant AI OR subsidy AI OR program AI OR AI tool OR AI software)"
        return " ".join(x for x in [base, suffix] if x)

def render_live_box_html(title: str, links: List[Dict[str,str]], *, lang: str="de", accent: Optional[str]=None) -> str:
    if not links:
        return ""
    accent = accent or ("#0b5ed7" if lang.startswith("de") else "#0b5ed7")
    items = "\n".join(
        f'<li><a href="{l["url"]}" target="_blank">{l["title"]}</a>'
        + (f' <span style="opacity:.7">({l["date"]})</span>' if l.get("date") else "")
        + (f'<br><span style="opacity:.9">{l["snippet"]}</span>' if l.get("snippet") else "")
        + "</li>"
        for l in links
    )
    return f"""
    <div style="border:1px solid {accent}; border-left:6px solid {accent}; padding:12px 14px; margin:10px 0 18px 0; border-radius:6px;">
      <div style="font-weight:700; color:{accent}; margin-bottom:6px;">{title}</div>
      <ul style="margin:0; padding-left:18px;">{items}</ul>
    </div>
    """
