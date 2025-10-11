
# websearch_utils.py
# Hybrid-Live-Suche über Perplexity + Tavily mit Klassifizierung, Dedupe & Logging.
from __future__ import annotations

from typing import Any, Dict, List, Optional
import os
import time
import json
import httpx

# Flexible Imports (als Local- oder Paket-Modul nutzbar)
try:
    from .utils_sources import normalize_url, get_domain, classify_source, dedupe_items, baseline_funding  # type: ignore
except Exception:  # pragma: no cover - fallback
    from utils_sources import normalize_url, get_domain, classify_source, dedupe_items, baseline_funding  # type: ignore

try:
    from .live_logger import log_event  # type: ignore
except Exception:  # pragma: no cover - fallback
    from live_logger import log_event  # type: ignore


TAVILY_URL = "https://api.tavily.com/search"
PPLX_URL = "https://api.perplexity.ai/chat/completions"  # Chat Completions (OpenAI-kompatibel)

# Default-Konfiguration
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS", "30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS", "60"))
TAVILY_MAX = int(os.getenv("TAVILY_MAX", "12"))
PPLX_MODEL = os.getenv("PPLX_MODEL", "sonar-medium-online")  # alternativen: sonar-pro, sonar-deep-research
PPLX_TIMEOUT = float(os.getenv("PPLX_TIMEOUT", "30.0"))

# ---- Tavily ---------------------------------------------------------------
def tavily_search(query: str, max_results: int = TAVILY_MAX, days: int = SEARCH_DAYS_NEWS) -> List[Dict[str, Any]]:
    """Sucht per Tavily mit Authorization: Bearer tvly-... und gibt eine homogene Struktur zurück."""
    key = os.getenv("TAVILY_API_KEY") or os.getenv("TAVILY_KEY") or ""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
        "time_range": f"{days}d",
    }
    ts = time.time()
    items: List[Dict[str, Any]] = []
    status = "ok"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(TAVILY_URL, headers=headers, json=payload)
        if resp.status_code == 401:
            status = "unauthorized"
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            items.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "domain": get_domain(r.get("url") or ""),
                "date": r.get("published_date") or "",
                "provider": "tavily",
                "score": r.get("score"),
            })
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        log_event("tavily", None, status, int((time.time() - ts) * 1000), count=len(items))
    return items


# ---- Perplexity (Chat Completions) ---------------------------------------
# Perplexity erfordert Bearer-Auth, messages[] und optional response_format (JSON Schema).
# Siehe beigefügte API-Hinweise. [perplexity messages/headers/response_format] fileciteturn0file0
def perplexity_search(query: str, max_results: int = 10, category_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    key = os.getenv("PPLX_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or ""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    system = "Du bist ein präziser Web-Recherche-Assistent. Antworte strikt als JSON ohne Fließtext."
    user = (
        "Finde aktuelle, verlässliche Webquellen (Titel, URL, Datum) zu folgendem Thema. "
        "Wenn möglich, gib das Veröffentlichungsdatum ISO‑8601 an. "
        f"Kontext-Hinweis Kategorie: {category_hint or 'gemischt'}. "
        f"Query: {query}"
    )
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "date": {"type": "string"},
                    },
                    "required": ["title", "url"],
                    "additionalProperties": True,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    body = {
        "model": PPLX_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 900,
        "response_format": {"type": "json_schema", "json_schema": {"schema": schema}},
    }
    ts = time.time()
    items: List[Dict[str, Any]] = []
    status = "ok"
    try:
        with httpx.Client(timeout=PPLX_TIMEOUT) as client:
            resp = client.post(PPLX_URL, headers=headers, json=body)
        if resp.status_code == 401:
            status = "unauthorized"
        resp.raise_for_status()
        data = resp.json()
        # OpenAI-kompatible Struktur: choices[0].message.content (JSON-String)
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        parsed = json.loads(content) if isinstance(content, str) else content
        for r in parsed.get("items", []):
            items.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "domain": get_domain(r.get("url") or ""),
                "date": r.get("date") or "",
                "provider": "perplexity",
            })
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        log_event("perplexity", os.getenv("PPLX_MODEL", PPLX_MODEL), status, int((time.time() - ts) * 1000), count=len(items))
    return items


# ---- Hybrid Orchestrierung -------------------------------------------------
def hybrid_live_search(
    query: str,
    briefing: Optional[Dict[str, Any]] = None,
    short_days: int = SEARCH_DAYS_NEWS,
    long_days: int = SEARCH_DAYS_TOOLS,
    max_results: int = 12,
) -> Dict[str, Any]:
    """Kombiniert Tavily + Perplexity, klassifiziert & dedupliziert, liefert admin-raw & Zählwerte."""
    # 1) Tavily & Perplexity abrufen
    tav = tavily_search(query, max_results=max_results, days=short_days)
    ppl = perplexity_search(query, max_results=max_results, category_hint="mixed")

    # 2) Baseline-Förderungen ergänzen (regionale + bundesweite)
    bl = baseline_funding((briefing or {}).get("bundesland_code"))

    raw_all = {"tavily": tav, "perplexity": ppl, "baseline": bl}

    # 3) Klassifizieren
    classified: List[Dict[str, Any]] = []
    for src in (tav + ppl + bl):
        cat = classify_source(src, briefing)
        item = dict(src)
        item["category"] = cat
        classified.append(item)

    # 4) Dedupe & Limitierung je Kategorie
    deduped = dedupe_items(classified)

    # 5) Zählen
    counts = {"news": 0, "tools": 0, "funding": 0, "other": 0}
    for it in deduped:
        counts[it.get("category", "other")] = counts.get(it.get("category", "other"), 0) + 1

    # 6) Rückgabe
    return {
        "items": deduped,
        "counts": counts,
        "raw": raw_all,
    }
