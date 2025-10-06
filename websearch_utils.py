# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Hybrid live search (Tavily + Perplexity) mit 7->30d-Fallback, Whitelist, Dedupe.
Beim ersten Zugriff wird config/live_queries.json automatisch validiert und – falls nötig –
korrigiert (Kommentare, trailing commas, BOM, zusammengeklebte JSON-Objekte).

Rückgabeformat der Suchfunktionen: [{title, url, source, date}]
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from typing import Any, Dict, List

import httpx

log = logging.getLogger("websearch_utils")
if not log.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
log.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# ENV / Pfade
# -----------------------------------------------------------------------------

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "pplx-70b-online")

CFG_DIR = os.getenv("CFG_DIR", os.path.join(os.getcwd(), "config"))
LIVE_QUERIES_PATH = os.getenv("LIVE_QUERIES_PATH", os.path.join(CFG_DIR, "live_queries.json"))

ENV_INCLUDE = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS", "") or "").split(",") if d.strip()]
ENV_EXCLUDE = [d.strip() for d in (os.getenv("SEARCH_EXCLUDE_DOMAINS", "") or "").split(",") if d.strip()]

LIVE_TIMEOUT_S = float(os.getenv("LIVE_TIMEOUT_S", "8.0"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS", "5"))

AUTOFIX_LIVE_QUERIES = os.getenv("LIVE_QUERIES_AUTOFIX", "1").strip().lower() in {"1", "true", "yes", "on"}

# -----------------------------------------------------------------------------
# JSON-Reparatur für config/live_queries.json
# -----------------------------------------------------------------------------

def _read_text_lenient(path: str) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read()
        # UTF-8 mit BOM tolerieren
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        return data.decode("utf-8", errors="ignore")
    except FileNotFoundError:
        return ""
    except Exception as exc:
        log.warning("live_queries: read failed: %s", exc)
        return ""

_COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE  = re.compile(r"^\s*//.*?$", re.MULTILINE)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_BACKTICKS_RE = re.compile(r"`")

def _strip_json_comments_and_trailing_commas(s: str) -> str:
    s = _COMMENT_BLOCK_RE.sub("", s)
    s = _LINE_COMMENT_RE.sub("", s)
    # Backticks verhindern json.loads → entfernen
    s = _BACKTICKS_RE.sub("", s)
    # trailing commas raus
    s = _TRAILING_COMMA_RE.sub(r"\1", s)
    return s.strip()

def _coalesce_concatenated_objects(s: str) -> Dict[str, Any]:
    """
    Falls mehrere JSON-Objekte einfach aneinandergeklebt wurden, mergen wir sie in EIN Dict.
    Beispiel:
        { "default": {...} }{ "beratung": {...} }
    → { "default": {...}, "beratung": {...} }
    Strategie: wir suchen alle Top-Level-Objekte und laden sie einzeln.
    """
    objs: List[Dict[str, Any]] = []
    depth = 0
    start = None
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                chunk = s[start:i+1]
                try:
                    obj = json.loads(_strip_json_comments_and_trailing_commas(chunk) or "{}")
                    if isinstance(obj, dict):
                        objs.append(obj)
                except Exception:
                    # Ignorieren – wir versuchen trotzdem, weiterzulesen
                    pass
                start = None
    merged: Dict[str, Any] = {}
    for o in objs:
        merged.update(o)
    return merged or {}

def _normalize_live_queries(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stellt sicher, dass include_domains Listen von Strings sind und dedupliziert,
    und dass ein 'default'-Block existiert.
    """
    def _dedupe_list(x: Any) -> List[str]:
        if not isinstance(x, list):
            return []
        seen, out = set(), []
        for v in x:
            if not isinstance(v, str):
                continue
            v2 = v.strip().lower()
            if v2 and v2 not in seen:
                seen.add(v2)
                out.append(v2)
        return out

    if "default" not in data or not isinstance(data["default"], dict):
        data["default"] = {}

    # Default include_domains
    data["default"]["include_domains"] = _dedupe_list(
        (data["default"].get("include_domains") if isinstance(data["default"], dict) else []) or []
    )

    # Merge ENV includes in jeden Branch
    for key, obj in list(data.items()):
        if not isinstance(obj, dict):
            continue
        obj.setdefault("include_domains", [])
        obj["include_domains"] = _dedupe_list(obj["include_domains"] + ENV_INCLUDE)

        # queries-Block optional, aber sicherstellen, dass dict
        if not isinstance(obj.get("queries"), dict):
            obj["queries"] = {}

    return data

def _autofix_live_queries_file_if_needed(path: str) -> Dict[str, Any]:
    """
    Liest live_queries.json, entfernt Kommentare/trailing commas/BOM,
    versucht bei JSON-Fehlern, zusammengeklebte Objekte zu mergen.
    Schreibt bei Änderungen die bereinigte Datei zurück (pretty-printed).
    """
    raw = _read_text_lenient(path)
    if not raw:
        log.warning("live_queries: file not found, using defaults")
        return {"default": {"include_domains": ENV_INCLUDE or []}}

    cleaned = _strip_json_comments_and_trailing_commas(raw)
    data: Dict[str, Any] = {}
    changed = False

    try:
        data = json.loads(cleaned or "{}")
    except Exception:
        # Versuch: mehrere aneinandergereihte JSON-Objekte mergen
        data = _coalesce_concatenated_objects(cleaned)
        changed = True

    if not isinstance(data, dict):
        # finaler Fallback
        log.warning("live_queries: invalid structure, using default object")
        data = {"default": {"include_domains": ENV_INCLUDE or []}}
        changed = True

    # Normalisieren + ENV-Merge
    normalized = _normalize_live_queries(data)
    if normalized != data:
        changed = True

    if AUTOFIX_LIVE_QUERIES and changed:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(normalized, f, ensure_ascii=False, indent=2)
            log.info("live_queries: auto-fixed and saved → %s", path)
        except Exception as exc:
            log.warning("live_queries: could not save auto-fixed file: %s", exc)

    return normalized

# -----------------------------------------------------------------------------
# Whitelist-Lader (lazy, mit Auto-Fix)
# -----------------------------------------------------------------------------

def _load_whitelist(branch: str) -> Dict[str, Any]:
    """
    Lädt und repariert (falls nötig) config/live_queries.json. Gibt einen Branch-Block zurück.
    Struktur:
    {
      "<branch>": {
        "include_domains": [...],
        "queries": { "news": [...], "tools": [...], "funding": [...] }
      },
      "default": {...}
    }
    """
    data = _autofix_live_queries_file_if_needed(LIVE_QUERIES_PATH)
    out = data.get(branch) or data.get("default") or {}
    # finale Absicherung
    out.setdefault("include_domains", [])
    out.setdefault("queries", {})
    # ENV-Excludes bleiben global – im Call verwendet
    return out

# -----------------------------------------------------------------------------
# API-Clients (Tavily / Perplexity)
# -----------------------------------------------------------------------------

def _days_to_tavily(days: int) -> str:
    d = 7 if days <= 7 else (30 if days <= 30 else days)
    return f"d{d}"

def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""

def _tavily_search(q: str, days: int, include: List[str], exclude: List[str], max_results: int) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": q,
        "search_depth": os.getenv("SEARCH_DEPTH", "basic"),
        "max_results": max_results,
        "include_domains": include or None,  # nie leere Liste senden
        "exclude_domains": exclude or None,
        "topic": os.getenv("SEARCH_TOPIC", "news"),
        "time_range": _days_to_tavily(days),
    }
    try:
        with httpx.Client(timeout=LIVE_TIMEOUT_S) as cli:
            r = cli.post(url, json=payload)
            if r.status_code == 400 and days < 30:
                # Query vereinfachen & 30 Tage
                payload["query"] = " ".join(q.split()[:8])
                payload["time_range"] = "d30"
                payload["include_domains"] = None
                r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            items = []
            for it in data.get("results", []):
                items.append({
                    "title": it.get("title") or it.get("url"),
                    "url": it.get("url"),
                    "source": it.get("website") or _domain(it.get("url") or ""),
                    "date": it.get("published_date") or "",
                })
            return items
    except Exception as exc:
        log.warning("Tavily failed: %s", exc)
        return []

def _perplexity_search(q: str, days: int, max_results: int) -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY:
        return []
    url = "https://api.perplexity.ai/chat/completions"
    since = (dt.date.today() - dt.timedelta(days=min(30, max(7, days)))).isoformat()
    sys = (
        "You are a web research assistant. Return a concise JSON array of items "
        "with keys: title, url, source, date (ISO), strictly from reputable sources."
    )
    user = f"Find up-to-date {q}. Consider only results since {since}. Respond with pure JSON."
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": PERPLEXITY_MODEL, "messages": [{"role": "system", "content": sys},
                                                       {"role": "user", "content": user}],
               "temperature": 0, "top_p": 1}
    try:
        with httpx.Client(timeout=LIVE_TIMEOUT_S) as cli:
            r = cli.post(url, json=payload)
            if r.status_code == 400 and days < 30:
                payload["messages"][-1]["content"] = f"Find recent {q}. Respond with pure JSON."
                r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            txt = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "[]"
            txt = re.sub(r"```json|```", "", txt).strip()
            items = json.loads(txt) if txt.strip().startswith("[") else []
            out = []
            for it in items[: max_results]:
                out.append({
                    "title": it.get("title") or it.get("url"),
                    "url": it.get("url"),
                    "source": it.get("source") or _domain(it.get("url") or ""),
                    "date": it.get("date") or "",
                })
            return out
    except Exception as exc:
        log.warning("Perplexity failed: %s", exc)
        return []

# -----------------------------------------------------------------------------
# Merge / Queries / Public API
# -----------------------------------------------------------------------------

def _dedupe(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        u = (it.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(it)
        if len(out) >= limit:
            break
    return out

def _queries_for(topic: str, b: Dict[str, Any], wl: Dict[str, Any]) -> List[str]:
    base = wl.get("queries", {}).get(topic) or []
    extra: List[str] = []
    branche = b.get("branche_label") or b.get("branche") or ""
    hl = b.get("hauptleistung") or ""
    if topic == "news":
        extra.append(f"{branche} KI Digitalisierung Deutschland")
    elif topic == "tools":
        extra.append("KI Tools EU hosting DSGVO")
    elif topic == "funding":
        extra.append(f"Förderung {b.get('bundesland_code','DE')} KI Digitalisierung Mittelstand Frist")
    if hl:
        extra.append(hl)
    # Dedupe
    seen, out = set(), []
    for q in base + extra:
        q2 = " ".join(str(q).split())
        if q2 and q2 not in seen:
            seen.add(q2)
            out.append(q2)
    return out or ["KI Digitalisierung Deutschland"]

def hybrid_search(topic: str, briefing: Dict[str, Any], days: int, max_items: int) -> List[Dict[str, Any]]:
    """
    Kombiniert Tavily + Perplexity.
    Bei 400-Errors wird im Client auf 30 Tage erweitert und die Query vereinfacht.
    """
    wl = _load_whitelist(briefing.get("branche") or "default")
    include = wl.get("include_domains", [])
    queries = _queries_for(topic, briefing, wl)

    tav_all: List[Dict[str, Any]] = []
    ppl_all: List[Dict[str, Any]] = []
    for q in queries[:3]:  # max. drei Queries
        tav = _tavily_search(q, days=days, include=include, exclude=ENV_EXCLUDE, max_results=max_items)
        ppl = _perplexity_search(q, days=days, max_results=max_items)
        tav_all.extend(tav)
        ppl_all.extend(ppl)

    merged = _dedupe(tav_all + ppl_all, limit=max_items)
    return merged
