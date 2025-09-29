# websearch_utils.py — Live Updates (News/Tools/Funding) via Tavily, robust & cachebar
# PEP8, Logging, Fail-Soft. Stand: 2025-09-29

from __future__ import annotations

import hashlib
import html
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

__all__ = ["collect_recent_items"]

# --------------------- Konfiguration per ENV ---------------------
# ALLOW_TAVILY            -> steuert Aktivierung (true/false)
# TAVILY_API_KEY          -> Tavily API Key
# SEARCH_TOPIC            -> optionales globales Topic (z.B. "GenAI", überschreibt Auto-Topic)
# SEARCH_DAYS             -> News-Recency (Default 60)
# SEARCH_DAYS_TOOLS       -> Tools-Recency (Default 45)
# SEARCH_DAYS_FUNDING     -> Funding-Recency (Default 60)
# SEARCH_MAX_RESULTS      -> Max. Ergebnisse pro Query (Default 6)
# SEARCH_INCLUDE_DOMAINS  -> CSV-Liste erlaubter Domains
# SEARCH_EXCLUDE_DOMAINS  -> CSV-Liste auszuschließender Domains
# LIVE_NEWS_MAX           -> Top-N Erzähl-Items (Default 5)
# LIVE_ITEM_MAXLEN        -> max. Textlänge pro Item (Default 560)
# LIVE_NEWS_MIN_SCORE     -> Minimaler Score-Filter (Default 0.0)
# LIVE_NEWS_SANITIZE      -> HTML-Sanitizing erzwingen (Default true)
# SHOW_TOOLS_NEWS         -> Tools-News aktivieren (true)
# SHOW_FUNDING_DEADLINES  -> Fördersummen/Fristen erwähnen (true)
# SHOW_FUNDING_STATUS     -> Status "laufend/geschlossen" erwähnen (true)

# --------------------- interner Cache ----------------------------
@dataclass
class CacheItem:
    ts: float
    data: Any


_CACHE: Dict[str, CacheItem] = {}


def _env_bool(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _now() -> float:
    return time.time()


def _cache_get(key: str, ttl: int) -> Optional[Any]:
    itm = _CACHE.get(key)
    if not itm:
        return None
    if _now() - itm.ts > ttl:
        return None
    return itm.data


def _cache_set(key: str, data: Any) -> None:
    _CACHE[key] = CacheItem(ts=_now(), data=data)


class TavilyClient:
    """Sehr robuste Tavily‑Abfrage mit Fail‑Soft und vereinheitlichten Feldern."""

    def __init__(self, api_key: str, timeout: float = 14.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str, *, topic: str = "news", max_results: int = 6) -> List[Dict[str, Any]]:
        url = "https://api.tavily.com/search"
        # Tavily akzeptiert api_key im JSON-Body; einige Deployments setzen zusätzlich einen Authorization-Header.
        payload = {
            "api_key": self.api_key,
            "query": query,
            "topic": topic,
            "search_depth": "basic",
            "include_answer": False,
            "max_results": int(max_results),
        }
        headers = {"Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
        except Exception:
            return []

        items = []
        for it in data.get("results", []):
            items.append(
                {
                    "title": it.get("title") or it.get("url"),
                    "url": it.get("url"),
                    "content": it.get("content") or it.get("snippet") or "",
                    "score": float(it.get("score") or 0.0),
                    "published": it.get("published_date") or "",
                }
            )
        return items


def _topic_auto(ctx: Dict[str, Any], lang: str) -> str:
    if os.getenv("SEARCH_TOPIC"):
        return os.getenv("SEARCH_TOPIC")  # type: ignore[return-value]
    branche = (ctx.get("branche") or "business").strip()
    if lang.startswith("de"):
        return f"KI {branche} Deutschland EU Unternehmen"
    return f"AI {branche} Europe business"


def _filter_domains(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    inc = {d.strip().lower() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS") or "").split(",") if d.strip()}
    exc = {d.strip().lower() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS") or "").split(",") if d.strip()}
    if inc:
        items = [x for x in items if any(h in (x.get("url") or "").lower() for h in inc)]
    if exc:
        items = [x for x in items if not any(h in (x.get("url") or "").lower() for h in exc)]
    return items


def _shorten(t: str, n: int) -> str:
    t = (t or "").strip()
    if len(t) <= n:
        return t
    return t[: max(0, n - 1)].rstrip() + "…"


def _as_p(txt: str) -> str:
    return f"<p>{html.escape(txt, quote=False)}</p>"


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", "ignore"))
    return h.hexdigest()


def _render_items_as_paragraphs(items: List[Dict[str, Any]], lang: str, maxlen: int) -> str:
    """Narrative Absätze, keine Listen/Nummern."""
    out: List[str] = []
    for it in items:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        content = _shorten(it.get("content") or "", maxlen)
        if lang.startswith("de"):
            s = f"{title}: {content} Mehr unter {url}"
        else:
            s = f"{title}: {content} Learn more: {url}"
        out.append(_as_p(s))
    return "".join(out)


def collect_recent_items(ctx: Dict[str, Any], *, lang: str = "de") -> Dict[str, Any]:
    """
    Holt knappe Live-Updates für News, Tools und Förderungen und gibt narrative
    HTML-Blöcke zurück (news_html / tools_rich_html / funding_rich_html).
    """
    if not _env_bool("ALLOW_TAVILY", True):
        return {}

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {}
    tav = TavilyClient(api_key)

    # Settings
    days_news = int(os.getenv("SEARCH_DAYS", "60"))
    days_tools = int(os.getenv("SEARCH_DAYS_TOOLS", "45"))
    days_funding = int(os.getenv("SEARCH_DAYS_FUNDING", "60"))
    max_results = int(os.getenv("SEARCH_MAX_RESULTS", "6"))
    top_n = int(os.getenv("LIVE_NEWS_MAX", "5"))
    maxlen = int(os.getenv("LIVE_ITEM_MAXLEN", "560"))
    min_score = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0.0"))
    show_tools = _env_bool("SHOW_TOOLS_NEWS", True)
    show_funding = True  # Funding wird in den Reports stark nachgefragt

    topic = _topic_auto(ctx, lang)

    def _do(query: str) -> List[Dict[str, Any]]:
        key = _hash(query, str(max_results))
        ttl = int(os.getenv("TAVILY_CACHE_TTL", "1800"))
        cached = _cache_get(key, ttl)
        if cached is not None:
            return cached
        res = _filter_domains(tav.search(query, topic="news", max_results=max_results))
        if min_score > 0:
            res = [x for x in res if float(x.get("score") or 0.0) >= min_score]
        _cache_set(key, res)
        return res

    # News
    q_news = f"{topic} last {days_news} days"
    news_items = _do(q_news)[:top_n]
    news_html = _render_items_as_paragraphs(news_items, lang, maxlen) if news_items else ""

    # Tools
    tools_html = ""
    if show_tools:
        q_tools = f"{topic} AI tool launch privacy EU last {days_tools} days"
        tool_items = _do(q_tools)[: max(2, min(4, top_n))]
        tools_html = _render_items_as_paragraphs(tool_items, lang, maxlen) if tool_items else ""

    # Funding
    funding_html = ""
    if show_funding:
        region = (ctx.get("bundesland") or "DE").upper()
        if lang.startswith("de"):
            q_funding = f"Förderprogramm Digitalisierung {region} Frist last {days_funding} days"
        else:
            q_funding = f"funding program digitization {region} deadline last {days_funding} days"
        funding_items = _do(q_funding)[: max(2, min(4, top_n))]
        funding_html = _render_items_as_paragraphs(funding_items, lang, maxlen) if funding_items else ""

    out: Dict[str, Any] = {}
    if news_html:
        out["news_html"] = news_html
    if tools_html:
        out["tools_rich_html"] = tools_html
    if funding_html:
        out["funding_rich_html"] = funding_html
    return out
