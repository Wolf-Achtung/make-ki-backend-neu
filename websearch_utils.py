# websearch_utils.py
import os
import httpx
from typing import List, Dict, Optional

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def tavily_search(query: str, days: int = 90, max_results: int = 5,
                  include_domains: Optional[list] = None, exclude_domains: Optional[list] = None,
                  depth: str = "basic") -> List[Dict]:
    if not TAVILY_API_KEY:
        return []
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": depth,     # "basic" | "advanced"
        "max_results": max_results,
        "days": days,
        "include_domains": [d for d in (include_domains or []) if d],
        "exclude_domains": [d for d in (exclude_domains or []) if d],
    }
    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
        out = []
        for it in data.get("results", []):
            out.append({
                "title": it.get("title"),
                "url": it.get("url"),
                "snippet": it.get("content") or it.get("snippet") or "",
                "source": it.get("source") or "",
                "date": it.get("published_date") or it.get("date") or "",
            })
        return out
    except Exception:
        return []

def serpapi_search(query: str, max_results: int = 5) -> List[Dict]:
    if not SERPAPI_KEY:
        return []
    try:
        params = {"engine":"google","q":query,"num":max_results,"api_key":SERPAPI_KEY}
        with httpx.Client(timeout=20.0) as c:
            r = c.get("https://serpapi.com/search.json", params=params)
            r.raise_for_status()
            data = r.json()
        out = []
        for n in (data.get("news_results") or []):
            out.append({"title": n.get("title"), "url": n.get("link"), "snippet": n.get("snippet"),
                        "source": n.get("source"), "date": n.get("date")})
        if not out:
            for o in (data.get("organic_results") or [])[:max_results]:
                out.append({"title": o.get("title"), "url": o.get("link"), "snippet": o.get("snippet"),
                            "source": "Google", "date": ""})
        return out
    except Exception:
        return []

def live_snippets(query: str, days: int = 90, max_results: int = 5,
                  include_domains: Optional[list] = None, exclude_domains: Optional[list] = None,
                  depth: str = "basic") -> List[Dict]:
    # Tavily zuerst
    t = tavily_search(query, days=days, max_results=max_results,
                      include_domains=include_domains, exclude_domains=exclude_domains, depth=depth)
    if t:
        return t[:max_results]
    # Fallback SerpAPI
    s = serpapi_search(query, max_results=max_results)
    return s[:max_results]
