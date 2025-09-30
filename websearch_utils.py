# websearch_utils.py — Live Updates via Tavily (Gold-Standard+)
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
from typing import Any, Dict, List, Optional

import httpx

LOG = os.getenv("LOG_LEVEL", "INFO").upper() != "ERROR"
CACHE_PATH = os.getenv("TAVILY_CACHE_FILE", "/tmp/tavily_cache.json")
CACHE_TTL = int(os.getenv("TAVILY_CACHE_TTL", "21600"))  # Sekunden (default 6h)

def _now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def _domain(url: str) -> str:
    try:
        return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    except Exception:
        return ""

def _read_cache() -> Dict[str, Any]:
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _write_cache(data: Dict[str, Any]) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def _cache_get(key: str) -> Optional[Any]:
    data = _read_cache()
    v = data.get(key)
    if not v:
        return None
    ts = v.get("_ts", 0)
    if (dt.datetime.utcnow().timestamp() - ts) > CACHE_TTL:
        return None
    return v.get("payload")

def _cache_set(key: str, payload: Any) -> None:
    data = _read_cache()
    data[key] = {"_ts": dt.datetime.utcnow().timestamp(), "payload": payload}
    _write_cache(data)

def _tv_search(query: str, days: int, max_results: int, include_domains: List[str], exclude_domains: List[str]) -> List[Dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.getenv("SEARCH_DEPTH", "basic"),
        "include_domains": include_domains or None,
        "exclude_domains": exclude_domains or None,
        "max_results": max_results,
        "time_range": f"d{max(1, days)}",
    }
    try:
        with httpx.Client(timeout=20) as cli:
            r = cli.post("https://api.tavily.com/search", json=payload)
            if r.status_code != 200:
                return []
            data = r.json()
            return data.get("results", []) or []
    except Exception:
        return []

def _cards(items: List[Dict[str, Any]], title_de: str, title_en: str, lang: str) -> str:
    if not items:
        return ""
    title = title_de if lang.startswith("de") else title_en
    rows = []
    for it in items:
        url = it.get("url") or it.get("link") or ""
        t = html.escape(it.get("title") or it.get("name") or _domain(url))
        s = html.escape(it.get("content") or it.get("snippet") or "")
        dom = _domain(url)
        date = it.get("published_date") or it.get("date") or ""
        if date:
            date = html.escape(str(date)[:10])
        a = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{t}</a>'
        meta = f"{date} · {dom}" if date else dom
        rows.append(f'<div class="live-card"><div class="live-title">{a}</div><div class="live-meta">{meta}</div><div class="live-snippet">{s}</div></div>')
    return f'<div class="live-group"><div class="live-title-group">{title}</div>{"".join(rows)}</div>'

def collect_recent_items(ctx: Dict[str, Any], lang: str = "de") -> Dict[str, str]:
    """
    Liefert HTML-Blöcke: news_html, tools_rich_html, funding_rich_html, funding_deadlines_html
    Gesteuert über ENV:
      - SEARCH_DAYS, SEARCH_DAYS_TOOLS, SEARCH_DAYS_FUNDING
      - SEARCH_MAX_RESULTS, LIVE_NEWS_MAX, LIVE_ITEM_MAXLEN
      - SEARCH_INCLUDE_DOMAINS, SEARCH_EXCLUDE_DOMAINS
      - SHOW_TOOLS_NEWS, SHOW_FUNDING_STATUS, SHOW_FUNDING_DEADLINES
    """
    days = int(os.getenv("SEARCH_DAYS", "14"))
    days_tools = int(os.getenv("SEARCH_DAYS_TOOLS", os.getenv("SEARCH_DAYS_TOOLS", "30")))
    days_funding = int(os.getenv("SEARCH_DAYS_FUNDING", "30"))
    max_results = int(os.getenv("SEARCH_MAX_RESULTS", "7"))
    live_max = int(os.getenv("LIVE_NEWS_MAX", "5"))
    include_domains = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS", "")).split(",") if d.strip()]
    exclude_domains = [d.strip() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS", "")).split(",") if d.strip()]

    out: Dict[str, str] = {}
    company_topic = ctx.get("branche") or ctx.get("hauptleistung") or "KI Mittelstand"

    # --- News
    if os.getenv("SHOW_REGWATCH", "1") in {"1", "true", "yes"}:
        key = f"news:{company_topic}:{days}:{max_results}"
        news = _cache_get(key)
        if news is None:
            news = _tv_search(f"{company_topic} KI News", days, max_results, include_domains, exclude_domains)[:live_max]
            _cache_set(key, news)
        out["news_html"] = _cards(news, "Aktuelle Meldungen", "Recent updates", lang)

    # --- Tools
    if os.getenv("SHOW_TOOLS_NEWS", "1") in {"1", "true", "yes"}:
        key = f"tools:{company_topic}:{days_tools}:{max_results}"
        tools = _cache_get(key)
        if tools is None:
            tools = _tv_search(f"new AI tools {company_topic}", days_tools, max_results, include_domains, exclude_domains)[:live_max]
            _cache_set(key, tools)
        out["tools_rich_html"] = _cards(tools, "Neue Tools & Releases", "New tools & releases", lang)

    # --- Funding
    if os.getenv("SHOW_FUNDING_STATUS", "1") in {"1", "true", "yes"}:
        key = f"funding:{company_topic}:{days_funding}:{max_results}"
        fund = _cache_get(key)
        if fund is None:
            fund = _tv_search(f"{company_topic} funding grants Germany", days_funding, max_results, include_domains, exclude_domains)[:live_max]
            _cache_set(key, fund)
        out["funding_rich_html"] = _cards(fund, "Förderprogramme & Ausschreibungen", "Funding & grants", lang)

    # --- Deadlines (optional separater Query)
    if os.getenv("SHOW_FUNDING_DEADLINES", "1") in {"1", "true", "yes"}:
        key = f"deadlines:{company_topic}:{days_funding}:{max_results}"
        dls = _cache_get(key)
        if dls is None:
            dls = _tv_search(f"{company_topic} grant deadline Germany", days_funding, max_results, include_domains, exclude_domains)[:live_max]
            _cache_set(key, dls)
        out["funding_deadlines_html"] = _cards(dls, "Fristen & Deadlines", "Deadlines", lang)

    return out
