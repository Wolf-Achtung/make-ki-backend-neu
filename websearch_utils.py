# websearch_utils.py
# Tavily-first Websuche mit Dateisystem-TTL-Cache und SerpAPI-Fallback.
# Exportiert: search_links(..), tavily_search(..), serpapi_search(..)

from __future__ import annotations
import os, json, time, hashlib, logging
from typing import List, Dict, Any, Optional
import httpx
from urllib.parse import urlparse

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [websearch] %(message)s")
log = logging.getLogger("websearch")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
SERPAPI_KEY    = os.getenv("SERPAPI_KEY", "").strip()

SEARCH_DAYS         = int(os.getenv("SEARCH_DAYS", "14"))
SEARCH_DEPTH        = os.getenv("SEARCH_DEPTH", "basic").strip()
SEARCH_TOPIC        = os.getenv("SEARCH_TOPIC", "news").strip()
SEARCH_MAX_RESULTS  = int(os.getenv("SEARCH_MAX_RESULTS", "5"))
INCLUDE_DOMAINS     = [d.strip() for d in os.getenv("SEARCH_INCLUDE_DOMAINS", "").split(",") if d.strip()]
EXCLUDE_DOMAINS     = [d.strip() for d in os.getenv("SEARCH_EXCLUDE_DOMAINS", "").split(",") if d.strip()]

CACHE_DIR = os.getenv("SEARCH_CACHE_DIR", "/tmp/ki_cache/websearch")
CACHE_TTL = int(os.getenv("REPORT_CACHE_TTL_SECONDS", "3600"))
os.makedirs(CACHE_DIR, exist_ok=True)

HTTP_TIMEOUT = float(os.getenv("SEARCH_HTTP_TIMEOUT", "18.0"))

def _norm_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def _hash_key(parts: Dict[str, Any]) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")

def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    p = _cache_path(key)
    if not os.path.exists(p): return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if (time.time() - float(data.get("_ts", 0))) > CACHE_TTL:
            try: os.remove(p)
            except Exception: pass
            return None
        return data
    except Exception:
        return None

def _cache_set(key: str, payload: Dict[str, Any]) -> None:
    p = _cache_path(key)
    try:
        payload = dict(payload); payload["_ts"] = time.time()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as e:
        log.debug("cache write failed: %s", e)

def _days_to_tavily_range(days: int) -> str:
    if days <= 1: return "d1"
    if days <= 3: return "d3"
    if days <= 7: return "d7"
    if days <= 14: return "d14"
    if days <= 30: return "m1"
    if days <= 90: return "m3"
    return "y1"

def _dedupe(items: List[Dict[str, Any]], key: str = "url") -> List[Dict[str, Any]]:
    seen = set(); out = []
    for it in items:
        v = (it.get(key) or "").strip()
        if v and v not in seen:
            seen.add(v); out.append(it)
    return out

def _apply_domain_filters(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not INCLUDE_DOMAINS and not EXCLUDE_DOMAINS: return items
    inc = set(d.lower() for d in INCLUDE_DOMAINS)
    exc = set(d.lower() for d in EXCLUDE_DOMAINS)
    out=[]
    for it in items:
        dom = _norm_domain(it.get("url",""))
        if inc and dom not in inc: continue
        if exc and dom in exc:    continue
        out.append(it)
    return out

def _normalize(items: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
    out=[]
    for r in items:
        title = r.get("title") or r.get("name") or r.get("source") or ""
        url   = r.get("url") or r.get("link") or ""
        if not url: continue
        snip  = r.get("content") or r.get("snippet") or r.get("text") or ""
        date  = r.get("published_date") or r.get("date") or r.get("published_time") or ""
        out.append({
            "title": title.strip(),
            "url": url.strip(),
            "snippet": (snip or "").strip(),
            "date": (date or "").strip(),
            "source": source,
            "domain": _norm_domain(url),
            "score": r.get("score") or r.get("position") or None,
            "favicon": r.get("favicon") or r.get("favicon_url") or None,
        })
    return out

# --- Tavily -------------------------------------------------------------------
def tavily_search(query: str, *, days: int = SEARCH_DAYS, depth: str = SEARCH_DEPTH,
                  topic: str = SEARCH_TOPIC, max_results: int = SEARCH_MAX_RESULTS,
                  include_domains: Optional[List[str]] = None,
                  exclude_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    body = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": depth,
        "topic": topic,
        "time_range": _days_to_tavily_range(days),
        "include_answer": False,
        "include_images": False,
        "include_results": True,
    }
    if include_domains: body["include_domains"] = include_domains
    if exclude_domains: body["exclude_domains"] = exclude_domains

    key = _hash_key({"eng":"tavily","q":query,"d":days,"k":max_results,"depth":depth,"topic":topic,"inc":include_domains,"exc":exclude_domains})
    cached = _cache_get(key)
    if cached: return _apply_domain_filters(_dedupe(_normalize(cached.get("results",[]),"tavily")))

    timeout = httpx.Timeout(connect=HTTP_TIMEOUT, read=HTTP_TIMEOUT, write=HTTP_TIMEOUT, pool=HTTP_TIMEOUT)
    with httpx.Client(http2=True, timeout=timeout) as c:
        r = c.post("https://api.tavily.com/search", json=body)
        r.raise_for_status()
        data = r.json() or {}

    _cache_set(key, {"results": data.get("results", [])})
    return _apply_domain_filters(_dedupe(_normalize(data.get("results", []),"tavily")))

# --- SerpAPI ------------------------------------------------------------------
def serpapi_search(query: str, *, days: int = SEARCH_DAYS, max_results: int = SEARCH_MAX_RESULTS,
                   include_domains: Optional[List[str]] = None, exclude_domains: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if not SERPAPI_KEY:
        return []
    params = {"engine":"google","q":query,"api_key":SERPAPI_KEY,"num":max_results,"hl":"de","gl":"de"}
    timeout = httpx.Timeout(connect=HTTP_TIMEOUT, read=HTTP_TIMEOUT, write=HTTP_TIMEOUT, pool=HTTP_TIMEOUT)
    with httpx.Client(http2=True, timeout=timeout) as c:
        r = c.get("https://serpapi.com/search.json", params=params)
        r.raise_for_status()
        data = r.json() or {}
    org = data.get("organic_results") or []
    slim = [{"title":x.get("title"),"url":x.get("link"),"snippet":x.get("snippet"),"date":x.get("date")} for x in org][:max_results]
    return _apply_domain_filters(_dedupe(_normalize(slim,"serpapi")))

# --- Unified facade -----------------------------------------------------------
def search_links(query: str, *, days: int = SEARCH_DAYS, max_results: int = SEARCH_MAX_RESULTS,
                 prefer: str = "tavily", include_domains: Optional[List[str]] = None,
                 exclude_domains: Optional[List[str]] = None, depth: str = SEARCH_DEPTH,
                 topic: str = SEARCH_TOPIC) -> List[Dict[str, Any]]:
    """
    Unified entry: Tavily-first, SerpAPI fallback. With TTL cache and domain filters.
    """
    # Cache key (in-memory + fs)
    key = _hash_key({"v":"1", "q":query, "days":days, "max":max_results, "prefer":prefer, "inc":include_domains, "exc":exclude_domains, "depth":depth, "topic":topic})
    fs = _cache_get(key)
    if fs is not None:
        return fs.get("items", [])

    items: List[Dict[str, Any]] = []
    if prefer == "tavily" and TAVILY_API_KEY:
        try:
            items = tavily_search(query, days=days, depth=depth, topic=topic,
                                  max_results=max_results, include_domains=include_domains, exclude_domains=exclude_domains)
        except Exception as e:
            log.warning("tavily failed: %s", e)
    if len(items) < max_results and SERPAPI_KEY:
        try:
            items.extend(serpapi_search(query, days=days, max_results=max_results,
                                        include_domains=include_domains, exclude_domains=exclude_domains))
        except Exception as e:
            log.warning("serpapi failed: %s", e)
    items = _apply_domain_filters(_dedupe(items))[:max_results]
    _cache_set(key, {"items": items})
    return items
