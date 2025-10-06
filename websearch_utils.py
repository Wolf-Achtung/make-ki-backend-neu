# File: websearch_utils.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import datetime as dt, logging, os, re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import httpx

log = logging.getLogger("websearch_utils")
if not log.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "").strip()
LIVE_TIMEOUT_S = float(os.getenv("LIVE_TIMEOUT_S", "8.0"))
LIVE_PRIMARY_DAYS = int(os.getenv("LIVE_NEWS_DAYS", "7"))
LIVE_FALLBACK_MAX_DAYS = int(os.getenv("LIVE_FALLBACK_MAX_DAYS", "30"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "5"))

TRUST_WEIGHT = {"foerderdatenbank.de":1.00,"bafa.de":0.95,"bund.de":0.95,"bmwk.de":0.90,
                "berlin.de":0.95,"ibb.de":0.95,"heise.de":0.85,"golem.de":0.80,"t3n.de":0.75,
                "handelsblatt.com":0.80,"wired.com":0.70,"theverge.com":0.65,"nextcloud.com":0.85,
                "matomo.org":0.85,"jitsi.org":0.75,"odoo.com":0.75,"huggingface.co":0.75,"github.com":0.70}

EU_TLDS = (".de",".eu",".fr",".nl",".it",".es",".se",".fi",".dk",".pl",".at",".be",".ie",".pt",".gr",".cz",".sk",".hu",".lt",".lv",".ee",".ro",".bg",".hr",".si",".lu",".mt",".cy")

def _client() -> httpx.Client:
    return httpx.Client(timeout=LIVE_TIMEOUT_S, follow_redirects=True)

def _trim_url(u: str) -> str:
    try:
        p = urlparse(u); q = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        clean = p._replace(query=urlencode(q), fragment="")
        path = re.sub(r"/{2,}", "/", clean.path or "/"); clean = clean._replace(path=path.rstrip("/") or "/")
        return urlunparse(clean)
    except Exception:
        return u

def _domain(u: str) -> str:
    try: return urlparse(u).netloc.lower()
    except Exception: return ""

def _today_iso() -> str: return dt.datetime.now().strftime("%Y-%m-%d")
def _days_to_range(days: int) -> str: return "d7" if days <= 7 else "d30"

def _parse_date(s: Optional[str]) -> str:
    if not s: return _today_iso()
    try: return dt.datetime.fromisoformat(s.replace("Z","+00:00")).date().isoformat()
    except Exception:
        for fmt in ("%Y-%m-%d","%d.%m.%Y","%Y/%m/%d"):
            try: return dt.datetime.strptime(s[:10], fmt).date().isoformat()
            except Exception: pass
    return _today_iso()

def _tavily_search(query: str, days: int, max_results: int = 6) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY: return []
    payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced",
               "time_range": _days_to_range(days), "max_results": max(1, min(10, max_results)),
               "include_answer": False, "include_raw_content": False}
    try:
        with _client() as client:
            r = client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json() or {}
            out: List[Dict[str, Any]] = []
            for item in data.get("results", []) or []:
                out.append({"title": (item.get("title") or "").strip() or (item.get("url") or ""),
                            "url": _trim_url(item.get("url") or ""),
                            "source": _domain(item.get("url") or ""),
                            "date": _parse_date(item.get("published_date")),
                            "snippet": (item.get("content") or "")[:300],
                            "engine": "tavily"})
            return out
    except httpx.HTTPStatusError as e:
        log.warning("Tavily failed (%s): %s", e.response.status_code, e)
        return []
    except Exception as e:
        log.warning("Tavily failed: %s", e)
        return []

def _perplexity_search(query: str, max_results: int = 6) -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY: return []
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    body = {"model": os.getenv("PPLX_MODEL", "sonar-small-online"), "temperature": 0.0, "return_images": False,
            "top_p": 0.9, "search_recency_filter": "month",
            "messages": [{"role":"system","content":"Answer briefly. Provide citations. Focus on trustworthy, official sources in DE/EU if available."},
                         {"role":"user","content": f"Find 6 most relevant sources for: {query}. Return answer with citations."}]}
    try:
        with _client() as client:
            r = client.post("https://api.perplexity.ai/chat/completions", headers=headers, json=body)
            r.raise_for_status()
            data = r.json() or {}
    except httpx.HTTPStatusError as e:
        log.warning("Perplexity failed (%s): %s", e.response.status_code, e)
        return []
    except Exception as e:
        log.warning("Perplexity failed: %s", e)
        return []
    cites = []
    try: cites = data["choices"][0]["message"].get("citations") or []
    except Exception: cites = []
    if not cites:
        content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "")
        cites = re.findall(r"https?://[^\s\]\)>\}]+", content)
    out: List[Dict[str, Any]] = []
    for url in cites[:max_results]:
        out.append({"title": "", "url": _trim_url(url), "source": _domain(url),
                    "date": _today_iso(), "snippet": "", "engine": "perplexity"})
    return out

def _is_berlin_funding(u: str) -> bool:
    d = _domain(u)
    return d.endswith("berlin.de") or d == "ibb.de" or "investitionsbank-berlin" in d

def _eu_hint(u: str) -> bool:
    d = _domain(u); return d.endswith(EU_TLDS)

def _dedup(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        key = (_trim_url(it.get("url","")), (it.get("title") or "").strip().lower())
        if key in seen: continue
        seen.add(key); out.append(it)
    return out

def _recency_score(date_iso: str, window_days: int) -> float:
    try: d = dt.datetime.fromisoformat(date_iso).date()
    except Exception: d = dt.date.today()
    days = max(0, (dt.date.today() - d).days)
    return max(0.0, 1.0 - (days / float(max(1, window_days))))

def _trust_score(u: str) -> float: from math import isfinite; s = TRUST_WEIGHT.get(_domain(u), 0.5); return s if isfinite(s) else 0.5

def _query_boost(title: str, query: str) -> float:
    t = (title or "").lower(); q = (query or "").lower(); score = 0.0
    for tok in re.findall(r"[a-zäöüß]{4,}", q):
        if tok in t: score += 0.1
    return min(0.3, score)

def _rank(items: List[Dict[str, Any]], window_days: int, query: str) -> List[Dict[str, Any]]:
    for it in items:
        rs = _recency_score(it.get("date") or _today_iso(), window_days)
        ts = _trust_score(it.get("url", "")); qb = _query_boost(it.get("title", "") or it.get("source", ""), query)
        it["score"] = round(0.55*ts + 0.35*rs + 0.10*qb, 4)
    items.sort(key=lambda x: (-x.get("score", 0.0), x.get("title", "")))
    return items

def build_live_sections(context: Dict[str, Any]) -> Dict[str, Any]:
    branche = (context.get("branche") or "").strip() or "Beratung & Dienstleistungen"
    region = (context.get("region_code") or "").strip().upper()
    country = (context.get("country") or "DE").strip().upper()
    q_news = f'{branche} KI ("Künstliche Intelligenz" OR "Generative KI") site:de'
    q_tools = f'EU-geeignete KI Tools OR Open-Source KI {country} {branche}'
    q_funding = f'Förderprogramme KI Digitalisierung {country} {"Berlin " + region if region=="BE" else ""}'
    window = LIVE_PRIMARY_DAYS
    news = _tavily_search(q_news, days=window, max_results=8)
    tools = _tavily_search(q_tools, days=window, max_results=8)
    funding = _tavily_search(q_funding, days=window, max_results=8)
    if len(news) < 5: news += _perplexity_search(q_news, max_results=6)
    if len(funding) < 3: funding += _perplexity_search(q_funding, max_results=6)
    if len(tools) < 3: tools += _perplexity_search(q_tools, max_results=6)
    if window < LIVE_FALLBACK_MAX_DAYS and (len(news)<2 or len(funding)<2 or len(tools)<2):
        window = LIVE_FALLBACK_MAX_DAYS
        news += _tavily_search(q_news, days=window, max_results=8)
        funding += _tavily_search(q_funding, days=window, max_results=8)
        tools += _tavily_search(q_tools, days=window, max_results=8)
    def _augment(items: List[Dict[str, Any]]): return items
    news, tools, funding = _dedup(news), _dedup(tools), _dedup(funding)
    news, tools, funding = _rank(news, window, q_news)[:LIVE_MAX_ITEMS], _rank(tools, window, q_tools)[:LIVE_MAX_ITEMS], _rank(funding, window, q_funding)[:LIVE_MAX_ITEMS]
    for t in tools: t["eu_hint"] = _eu_hint(t.get("url", ""))
    for f in funding: f["berlin_badge"] = _is_berlin_funding(f.get("url", ""))
    return {"window_days": window, "news": news, "tools": tools, "funding": funding}
