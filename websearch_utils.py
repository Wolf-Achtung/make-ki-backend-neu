
"""
websearch_utils.py — unified web search helper for KI-Status-Report (Railway)
-----------------------------------------------------------------------------
- Primary provider: Tavily (https://docs.tavily.com) via tavily-python
- Optional fallback: SerpAPI (if SERPAPI_API_KEY is set)
- Graceful no-op when neither API key is available

Env vars (recommended defaults shown):
  TAVILY_API_KEY=tvly-...
  SEARCH_PROVIDER=tavily               # tavily | serpapi | auto
  SEARCH_TOPIC=news                    # news | general | finance
  SEARCH_DAYS=14                       # only used for topic=news
  SEARCH_MAX_RESULTS=5
  SEARCH_DEPTH=basic                   # basic (1 credit) | advanced (2 credits)
  SEARCH_COUNTRY=germany               # only used for topic=general (Tavily)
  SEARCH_INCLUDE_DOMAINS=             # comma-separated allow list
  SEARCH_EXCLUDE_DOMAINS=             # comma-separated block list

Returned shape:
  List[{"title": str, "url": str, "snippet": str}]
"""
from __future__ import annotations
import os, time, json, logging
from typing import List, Dict, Any, Optional, Tuple

log = logging.getLogger("websearch")

# ------------------------------- tiny TTL cache -------------------------------
_CACHE: Dict[Tuple, Tuple[float, Any]] = {}
def _cache_get(key: Tuple, ttl_s: int) -> Optional[Any]:
    now = time.time()
    item = _CACHE.get(key)
    if not item:
        return None
    ts, val = item
    if now - ts > ttl_s:
        _CACHE.pop(key, None)
        return None
    return val

def _cache_set(key: Tuple, val: Any) -> None:
    _CACHE[key] = (time.time(), val)

def _csv_env(name: str) -> Optional[List[str]]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return [tok.strip() for tok in raw.split(",") if tok.strip()]

# ------------------------------- providers ------------------------------------
def _tavily_available() -> bool:
    return bool(os.getenv("TAVILY_API_KEY"))

def _serpapi_available() -> bool:
    return bool(os.getenv("SERPAPI_API_KEY"))

def _tavily_search(query: str,
                   topic: Optional[str] = None,
                   days: Optional[int] = None,
                   max_results: int = 5,
                   depth: str = "basic",
                   country: Optional[str] = None,
                   include_domains: Optional[List[str]] = None,
                   exclude_domains: Optional[List[str]] = None) -> List[Dict[str, str]]:
    try:
        from tavily import TavilyClient  # type: ignore
    except Exception as e:
        log.warning("tavily-python not installed: %s", e)
        return []
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    payload: Dict[str, Any] = {
        "query": query,
        "search_depth": depth if depth in ("basic", "advanced") else "basic",
        "max_results": int(max_results or 5),
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_favicon": False,
        "auto_parameters": False,
    }
    tpc = (topic or os.getenv("SEARCH_TOPIC", "news")).lower()
    if tpc in {"news", "general", "finance"}:
        payload["topic"] = tpc
    # Tavily: days only for topic=news
    if tpc == "news":
        try:
            payload["days"] = int(days or int(os.getenv("SEARCH_DAYS", "14")))
        except Exception:
            payload["days"] = 14
    # country only works for topic=general
    if tpc == "general" and country:
        payload["country"] = country
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains
    try:
        res = client.search(**payload)  # returns dict
    except Exception as e:
        log.warning("Tavily error: %s", e)
        return []
    results = []
    for item in res.get("results", []):
        title = item.get("title") or ""
        url = item.get("url") or ""
        snippet = item.get("content") or item.get("raw_content") or ""
        if title and url:
            results.append({"title": title.strip(), "url": url.strip(), "snippet": (snippet or "").strip()})
    return results

def _serpapi_search(query: str,
                    max_results: int = 5,
                    include_domains: Optional[List[str]] = None,
                    exclude_domains: Optional[List[str]] = None) -> List[Dict[str, str]]:
    # Lightweight SerpAPI wrapper (web search). Requires SERPAPI_API_KEY.
    # We keep it intentionally minimal; filter by include/exclude domains post-hoc.
    try:
        import httpx  # type: ignore
    except Exception as e:
        log.warning("httpx not available for SerpAPI: %s", e)
        return []
    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        return []
    params = {
        "engine": "google",
        "q": query,
        "api_key": key,
        "num": int(max_results or 5)
    }
    try:
        r = httpx.get("https://serpapi.com/search", params=params, timeout=20)
        data = r.json()
    except Exception as e:
        log.warning("SerpAPI error: %s", e)
        return []
    out: List[Dict[str, str]] = []
    for item in (data.get("organic_results") or []):
        title = item.get("title") or ""
        url = item.get("link") or ""
        snippet = item.get("snippet") or ""
        if title and url:
            out.append({"title": title, "url": url, "snippet": snippet})
    # Domain filters
    def _host(u: str) -> str:
        try:
            from urllib.parse import urlparse
            return urlparse(u).netloc.lower()
        except Exception:
            return ""
    inc = set((d.lower() for d in (include_domains or [])))
    exc = set((d.lower() for d in (exclude_domains or [])))
    if inc:
        out = [it for it in out if any(h in _host(it["url"]) for h in inc)]
    if exc:
        out = [it for it in out if not any(h in _host(it["url"]) for h in exc)]
    return out[:max_results]

# ------------------------------ public facade ---------------------------------
def search_links(query: str,
                 num_results: int = 5,
                 topic: Optional[str] = None,
                 days: Optional[int] = None,
                 depth: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Unified entry point.
    - Chooses provider based on SEARCH_PROVIDER (tavily|serpapi|auto)
    - Applies lightweight TTL cache (60s) to avoid duplicate queries during one report run
    - Applies include/exclude domain filters from env
    """
    provider = (os.getenv("SEARCH_PROVIDER", "auto") or "auto").lower()
    topic = (topic or os.getenv("SEARCH_TOPIC", "news")).lower()
    depth = (depth or os.getenv("SEARCH_DEPTH", "basic")).lower()
    country = os.getenv("SEARCH_COUNTRY", "germany")
    include_domains = _csv_env("SEARCH_INCLUDE_DOMAINS")
    exclude_domains = _csv_env("SEARCH_EXCLUDE_DOMAINS")
    try:
        n = int(num_results or int(os.getenv("SEARCH_MAX_RESULTS", "5")))
    except Exception:
        n = 5
    try:
        d = int(days or int(os.getenv("SEARCH_DAYS", "14")))
    except Exception:
        d = 14
    key = ("v1", provider, query.strip(), topic, d, n, depth, tuple(include_domains or []), tuple(exclude_domains or []))
    cached = _cache_get(key, ttl_s=60)
    if cached is not None:
        return cached
    # Provider selection
    if provider == "tavily" or (provider == "auto" and _tavily_available()):
        out = _tavily_search(query=query,
                             topic=topic,
                             days=d,
                             max_results=n,
                             depth=depth,
                             country=country,
                             include_domains=include_domains,
                             exclude_domains=exclude_domains)
    elif provider == "serpapi" or (provider == "auto" and _serpapi_available()):
        out = _serpapi_search(query=query,
                              max_results=n,
                              include_domains=include_domains,
                              exclude_domains=exclude_domains)
    else:
        # No provider available → no-op
        out = []
    _cache_set(key, out)
    return out

# Backwards-compat alias for legacy imports
serpapi_search = search_links
