# websearch_utils.py — Live-Suche (Tavily-first) + HTML-Renderer (bullet-less)
# Stand: 2025-09-29

from __future__ import annotations
import os, time, logging, html, re
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlencode
import httpx

log = logging.getLogger("websearch")

# ------------------------- ENV / Flags -------------------------
def _get_bool(name: str, default: bool=False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if v in {"1","true","yes","y","on"}: return True
    if v in {"0","false","no","n","off"}: return False
    return default

TAVILY_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
SERPAPI_KEY = (os.getenv("SERPAPI_KEY") or "").strip()
ALLOW_TAVILY = _get_bool("ALLOW_TAVILY", True)

SEARCH_DAYS_DEFAULT   = int(os.getenv("SEARCH_DAYS", "30"))
SEARCH_DAYS_FUNDING   = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
SEARCH_DAYS_TOOLS     = int(os.getenv("SEARCH_DAYS_TOOLS", "45"))
SEARCH_MAX_RESULTS    = int(os.getenv("SEARCH_MAX_RESULTS", "6"))
SEARCH_PROVIDER       = (os.getenv("SEARCH_PROVIDER") or "tavily").lower()

INCLUDE_DOMAINS = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS") or "").split(",") if d.strip()]
EXCLUDE_DOMAINS = [d.strip() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS") or "").split(",") if d.strip()]

LIVE_NEWS_MAX        = int(os.getenv("LIVE_NEWS_MAX", "4"))
LIVE_NEWS_MIN_SCORE  = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0"))
LIVE_ITEM_MAXLEN     = int(os.getenv("LIVE_ITEM_MAXLEN", "280"))
LIVE_NEWS_SANITIZE   = _get_bool("LIVE_NEWS_SANITIZE", True)

# TTL-Cache
_TTL  = int(os.getenv("TAVILY_CACHE_TTL", os.getenv("WEBSEARCH_TTL", "3600")))
_CACHE: Dict[Tuple, Tuple[float, List[Dict[str, Any]]]] = {}

# ------------------------- Helpers -------------------------
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

def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) <= n: return s
    return s[:n-1].rstrip() + "…"

def _domain_from_url(u: str) -> str:
    m = re.search(r"https?://([^/]+)/?", u or "", re.I)
    return m.group(1) if m else ""

def _pass_domain(u: str) -> bool:
    d = _domain_from_url(u)
    if INCLUDE_DOMAINS and d not in INCLUDE_DOMAINS: return False
    if EXCLUDE_DOMAINS and d in EXCLUDE_DOMAINS: return False
    return True

def _normalize_links(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in items or []:
        out.append({
            "title": it.get("title") or it.get("name") or "",
            "url": it.get("url") or it.get("link") or "",
            "snippet": it.get("snippet") or it.get("content") or it.get("description") or "",
            "date": it.get("published_date") or it.get("date") or "",
            "source": it.get("source") or it.get("domain") or _domain_from_url(it.get("url") or it.get("link") or ""),
            "score": float(it.get("score", 0) or 0),
        })
    # Dedupe
    seen = set()
    uniq = []
    for x in out:
        u = x["url"]
        if not u or u in seen: 
            continue
        if not _pass_domain(u): 
            continue
        seen.add(u)
        uniq.append(x)
    return uniq

# ------------------------- Providers -------------------------
def _tavily_search(query: str, lang: str, num: int, recency_days: int) -> List[Dict[str, Any]]:
    if not TAVILY_KEY:
        raise RuntimeError("TAVILY_API_KEY missing")
    payload = {
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "include_domains": INCLUDE_DOMAINS or None,
        "max_results": num,
        "days": recency_days,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TAVILY_KEY}"}
    r = httpx.post("https://api.tavily.com/search", json=payload, headers=headers, timeout=40)
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
        "tbs": "qdr:d" if recency_days <= 7 else "qdr:w" if recency_days <= 30 else "qdr:m",
        "api_key": SERPAPI_KEY,
    }
    url = f"https://serpapi.com/search.json?{urlencode(params)}"
    r = httpx.get(url, timeout=40)
    r.raise_for_status()
    data = r.json()
    items = []
    for it in (data.get("organic_results") or []):
        items.append({
            "title": it.get("title"),
            "url": it.get("link"),
            "snippet": it.get("snippet"),
            "date": it.get("date"),
            "source": _domain_from_url(it.get("link") or ""),
            "score": 0.0,
        })
    return _normalize_links(items)

def search_links(query: str, lang: str = "de", num: int = 5, recency_days: int = 31) -> List[Dict[str, Any]]:
    """
    Tavily-first, SerpAPI fallback. Öffentliche, stabile Signatur (wird in gpt_analyze importiert).
    """
    key = ("v3", query.strip(), lang[:2], num, recency_days, tuple(INCLUDE_DOMAINS), tuple(EXCLUDE_DOMAINS))
    cached = _cache_get(key)
    if cached is not None:
        return cached

    if not ALLOW_TAVILY and SEARCH_PROVIDER != "tavily":
        # SerpAPI-Only Mode (falls Tavily explizit aus)
        try:
            items = _serpapi_search(query, lang, num, recency_days)
        except Exception as e:
            log.error("serpapi failed: %s", e)
            items = []
        _cache_set(key, items[:num])
        return items[:num]

    try:
        items = _tavily_search(query, lang, num, recency_days)
    except Exception as e:
        log.warning("tavily failed: %s", e)
        try:
            items = _serpapi_search(query, lang, num, recency_days)
        except Exception as e2:
            log.error("serpapi fallback failed: %s", e2)
            items = []

    # Score-Filter
    if LIVE_NEWS_MIN_SCORE > 0:
        items = [x for x in items if float(x.get("score", 0) or 0) >= LIVE_NEWS_MIN_SCORE]

    items = items[:num]
    _cache_set(key, items)
    return items

# ------------------------- Query Builder -------------------------
def _norm(v: str) -> str:
    return (v or "").strip()

def _country_for(lang: str) -> str:
    return "de" if lang.startswith("de") else "en"

def queries_news(ctx: Dict[str, Any], lang: str) -> List[str]:
    branche = _norm(ctx.get("branche") or ctx.get("meta", {}).get("industry"))
    produkt = _norm(ctx.get("hauptleistung") or ctx.get("meta", {}).get("main_product"))
    land = ctx.get("meta", {}).get("hq_country") or _country_for(lang)

    if lang.startswith("de"):
        return [
            f'{branche} KI Nachrichten site:.de',
            f'{branche} {produkt} "KI" (Praxis OR Einführung) site:.de',
            f'EU AI Act {branche} Auswirkungen site:.{land}',
        ]
    else:
        return [
            f'{branche} AI news',
            f'{branche} {produkt} "AI" adoption',
            f'EU AI Act {branche} impact',
        ]

def queries_tools(ctx: Dict[str, Any], lang: str) -> List[str]:
    usecases = ctx.get("ki_usecases") or ""
    if isinstance(usecases, list): usecases = ", ".join(usecases)
    if lang.startswith("de"):
        return [
            f'bestes KI Tool {usecases} GDPR DPA',
            f'Open Source {usecases} AI self-hosted',
        ]
    else:
        return [
            f'best AI tool {usecases} GDPR DPA',
            f'open source {usecases} ai self-hosted',
        ]

def queries_funding(ctx: Dict[str, Any], lang: str) -> List[str]:
    state = _norm(ctx.get("bundesland") or "DE")
    if lang.startswith("de"):
        return [
            f'Förderprogramm Digitalisierung {state} KMU Zuschuss',
            f'Förderung KI Mittelstand {state}',
            f'EU Förderung Digitalisierung KMU {state}',
        ]
    else:
        return [
            f'AI grant {state} SME',
            f'digitalisation grant {state} SME',
            f'EU funding AI SME {state}',
        ]

# ------------------------- HTML Renderer -------------------------
def _card(item: Dict[str, Any]) -> str:
    t = html.escape(_truncate(item.get("title",""), 120))
    u = html.escape(item.get("url",""))
    s = html.escape(_truncate(item.get("snippet",""), LIVE_ITEM_MAXLEN))
    d = html.escape(item.get("date",""))
    src = html.escape(item.get("source",""))
    meta = " · ".join(x for x in (d, src) if x)
    return (
        f'<div class="info-box">'
        f'<div class="info-box-title"><a href="{u}">{t}</a></div>'
        f'<p>{s}</p>'
        f'<div class="meta" style="color:#6B7280;font-size:9pt">{meta}</div>'
        f'</div>'
    )

def render_cards_html(title: str, items: List[Dict[str, Any]], lang: str = "de") -> str:
    if not items:
        return ""
    head = f'<h2>{html.escape(title)}</h2>'
    return head + "".join(_card(it) for it in items)

# ------------------------- Orchestrator -------------------------
def collect_recent_items(ctx: Dict[str, Any], lang: str = "de") -> Dict[str,str]:
    """
    Liefert fertige HTML-Fragmente: news_html, tools_rich_html, funding_rich_html
    """
    if not ALLOW_TAVILY:
        return {}

    out: Dict[str,str] = {}
    try:
        # NEWS
        n_items: List[Dict[str, Any]] = []
        for q in queries_news(ctx, lang):
            n_items += search_links(q, lang=lang, num=SEARCH_MAX_RESULTS, recency_days=SEARCH_DAYS_DEFAULT)
        # dedupe
        seen = set(); news = []
        for it in n_items:
            if it["url"] in seen: continue
            seen.add(it["url"]); news.append(it)
        news = news[:LIVE_NEWS_MAX]
        out["news_html"] = render_cards_html("Aktuelle Meldungen" if lang.startswith("de") else "Recent Updates", news, lang)

        # TOOLS
        t_items: List[Dict[str, Any]] = []
        for q in queries_tools(ctx, lang):
            t_items += search_links(q, lang=lang, num=SEARCH_MAX_RESULTS, recency_days=SEARCH_DAYS_TOOLS)
        seen = set(); tools = []
        for it in t_items:
            if it["url"] in seen: continue
            seen.add(it["url"]); tools.append(it)
        tools = tools[:LIVE_NEWS_MAX]
        out["tools_rich_html"] = render_cards_html("Werkzeuge & Tools (Quellen)" if lang.startswith("de") else "Tools & Sources", tools, lang)

        # FUNDING
        f_items: List[Dict[str, Any]] = []
        for q in queries_funding(ctx, lang):
            f_items += search_links(q, lang=lang, num=SEARCH_MAX_RESULTS, recency_days=SEARCH_DAYS_FUNDING)
        seen = set(); funds = []
        for it in f_items:
            if it["url"] in seen: continue
            seen.add(it["url"]); funds.append(it)
        funds = funds[:LIVE_NEWS_MAX]
        out["funding_rich_html"] = render_cards_html("Förderprogramme (aktuelle Hinweise)" if lang.startswith("de") else "Funding Programs (recent)", funds, lang)

    except Exception as e:
        log.warning("collect_recent_items failed: %s", e)

    return out

__all__ = [
    "search_links",
    "queries_news", "queries_tools", "queries_funding",
    "collect_recent_items",
    "render_cards_html",
]
