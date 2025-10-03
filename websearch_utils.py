# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live-Suche (Gold-Standard+)

Neu/verbessert:
- Provider: Tavily, Perplexity, Hybrid (Merge/Dedupe/Rank)
- On-Disk-Cache für Live-Ergebnisse (SQLite, TTL)
- EU-Host-Check via DNS-Resolve + RDAP (ipwhois) inkl. eigenem Cache (TTL)
- Branchen-Heuristik für Tool-Kategorisierung (Tuning-Map)
- Erweiterte Kanäle: news, tools, funding, case_studies, regulatory
- Vendor-Shortlist (Top 5, unique Domains, Host-Land), Tool-Alternativen
- Förder-Alarm (Deadline-Erkennung)
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import socket
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

import httpx
from ipwhois import IPWhois  # type: ignore
try:
    import dns.resolver  # type: ignore
except Exception:  # optional fallback, socket wird ohnehin verwendet
    dns = None  # type: ignore

logger = logging.getLogger("websearch_utils")
if not logger.handlers:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# ------------------------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent
CACHE_DIR: Path = Path(os.getenv("CACHE_DIR", str(BASE_DIR / ".cache")))
LIVE_CACHE_PATH: Path = Path(os.getenv("LIVE_CACHE_PATH", str(CACHE_DIR / "live_cache.sqlite")))
LIVE_CACHE_ENABLED: bool = os.getenv("LIVE_CACHE_ENABLED", "true").lower() == "true"
LIVE_CACHE_TTL_SECONDS: int = int(os.getenv("LIVE_CACHE_TTL_SECONDS", "7200"))  # 2h

# Cache für Host-Geolocation (Domain → cc)
HOST_CACHE_PATH: Path = Path(os.getenv("HOST_CACHE_PATH", str(CACHE_DIR / "host_cache.sqlite")))
EU_HOST_TTL_SECONDS: int = int(os.getenv("EU_HOST_TTL_SECONDS", "604800"))  # 7 Tage
ENABLE_EU_HOST_CHECK: bool = os.getenv("ENABLE_EU_HOST_CHECK", "true").lower() == "true"

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid").lower()  # tavily|perplexity|hybrid
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
COUNTRY_CODE = os.getenv("COUNTRY_CODE", "DE").upper()
LIVE_MAX_RESULTS = int(os.getenv("LIVE_MAX_RESULTS", "10"))
LIVE_DAYS = int(os.getenv("LIVE_DAYS", "60"))
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "18.0"))

ENABLE_CASE_STUDIES = os.getenv("ENABLE_CASE_STUDIES", "true").lower() == "true"
ENABLE_REGULATORY = os.getenv("ENABLE_REGULATORY", "true").lower() == "true"

# EU‑Zuordnung
EU_TLDS = {
    "at", "be", "bg", "hr", "cy", "cz", "dk", "ee", "fi", "fr", "de", "gr",
    "hu", "ie", "it", "lv", "lt", "lu", "mt", "nl", "pl", "pt", "ro", "sk",
    "si", "es", "se", "eu",
}
EU_COUNTRIES = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV",
    "LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"
}

# Branchen-Heuristik (Tuning) – Kanonische Keys
INDUSTRY_TUNING: Dict[str, List[str]] = {
    "beratung": ["nlp", "automation", "crm", "analytics", "documentation"],
    "marketing": ["marketing", "analytics", "nlp", "automation", "crm"],
    "it": ["dev", "security", "documentation", "automation", "search"],
    "finanzen": ["finance", "security", "compliance", "analytics", "automation"],
    "handel": ["marketing", "crm", "analytics", "automation", "support"],
    "bildung": ["documentation", "nlp", "analytics", "support", "search"],
    "verwaltung": ["compliance", "security", "documentation", "search", "automation"],
    "gesundheit": ["compliance", "security", "nlp", "documentation", "support"],
    "bau": ["vision", "documentation", "automation", "project"],
    "medien": ["vision", "nlp", "automation", "marketing", "analytics"],
    "industrie": ["automation", "analytics", "vision", "dev", "security"],
    "transport": ["automation", "analytics", "support", "vision", "documentation"],
}

# ------------------------------------------------------------------------------
# SQLite Caches
# ------------------------------------------------------------------------------
def _sql_init(path: Path, ddl: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(path)) as con:
            con.executescript(ddl)
            con.commit()
    except Exception as e:
        logger.warning("SQLite init failed for %s: %s", path, e)

def _live_cache_init() -> None:
    if not LIVE_CACHE_ENABLED:
        return
    _sql_init(
        LIVE_CACHE_PATH,
        """
        CREATE TABLE IF NOT EXISTS live_cache (
            key TEXT PRIMARY KEY,
            payload TEXT,
            created_at INTEGER
        );
        """,
    )

def _host_cache_init() -> None:
    if not ENABLE_EU_HOST_CHECK:
        return
    _sql_init(
        HOST_CACHE_PATH,
        """
        CREATE TABLE IF NOT EXISTS host_cache (
            domain TEXT PRIMARY KEY,
            cc TEXT,
            ip TEXT,
            created_at INTEGER
        );
        """,
    )

def _live_cache_get(key: str) -> Optional[Dict[str, Any]]:
    if not (LIVE_CACHE_ENABLED and LIVE_CACHE_PATH.exists()):
        return None
    try:
        with sqlite3.connect(str(LIVE_CACHE_PATH)) as con:
            row = con.execute("SELECT payload, created_at FROM live_cache WHERE key=?", (key,)).fetchone()
            if not row:
                return None
            payload, created_at = row
            if int(time.time()) - int(created_at) > LIVE_CACHE_TTL_SECONDS:
                return None
            return json.loads(payload)
    except Exception as e:
        logger.debug("Live cache get failed: %s", e)
        return None

def _live_cache_set(key: str, payload: Mapping[str, Any]) -> None:
    if not LIVE_CACHE_ENABLED:
        return
    try:
        with sqlite3.connect(str(LIVE_CACHE_PATH)) as con:
            con.execute(
                "INSERT OR REPLACE INTO live_cache (key, payload, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(payload, ensure_ascii=False), int(time.time())),
            )
            con.commit()
    except Exception as e:
        logger.debug("Live cache set failed: %s", e)

def _host_cache_get(domain: str) -> Optional[Tuple[str, str]]:
    if not (ENABLE_EU_HOST_CHECK and HOST_CACHE_PATH.exists()):
        return None
    try:
        with sqlite3.connect(str(HOST_CACHE_PATH)) as con:
            row = con.execute("SELECT cc, ip FROM host_cache WHERE domain=?", (domain,)).fetchone()
            if not row:
                return None
            cc, ip = row
            # TTL prüfen
            ts_row = con.execute("SELECT created_at FROM host_cache WHERE domain=?", (domain,)).fetchone()
            if not ts_row:
                return None
            created_at = ts_row[0]
            if int(time.time()) - int(created_at) > EU_HOST_TTL_SECONDS:
                return None
            return str(cc or ""), str(ip or "")
    except Exception:
        return None

def _host_cache_set(domain: str, cc: str, ip: str) -> None:
    if not ENABLE_EU_HOST_CHECK:
        return
    try:
        with sqlite3.connect(str(HOST_CACHE_PATH)) as con:
            con.execute(
                "INSERT OR REPLACE INTO host_cache (domain, cc, ip, created_at) VALUES (?, ?, ?, ?)",
                (domain, cc, ip, int(time.time())),
            )
            con.commit()
    except Exception:
        pass

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _escape(s: Any) -> str:
    return "" if s is None else html.escape(str(s).strip(), quote=True)

def _safe_url(u: Any) -> str:
    u = str(u or "").strip()
    if not u:
        return ""
    if re.match(r"^https?://", u, flags=re.I):
        return u
    return ""

def _extract_domain(u: str) -> str:
    try:
        netloc = urlparse(u).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""

def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in items:
        key = (it.get("title", "").lower(), it.get("url", "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def _rank(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    type_weight = {"news": 3, "funding": 2, "tools": 1, "regulatory": 2, "case_studies": 2}
    def score(it: Dict[str, Any]) -> float:
        w = type_weight.get(it.get("type", ""), 0)
        try:
            dt = datetime.fromisoformat(it.get("published_at", "").replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            rec = max(0, LIVE_DAYS - age_days) / LIVE_DAYS
        except Exception:
            rec = 0.5
        return w + rec
    return sorted(items, key=score, reverse=True)

def _normalize_item(title: Any, url: Any, summary: Any = "", published_at: Any = "",
                    source: Any = "", itype: str = "") -> Dict[str, Any]:
    t = _escape(title)
    u = _safe_url(url)
    s = _escape(summary)[:300]
    p = str(published_at or "").strip()
    if p and not re.search(r"\d{4}-\d{2}-\d{2}", p):
        p = ""
    return {
        "title": t or "",
        "url": u,
        "summary": s,
        "published_at": p,
        "source": (source or "").strip()[:120],
        "type": itype,
    }

# ---- DNS & RDAP (EU-Host-Check) ------------------------------------------------
def _resolve_ips(domain: str) -> List[str]:
    ips: List[str] = []
    # socket
    try:
        infos = socket.getaddrinfo(domain, 80, proto=socket.IPPROTO_TCP)
        for fam, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            if ":" not in ip:  # IPv4 bevorzugen
                ips.append(ip)
    except Exception:
        pass
    # dnspython fallback
    if not ips and "dns" in globals() and getattr(dns, "resolver", None):
        try:
            ans = dns.resolver.resolve(domain, "A")
            ips = [r.to_text() for r in ans]
        except Exception:
            pass
    return ips[:3]

def _ip_to_country(ip: str) -> str:
    try:
        data = IPWhois(ip).lookup_rdap(depth=1)
        cc = (data.get("asn_country_code") or
              (data.get("network") or {}).get("country") or "")
        return (cc or "").upper()
    except Exception:
        return ""

def _eu_host_info(url: str) -> Dict[str, Any]:
    """
    Best effort: Domain → IP(s) → RDAP → Country Code.
    Caching: Domain→(cc, ip) mit TTL.
    """
    domain = _extract_domain(url)
    if not (ENABLE_EU_HOST_CHECK and domain):
        return {"domain": domain, "ip": "", "cc": "", "eu": False}

    _host_cache_init()
    cached = _host_cache_get(domain)
    if cached:
        cc, ip = cached
        return {"domain": domain, "ip": ip, "cc": cc, "eu": cc in EU_COUNTRIES}

    ips = _resolve_ips(domain)
    cc = ""
    ip_hit = ""
    for ip in ips:
        cc = _ip_to_country(ip)
        ip_hit = ip
        if cc:
            break

    # Fallback: ccTLD Heuristik
    if not cc and "." in domain:
        tld = domain.split(".")[-1].lower()
        if tld in EU_TLDS:
            cc = tld.upper()

    _host_cache_set(domain, cc, ip_hit)
    return {"domain": domain, "ip": ip_hit, "cc": cc, "eu": cc in EU_COUNTRIES}

# ------------------------------------------------------------------------------
# Provider: Tavily
# ------------------------------------------------------------------------------
def _query_tavily(q: str, max_results: int, days: int, itype_hint: str = "") -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": q,
        "search_depth": "advanced",
        "max_results": max(1, min(max_results, 20)),
        "include_domains": [],
        "exclude_domains": [],
        "days": max(1, min(days, 365)),
        "include_answer": False,
        "include_raw_content": False,
        "topic": "general",
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Tavily request failed: %s", e)
        return []

    items: List[Dict[str, Any]] = []
    for res in data.get("results", []):
        items.append(
            _normalize_item(
                res.get("title"),
                res.get("url"),
                res.get("content", ""),
                res.get("published_date") or res.get("published_at") or "",
                res.get("source", ""),
                itype_hint or "news",
            )
        )
    return items

# ------------------------------------------------------------------------------
# Provider: Perplexity
# ------------------------------------------------------------------------------
def _query_perplexity(q: str, max_results: int, itype_hint: str = "") -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY:
        return []
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    prompt = (
        "Return a concise JSON array of relevant links with fields: "
        '[{"title":"...","url":"...","summary":"...","published_at":"YYYY-MM-DD"}]. '
        "No intro text, JSON only."
    )
    body = {
        "model": os.getenv("PERPLEXITY_MODEL", "sonar"),
        "messages": [
            {"role": "system", "content": "You are a precise research assistant."},
            {"role": "user", "content": f"{q}\n\n{prompt}"},
        ],
        "temperature": 0.0,
        "max_tokens": int(os.getenv("PPLX_MAX_TOKENS", "800")),
    }
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        logger.warning("Perplexity request failed: %s", e)
        return []

    items: List[Dict[str, Any]] = []
    try:
        arr = json.loads(text)
        if isinstance(arr, list):
            for it in arr[: max_results]:
                items.append(
                    _normalize_item(
                        it.get("title"),
                        it.get("url"),
                        it.get("summary", ""),
                        it.get("published_at", ""),
                        "perplexity",
                        itype_hint or "news",
                    )
                )
            return items
    except Exception:
        pass
    for m in re.finditer(r"https?://[^\s)\"']+", text):
        u = m.group(0)
        items.append(_normalize_item(u, u, "", "", "perplexity", itype_hint or "news"))
    return items[:max_results]

# ------------------------------------------------------------------------------
# Post-Processing: Tools & Funding
# ------------------------------------------------------------------------------
def _label_tool(item: Dict[str, Any]) -> List[str]:
    lbl: List[str] = []
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    url = item.get("url", "").lower()
    domain = _extract_domain(url)
    if "open source" in text or "opensource" in text or "self-host" in text or "github.com" in url:
        lbl.append("Open-Source")
    if "gdpr" in text or "dsgvo" in text:
        lbl.append("DSGVO")
    tld = domain.split(".")[-1] if domain else ""
    if tld in EU_TLDS:
        lbl.append("EU")
    if "api" in text:
        lbl.append("API")
    if "free tier" in text or "free plan" in text or "kostenlos" in text or "gratis" in text:
        lbl.append("Free")
    return lbl

def _infer_tool_category(title: str, summary: str, branche: str = "") -> str:
    text = f"{title} {summary}".lower()
    base_map = {
        "documentation": ["doc", "doku", "knowledge", "wiki", "handbook"],
        "analytics": ["analytics", "analyse", "insights", "tracking", "metrics", "bi"],
        "automation": ["automation", "workflow", "rpa", "automatisierung", "pipeline", "orchestr"],
        "chatbot": ["chatbot", "assistant", "copilot", "conversational"],
        "vision": ["video", "image", "vision", "schnitt", "subtitle", "ocr"],
        "nlp": ["text", "prompt", "summar", "transkript", "spracherkennung"],
        "dev": ["code", "testing", "lint", "deploy", "ci", "cd", "repository"],
        "security": ["security", "sicherheit", "privacy", "encryption"],
        "compliance": ["compliance", "ai act", "dsgvo", "gdpr"],
        "search": ["search", "suche", "retrieval", "rag", "index"],
        "marketing": ["ads", "kampagne", "seo", "content", "social"],
        "crm": ["crm", "kund", "sales", "pipeline"],
        "finance": ["invoice", "finanz", "buchhaltung", "abrechnung"],
        "hr": ["hr", "bewerb", "recruit", "talent"],
        "support": ["ticket", "support", "helpdesk"],
        "general": [],
    }
    # Basis-Scores aus Keywords
    scores: Dict[str, float] = {k: 0.0 for k in base_map}
    for cat, keys in base_map.items():
        for k in keys:
            if k and k in text:
                scores[cat] += 1.0
    # Branchen-Tuning
    b = (branche or "").lower()
    for key, pref in INDUSTRY_TUNING.items():
        if key in b:
            for i, cat in enumerate(pref[:5]):
                scores[cat] = scores.get(cat, 0.0) + (0.30 - i * 0.05)
            break
    # Beste Kategorie
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "general"

def _build_vendor_shortlist(tools: List[Dict[str, Any]], branche: str, limit: int = 5) -> List[Dict[str, Any]]:
    ranked = _rank(tools)
    seen_domains = set()
    shortlist: List[Dict[str, Any]] = []
    for it in ranked:
        domain = _extract_domain(it.get("url", ""))
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        labels = _label_tool(it)
        cat = _infer_tool_category(it.get("title", ""), it.get("summary", ""), branche)
        host_cc = ""
        eu_host = False
        if ENABLE_EU_HOST_CHECK:
            info = _eu_host_info(it.get("url", ""))
            host_cc = info.get("cc", "")
            eu_host = bool(info.get("eu"))
            if eu_host and "EU-Host" not in labels:
                labels.append("EU-Host")
        shortlist.append(
            {
                "name": it.get("title", ""),
                "url": it.get("url", ""),
                "domain": domain,
                "category": cat,
                "labels": labels,
                "host_cc": host_cc,
                "eu_host": eu_host,
            }
        )
        if len(shortlist) >= limit:
            break
    return shortlist

def _build_tool_alternatives(tools: List[Dict[str, Any]], branche: str, groups: int = 5) -> List[Dict[str, Any]]:
    # Gruppieren nach getunter Kategorie
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for it in tools:
        cat = _infer_tool_category(it.get("title", ""), it.get("summary", ""), branche)
        it["category"] = cat
        buckets.setdefault(cat, []).append(it)

    out: List[Dict[str, Any]] = []
    for cat, items in buckets.items():
        ranked = _rank(items)
        if not ranked:
            continue
        for primary in ranked[:groups]:
            alts = [x for x in ranked if _extract_domain(x.get("url", "")) != _extract_domain(primary.get("url", ""))]
            alts = alts[:2]
            primary_l = dict(primary)
            primary_l["badges"] = _label_tool(primary_l)
            if ENABLE_EU_HOST_CHECK:
                info = _eu_host_info(primary_l.get("url", ""))
                if info.get("eu"):
                    primary_l["badges"].append("EU-Host")
            for a in alts:
                a["badges"] = _label_tool(a)
                if ENABLE_EU_HOST_CHECK:
                    info_a = _eu_host_info(a.get("url", ""))
                    if info_a.get("eu"):
                        a["badges"].append("EU-Host")
            out.append({"primary": primary_l, "alternatives": alts})
            if len(out) >= groups:
                return out
    return out

def _parse_date_any(text: str) -> Optional[datetime]:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        try:
            return datetime.fromisoformat(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
    if m:
        d, mth, y = m.group(1).split(".")
        try:
            return datetime(int(y), int(mth), int(d))
        except Exception:
            pass
    return None

def _mark_funding_urgency(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        text = f"{it.get('title', '')} {it.get('summary','')}"
        deadline = _parse_date_any(text)
        it = dict(it)
        it["badges"] = it.get("badges", [])
        if deadline:
            days = (deadline - datetime.now()).days
            it["deadline_days"] = days
            if 0 <= days <= 30:
                it["badges"].append("Deadline ≤ 30 Tage")
            elif days < 0:
                it["badges"].append("Deadline abgelaufen")
            else:
                it["badges"].append(f"Deadline in {days} Tagen")
        elif re.search(r"\b(frist|deadline|endet|stichtag)\b", text, flags=re.I):
            it["badges"].append("Frist beachten")
        out.append(it)
    return out

# ------------------------------------------------------------------------------
# Query-Baukasten
# ------------------------------------------------------------------------------
def _make_queries(branche: str, leistung: str, bundesland: str, size: str, lang: str) -> Dict[str, List[str]]:
    b = (branche or "").strip()
    l = (leistung or "").strip()
    s = (size or "").strip()
    bl = (bundesland or "").strip()

    news_q = [
        f'{b} KI Nachrichten {COUNTRY_CODE} letzte {LIVE_DAYS} Tage',
        f'{b} {l} KI Praxisbeispiele {COUNTRY_CODE} News',
    ]
    tools_q = [
        f'KI Tools für {b} {s} DSGVO-konform',
        f'Open-Source KI Tools {b} 2025',
    ]
    funding_q = [
        f'{COUNTRY_CODE} {bl} Förderprogramme KI KMU Frist',
        f'{COUNTRY_CODE} Innovationsförderung KI Mittelstand',
    ]

    if lang != "de":
        news_q = [
            f'{b} AI news {COUNTRY_CODE} last {LIVE_DAYS} days',
            f'{b} {l} AI case studies {COUNTRY_CODE} news',
        ]
        tools_q = [
            f'best AI tools for {b} {s} company 2025 GDPR-friendly',
            f'{b} {l} open source AI tools 2025',
        ]
        funding_q = [
            f'{COUNTRY_CODE} {bl} AI grants SME deadline',
            f'{COUNTRY_CODE} innovation grant AI small business',
        ]

    return {"news": news_q, "tools": tools_q, "funding": funding_q}

# ------------------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------------------
def query_live_items(
    branche: Optional[str] = "",
    unternehmensgroesse: Optional[str] = "",
    leistung: Optional[str] = "",
    bundesland: Optional[str] = "",
    lang: Optional[str] = "de",
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Kern-Einstieg: führt queries (news/tools/funding) aus, merged, dedupliziert, rankt.
    Liefert zusätzlich:
      - funding mit Badges (Deadline-Alarm)
      - case_studies (optional), regulatory (optional)
      - vendor_shortlist (Top 5, unique Domains, Host-Land), tool_alternatives
      - EU-Host-Labels (falls aktiviert)
    Caching: live_cache (TTL), host_cache (TTL)
    """
    lang = (lang or "de")[:2]
    key_raw = json.dumps(
        {
            "branche": (branche or "").lower(),
            "size": (unternehmensgroesse or "").lower(),
            "leistung": (leistung or "").lower(),
            "bundesland": (bundesland or "").lower(),
            "lang": lang,
            "provider": SEARCH_PROVIDER,
            "live_days": LIVE_DAYS,
            "live_max": LIVE_MAX_RESULTS,
            "country": COUNTRY_CODE,
            "case": ENABLE_CASE_STUDIES,
            "reg": ENABLE_REGULATORY,
            "eu_host": ENABLE_EU_HOST_CHECK,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    cache_key = sha256(key_raw.encode("utf-8")).hexdigest()

    _live_cache_init()
    cached = _live_cache_get(cache_key)
    if cached:
        logger.info("Live cache hit")
        return cached

    logger.info(
        "Query for: %s/%s/%s/%s",
        (branche or "").lower(), (leistung or "").lower(),
        (bundesland or "").lower(), (unternehmensgroesse or "").lower(),
    )

    queries = _make_queries(branche or "", leistung or "", bundesland or "", unternehmensgroesse or "", lang)
    out: Dict[str, List[Dict[str, Any]]] = {"news": [], "tools": [], "funding": []}

    def run_provider(q: str, itype: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if SEARCH_PROVIDER in ("tavily", "hybrid"):
            results += _query_tavily(q, LIVE_MAX_RESULTS, LIVE_DAYS, itype_hint=itype)
        if SEARCH_PROVIDER in ("perplexity", "hybrid"):
            results += _query_perplexity(q, LIVE_MAX_RESULTS, itype_hint=itype)
        return results

    # Core channels
    for itype, qlist in queries.items():
        merged: List[Dict[str, Any]] = []
        for q in qlist:
            merged += run_provider(q, itype)
        merged = _rank(_dedupe(merged))
        out[itype] = merged[:LIVE_MAX_RESULTS]

    # Funding urgency
    out["funding"] = _mark_funding_urgency(out["funding"])

    # Optional channels
    if ENABLE_CASE_STUDIES:
        cs: List[Dict[str, Any]] = []
        for q in [f"{branche} KI Case Study 2025", f"{branche} KI Best Practice {COUNTRY_CODE}"]:
            cs += run_provider(q, "case_studies")
        out["case_studies"] = _rank(_dedupe(cs))[:LIVE_MAX_RESULTS]

    if ENABLE_REGULATORY:
        reg: List[Dict[str, Any]] = []
        for q in [f"AI Act guidance {COUNTRY_CODE}", "DSGVO KI Leitfaden 2025"]:
            reg += run_provider(q, "regulatory")
        out["regulatory"] = _rank(_dedupe(reg))[:LIVE_MAX_RESULTS]

    # Tools post-processing
    tools = out.get("tools", [])
    for t in tools:
        t["badges"] = _label_tool(t)
        t["category"] = _infer_tool_category(t.get("title", ""), t.get("summary", ""), branche)
        if ENABLE_EU_HOST_CHECK:
            info = _eu_host_info(t.get("url", ""))
            t["host_cc"] = info.get("cc", "")
            if info.get("eu") and "EU-Host" not in t["badges"]:
                t["badges"].append("EU-Host")

    out["vendor_shortlist"] = _build_vendor_shortlist(tools, branche, limit=5)
    out["tool_alternatives"] = _build_tool_alternatives(tools, branche, groups=5)

    _live_cache_set(cache_key, out)
    return out
