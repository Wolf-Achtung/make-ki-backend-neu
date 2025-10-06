# -*- coding: utf-8 -*-
"""
Hybrid live search (Tavily + Perplexity) with proper 7->30d fallback,
domain allow-list and dedupe. Returns [{title,url,source,date}].
"""
from __future__ import annotations
import json, logging, os, datetime as dt
from typing import Any, Dict, List
import httpx

log = logging.getLogger("websearch_utils")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "pplx-70b-online")

CFG_DIR = os.getenv("CFG_DIR", os.path.join(os.getcwd(), "config"))
LIVE_QUERIES_PATH = os.getenv("LIVE_QUERIES_PATH", os.path.join(CFG_DIR, "live_queries.json"))

def _load_whitelist(branche: str) -> Dict[str, Any]:
    try:
        with open(LIVE_QUERIES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(branche) or data.get("default") or {}
    except Exception as exc:
        log.warning("live_queries.json read failed: %s", exc)
        return {"include_domains": []}

def _days_to_tavily(days: int) -> str:
    days = 7 if days <= 7 else (30 if days <= 30 else days)
    return f"d{days}"

def _tavily_search(q: str, days: int, include: List[str], exclude: List[str], max_results: int) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY: return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": q,
        "search_depth": os.getenv("SEARCH_DEPTH", "basic"),
        "max_results": max_results,
        "include_domains": include or None,  # wichtig: None statt []
        "exclude_domains": exclude or None,
        "topic": os.getenv("SEARCH_TOPIC", "news"),
        "time_range": _days_to_tavily(days),
    }
    try:
        with httpx.Client(timeout=float(os.getenv("LIVE_TIMEOUT_S","8.0"))) as cli:
            r = cli.post(url, json=payload)
            if r.status_code == 400 and days < 30:
                payload["include_domains"] = None
                payload["query"] = " ".join(q.split()[:8])
                payload["time_range"] = "d30"
                r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            return [{"title":it.get("title"),"url":it.get("url"),"source":it.get("website"),"date":it.get("published_date") or ""} for it in data.get("results",[])]
    except Exception as exc:
        log.warning("Tavily failed: %s", exc); return []

def _perplexity_search(q: str, days: int, max_results: int) -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY: return []
    url = "https://api.perplexity.ai/chat/completions"
    sys = "You are a web research assistant. Return fresh, credible items (title + url + source + date)."
    since = (dt.date.today() - dt.timedelta(days=min(30, max(7, days)))).isoformat()
    user = f"Return {max_results} current items since {since} as JSON list with objects {{title, url, source, date}} for: {q}"
    payload = {"model": PERPLEXITY_MODEL, "messages":[{"role":"system","content":sys},{"role":"user","content":user}],"max_tokens":600}
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=float(os.getenv("LIVE_TIMEOUT_S","8.0"))) as cli:
            r = cli.post(url, headers=headers, json=payload)
            if r.status_code == 400 and days < 30:
                since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
                payload["messages"][-1]["content"] = f"Return {max_results} current items since {since} as JSON list with objects {{title, url, source, date}} for: {q[:128]}"
                r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            txt = r.json().get("choices", [{}])[0].get("message", {}).get("content", "[]")
            data = json.loads(txt) if txt.strip().startswith("[") else []
            return [{"title":it.get("title"),"url":it.get("url"),"source":it.get("source"),"date":it.get("date")} for it in data[:max_results]]
    except Exception as exc:
        log.warning("Perplexity failed: %s", exc); return []

def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        try: domain = (it.get("url") or "").split("/")[2]
        except Exception: domain = ""
        key = (it.get("title") or "").strip().lower()[:120] + "|" + (domain or "")
        if key not in seen:
            seen.add(key); out.append(it)
    return out[: int(os.getenv("LIVE_MAX_ITEMS","5"))]

def _build_query(topic: str, b: Dict[str, Any]) -> str:
    branche = b.get("branche_label") or b.get("branche") or ""
    usecase = (b.get("_pull_kpi") or {}).get("usecase") or ""
    if topic == "news":   return f"{branche} KI Digitalisierung aktuelle Nachrichten {usecase}"
    if topic == "tools":  return f"{branche} KI Tools DSGVO EU {usecase}"
    if topic == "funding":
        bl = b.get("bundesland_code") or ""; return f"Förderprogramme {branche} Digitalisierung KI {bl}"
    return "KI Digitalisierung Aktualisierung"

def hybrid_search(topic: str, briefing: Dict[str, Any], days: int, max_items: int) -> List[Dict[str, Any]]:
    q = _build_query(topic, briefing)
    wl = _load_whitelist(str(briefing.get("branche") or "default"))
    include = wl.get("include_domains", [])
    exclude_env = [d.strip() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS") or "").split(",") if d.strip()]
    tav = _tavily_search(q, days=days, include=include, exclude=exclude_env, max_results=max_items)
    ppl = _perplexity_search(q, days=days, max_results=max_items)
    return _dedupe(tav + ppl)
