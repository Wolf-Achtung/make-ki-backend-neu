# websearch_utils.py — Tavily-first with TTL cache (2025-09-18 HF3)
from __future__ import annotations
import os, time, json, hashlib
from typing import List, Dict, Any, Optional
import httpx
from urllib.parse import quote_plus

TAVILY_API_KEY = (os.getenv("TAVILY_API_KEY") or "").strip()
SERPAPI_KEY    = (os.getenv("SERPAPI_KEY") or "").strip()

SEARCH_DAYS        = int(os.getenv("SEARCH_DAYS", "14"))
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "5"))
SEARCH_DEPTH       = os.getenv("SEARCH_DEPTH", "basic")   # "basic" | "advanced"
INCLUDE = [s.strip() for s in os.getenv("SEARCH_INCLUDE_DOMAINS", "").split(",") if s.strip()]
EXCLUDE = [s.strip() for s in os.getenv("SEARCH_EXCLUDE_DOMAINS", "").split(",") if s.strip()]

# -------- TTL Cache ----------
_CACHE: Dict[str, Dict[str, Any]] = {}
_DEFAULT_TTL = int(os.getenv("REPORT_CACHE_TTL_SECONDS", "3600"))

def _cache_key(prefix: str, payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",",":"))
    return prefix + ":" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _cache_get(key: str, ttl: int) -> Optional[Any]:
    ent = _CACHE.get(key)
    if not ent: return None
    if (time.time() - ent["ts"]) > ttl:
        try: del _CACHE[key]
        except Exception: pass
        return None
    return ent["data"]

def _cache_set(key: str, data: Any) -> None:
    _CACHE[key] = {"ts": time.time(), "data": data}

# -------- Helpers ----------
def live_query_for(industry: str, company_size: str, main_service: str, lang: str="de") -> str:
    industry = (industry or "").strip() or "Branche"
    company_size = (company_size or "").strip() or ""
    main_service = (main_service or "").strip()
    if (lang or "de").lower().startswith("de"):
        # Förder/Tool-News komprimiert
        core = f"{industry} {main_service or ''} {company_size}".strip()
        return (f"{core} (Förderung KI OR Zuschuss KI OR Programm KI OR Tool KI OR Software KI)")
    else:
        core = f"{industry} {main_service or ''} {company_size}".strip()
        return (f"{core} (AI funding OR grant OR program OR AI tool OR software)")

def _normalize_links(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in items or []:
        url = it.get("url") or it.get("link") or ""
        if not url: continue
        title = it.get("title") or it.get("name") or it.get("source") or url
        date  = it.get("published_date") or it.get("date") or ""
        source = it.get("source") or it.get("site") or ""
        out.append({"title": title, "url": url, "date": date, "source": source})
    # de-dup
    seen = set(); deduped = []
    for it in out:
        k = it["url"].split("#")[0]
        if k in seen: continue
        seen.add(k); deduped.append(it)
    return deduped[:SEARCH_MAX_RESULTS]

# -------- Search (Tavily first; SerpAPI fallback) ----------
async def search_links(
    query: str,
    *,
    days: int = SEARCH_DAYS,
    max_results: int = SEARCH_MAX_RESULTS,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    lang: str = "de",          # <— akzeptiert, auch wenn Tavily es nicht direkt nutzt
    ttl_seconds: int = _DEFAULT_TTL
) -> List[Dict[str, Any]]:
    include_domains = include_domains or INCLUDE
    exclude_domains = exclude_domains or EXCLUDE

    key = _cache_key("links", {
        "q": query, "d": days, "m": max_results, "inc": include_domains, "exc": exclude_domains, "lang": lang
    })
    cached = _cache_get(key, ttl_seconds)
    if cached is not None:
        return cached

    links: List[Dict[str, Any]] = []

    # 1) Tavily
    try:
        if TAVILY_API_KEY:
            payload = {
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": SEARCH_DEPTH,
                "max_results": max_results,
                "include_domains": include_domains or None,
                "exclude_domains": exclude_domains or None,
                "time_range": f"{days}d",   # z.B. "14d"
            }
            to = httpx.Timeout(10.0, connect=10.0)
            async with httpx.AsyncClient(timeout=to) as c:
                r = await c.post("https://api.tavily.com/search", json=payload)
                r.raise_for_status()
                data = r.json() or {}
                results = data.get("results") or []
                links = _normalize_links(results)
    except Exception as e:
        # still try fallback
        pass

    # 2) SerpAPI fallback
    try:
        if not links and SERPAPI_KEY:
            tbs = "qdr:m" if days > 7 else "qdr:w"
            q = quote_plus(query)
            hl = "de" if (lang or "de").startswith("de") else "en"
            gl = "de" if hl == "de" else "us"
            # Optional domain filter via Google query
            f_inc = " ".join([f"site:{d}" for d in (include_domains or [])])
            f_exc = " ".join([f"-site:{d}" for d in (exclude_domains or [])])
            full_q = " ".join([q, quote_plus(f_inc), quote_plus(f_exc)]).strip()
            params = f"engine=google&q={full_q}&num={max_results}&hl={hl}&gl={gl}&tbs={tbs}&api_key={SERPAPI_KEY}"
            url = f"https://serpapi.com/search.json?{params}"
            to = httpx.Timeout(10.0, connect=10.0)
            async with httpx.AsyncClient(timeout=to) as c:
                r = await c.get(url)
                r.raise_for_status()
                data = r.json() or {}
                org = data.get("organic_results") or []
                links = _normalize_links(org)
    except Exception:
        pass

    _cache_set(key, links)
    return links

# -------- Render HTML box ----------
def render_live_box_html(title: str, links: List[Dict[str, Any]], *, lang: str = "de") -> str:
    if not links:
        if (lang or "de").startswith("de"):
            return f'<div class="live-box"><div class="live-title">{title}</div><div class="live-item">Keine neuen Meldungen gefunden.</div></div>'
        return f'<div class="live-box"><div class="live-title">{title}</div><div class="live-item">No recent items found.</div></div>'
    items = []
    for it in links:
        meta = " · ".join([p for p in [it.get("source","").strip(), it.get("date","").strip()] if p])
        items.append(
            f'<div class="live-item"><a href="{it["url"]}">{it["title"]}</a>'
            + (f'<div class="live-meta">{meta}</div>' if meta else "") +
            '</div>'
        )
    return f'<div class="live-box"><div class="live-title">{title}</div>' + "\n".join(items) + "</div>"
