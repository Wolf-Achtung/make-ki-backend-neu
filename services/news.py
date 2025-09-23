from typing import List, Optional, Dict, Any
from loguru import logger
from services.config import settings

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

def fetch_news(company: Optional[str], industry: Optional[str], language: str) -> List[Dict[str, Any]]:
    """
    Fetch latest news via Tavily API. If API key missing or httpx not available,
    returns empty list. We keep it language-aware.
    """
    if not settings.TAVILY_API_KEY:
        return []
    if httpx is None:
        logger.warning("httpx not available; cannot reach Tavily")
        return []

    q_parts = []
    if company:
        q_parts.append(company)
    if industry:
        q_parts.append(industry)
    q_parts.append("KI OR AI news")
    query = " ".join(q_parts)

    lang = "de" if language.lower().startswith("de") else "en"

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "advanced",
                    "include_raw_content": False,
                    "max_results": 5,
                    "include_answer": False
                },
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            # Normalize
            news_items = []
            for r in results:
                news_items.append({
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("content") or r.get("snippet")
                })
            return news_items
    except Exception as e:
        logger.error(f"Tavily error: {e}")
        return []
