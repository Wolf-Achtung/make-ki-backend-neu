# File: websearch_utils.py
# -*- coding: utf-8 -*-
"""
Live-Suche (Tavily + Perplexity) mit:
- SQLite-Cache (TTL)
- EU-Host-Check (DNS+RDAP)
- Branchen-Heuristiken (Kategorie)
- Domain-Whitelists/Blacklists
- Ranking & Dedupe

Adressiert u. a. dein Log: Query für "///" führt zu generischen Treffern.
Mit Branchenfeldern liefert das deutlich bessere Ergebnisse. :contentReference[oaicite:7]{index=7}
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
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse

import httpx
from ipwhois import IPWhois  # type: ignore

try:
    import dns.resolver  # type: ignore
except Exception:
    dns = None  # type: ignore

logger = logging.getLogger("websearch_utils")
if not logger.handlers:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.getenv("CACHE_DIR", str(BASE_DIR / ".cache")))
LIVE_CACHE_PATH = Path(os.getenv("LIVE_CACHE_PATH", str(CACHE_DIR / "live_cache.sqlite")))
HOST_CACHE_PATH = Path(os.getenv("HOST_CACHE_PATH", str(CACHE_DIR / "host_cache.sqlite")))

LIVE_CACHE_ENABLED = os.getenv("LIVE_CACHE_ENABLED", "true").lower() == "true"
LIVE_CACHE_TTL_SECONDS = int(os.getenv("LIVE_CACHE_TTL_SECONDS", "7200"))
EU_HOST_TTL_SECONDS = int(os.getenv("EU_HOST_TTL_SECONDS", "604800"))
ENABLE_EU_HOST_CHECK = os.getenv("ENABLE_EU_HOST_CHECK", "true").lower() == "true"

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "hybrid").lower()
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
COUNTRY_CODE = os.getenv("COUNTRY_CODE", "DE").upper()
LIVE_MAX_RESULTS = int(os.getenv("LIVE_MAX_RESULTS", "10"))
LIVE_DAYS = int(os.getenv("LIVE_DAYS", "45"))
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "18.0"))

ENABLE_CASE_STUDIES = os.getenv("ENABLE_CASE_STUDIES", "true").lower() == "true"
ENABLE_REGULATORY = os.getenv("ENABLE_REGULATORY", "true").lower() == "true"

NEWS_INCLUDE = [d.strip() for d in os.getenv("NEWS_INCLUDE_DOMAINS", "").split(",") if d.strip()]
FUNDING_INCLUDE = [
    d.strip()
    for d in (
        os.getenv(
            "FUNDING_INCLUDE_DOMAINS",
            "bund.de,foerderdatenbank.de,bmwk.de,bafa.de,ec.europa.eu,europa.eu,bmbf.de",
        ).split(",")
    )
    if d.strip()
]
TOOLS_EXCLUDE = [
    d.strip()
    for d in os.getenv(
        "TOOLS_EXCLUDE_DOMAINS",
        "medium.com,linkedin.com,twitter.com,x.com,youtube.com,reddit.com,markopolo.ai,digitaldefynd.com",
    ).split(",")
    if d.strip()
]

EU_TLDS = {
    "at",
    "be",
    "bg",
    "hr",
    "cy",
    "cz",
    "dk",
    "ee",
    "fi",
    "fr",
    "de",
    "gr",
    "hu",
    "ie",
    "it",
    "lv",
    "lt",
    "lu",
    "mt",
    "nl",
    "pl",
    "pt",
    "ro",
    "sk",
    "si",
    "es",
    "se",
    "eu",
}
EU_COUNTRIES = {
    "AT",
    "BE",
    "BG",
    "HR",
    "CY",
    "CZ",
    "DK",
    "EE",
    "FI",
    "FR",
    "DE",
    "GR",
    "HU",
    "IE",
    "IT",
    "LV",
    "LT",
    "LU",
    "MT",
    "NL",
    "PL",
    "PT",
    "RO",
    "SK",
    "SI",
    "ES",
    "SE",
}


def _sql_init(path: Path, ddl: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(path)) as con:
            con.executescript(ddl)
            con.commit()
    except Exception as e:
        logger.warning("SQLite init failed for %s: %s", path, e)


def _live_cache_init() -> None:
    if LIVE_CACHE_ENABLED:
        _sql_init(
            LIVE_CACHE_PATH,
            "CREATE TABLE IF NOT EXISTS live_cache (key TEXT PRIMARY KEY, payload TEXT, created_at INTEGER);",
        )


def _host_cache_init() -> None:
    if ENABLE_EU_HOST_CHECK:
        _sql_init(
            HOST_CACHE_PATH,
            "CREATE TABLE IF NOT EXISTS host_cache (domain TEXT PRIMARY KEY, cc TEXT, ip TEXT, created_at INTEGER);",
        )


def _live_cache_get(key: str) -> Optional[Dict[str, Any]]:
    if not (LIVE_CACHE_ENABLED and LIVE_CACHE_PATH.exists()):
        return None
    try:
        with sqlite3.connect(str(LIVE_CACHE_PATH)) as con:
            row = con.execute("SELECT payload,created_at FROM live_cache WHERE key=?", (key,)).fetchone()
            if not row:
                return None
            payload, created_at = row
            if int(time.time()) - int(created_at) > LIVE_CACHE_TTL_SECONDS:
                return None
            return json.loads(payload)
    except Exception:
        return None


def _live_cache_set(key: str, payload: Mapping[str, Any]) -> None:
    if not LIVE_CACHE_ENABLED:
        return
    try:
        with sqlite3.connect(str(LIVE_CACHE_PATH)) as con:
            con.execute(
                "INSERT OR REPLACE INTO live_cache (key,payload,created_at) VALUES (?,?,?)",
                (key, json.dumps(payload, ensure_ascii=False), int(time.time())),
            )
            con.commit()
    except Exception:
        pass


def _host_cache_get(domain: str) -> Optional[tuple]:
    if not (ENABLE_EU_HOST_CHECK and HOST_CACHE_PATH.exists()):
        return None
    try:
        with sqlite3.connect(str(HOST_CACHE_PATH)) as con:
            row = con.execute("SELECT cc,ip,created_at FROM host_cache WHERE domain=?", (domain,)).fetchone()
            if not row:
                return None
            cc, ip, created = row
            if int(time.time()) - int(created) > EU_HOST_TTL_SECONDS:
                return None
            return cc, ip
    except Exception:
        return None


def _host_cache_set(domain: str, cc: str, ip: str) -> None:
    if not ENABLE_EU_HOST_CHECK:
        return
    try:
        with sqlite3.connect(str(HOST_CACHE_PATH)) as con:
            con.execute(
                "INSERT OR REPLACE INTO host_cache (domain,cc,ip,created_at) VALUES (?,?,?,?)",
                (domain, cc, ip, int(time.time())),
            )
            con.commit()
    except Exception:
        pass


def _escape(s: Any) -> str:
    return "" if s is None else html.escape(str(s).strip(), quote=True)


def _safe_url(u: Any) -> str:
    u = str(u or "").strip()
    return u if u and re.match(r"^https?://", u, flags=re.I) else ""


def _extract_domain(u: str) -> str:
    try:
        d = urlparse(u).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


def _resolve_ips(domain: str) -> List[str]:
    ips: List[str] = []
    try:
        infos = socket.getaddrinfo(domain, 80, proto=socket.IPPROTO_TCP)
        for _, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            if ":" not in ip:
                ips.append(ip)
    except Exception:
        pass
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
        cc = (data.get("asn_country_code") or (data.get("network") or {}).get("country") or "")
        return (cc or "").upper()
    except Exception:
        return ""


def _eu_host_info(url: str) -> Dict[str, Any]:
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
    if not cc and "." in domain:
        tld = domain.split(".")[-1].lower()
        if tld in EU_TLDS:
            cc = tld.upper()
    _host_cache_set(domain, cc, ip_hit)
    return {"domain": domain, "ip": ip_hit, "cc": cc, "eu": cc in EU_COUNTRIES}


def _normalize_item(title, url, summary="", published_at="", source="", itype="") -> Dict[str, Any]:
    t = _escape(title)
    u = _safe_url(url)
    s = _escape(summary)[:300]
    p = str(published_at or "").strip()
    if p and not re.search(r"\d{4}-\d{2}-\d{2}", p):
        p = ""
    return {"title": t or "", "url": u, "summary": s, "published_at": p, "source": (source or "").strip()[:120], "type": itype}


def _domain_score(domain: str, itype: str) -> float:
    if not domain:
        return 0.0
    if itype == "funding" and any(domain.endswith(d) or domain == d for d in FUNDING_INCLUDE):
        return 2.5
    if itype == "tools" and any(domain.endswith(d) or domain == d for d in TOOLS_EXCLUDE):
        return -1.0
    if itype == "news" and NEWS_INCLUDE and any(domain.endswith(d) or domain == d for d in NEWS_INCLUDE):
        return 1.0
    return 0.0


def _rank(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    type_weight = {"news": 3, "funding": 2, "tools": 1, "regulatory": 2, "case_studies": 1}

    def score(it: Dict[str, Any]) -> float:
        w = type_weight.get(it.get("type", ""), 0)
        rec = 0.5
        try:
            dt = datetime.fromisoformat(it.get("published_at", "").replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            rec = max(0, LIVE_DAYS - age_days) / LIVE_DAYS
        except Exception:
            pass
        ds = _domain_score(_extract_domain(it.get("url", "")), it.get("type", ""))
        return w + rec + ds

    return sorted(items, key=score, reverse=True)


def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        key = (it.get("title", "").lower(), it.get("url", "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _query_tavily(q: str, max_results: int, days: int, itype_hint: str = "", include_domains=None, exclude_domains=None) -> List[Dict[str, Any]]:
    if not TAVILY_API_KEY:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": q,
        "search_depth": "advanced",
        "max_results": max(1, min(max_results, 20)),
        "days": max(1, min(days, 365)),
        "include_answer": False,
        "include_raw_content": False,
        "topic": "general",
        "include_domains": include_domains or [],
        "exclude_domains": exclude_domains or [],
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


def _query_perplexity(q: str, max_results: int, itype_hint: str = "") -> List[Dict[str, Any]]:
    if not PERPLEXITY_API_KEY:
        return []
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    prompt = (
        "Return a concise JSON array: "
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
    # JSON extrahieren
    items: List[Dict[str, Any]] = []
    try:
        arr = json.loads(text)
        if isinstance(arr, list):
            for it in arr[:max_results]:
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


INDUSTRY_TUNING = {
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


def _label_tool(item: Dict[str, Any]) -> List[str]:
    lbl: List[str] = []
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    u = item.get("url", "").lower()
    domain = _extract_domain(u)
    if "open source" in text or "opensource" in text or "self-host" in text or "github.com" in u:
        lbl.append("Open-Source")
    if "gdpr" in text or "dsgvo" in text:
        lbl.append("DSGVO")
    if domain.split(".")[-1] in EU_TLDS:
        lbl.append("EU")
    if "api" in text:
        lbl.append("API")
    if "free" in text or "kostenlos" in text or "gratis" in text:
        lbl.append("Free")
    return lbl


def _infer_tool_category(title: str, summary: str, branche: str = "") -> str:
    text = f"{title} {summary}".lower()
    base = {
        "documentation": ["doc", "doku", "knowledge", "wiki", "handbook"],
        "analytics": ["analytics", "analyse", "insights", "tracking", "metrics", "bi"],
        "automation": ["automation", "workflow", "rpa", "automatisierung", "pipeline", "orchestr"],
        "chatbot": ["chatbot", "assistant", "copilot", "conversational"],
        "vision": ["video", "image", "vision", "schnitt", "subtitle", "ocr"],
        "nlp": ["text", "prompt", "summar", "transkript", "speech", "asr"],
        "dev": ["code", "testing", "lint", "deploy", "ci", "cd", "repository"],
        "security": ["security", "sicherheit", "privacy", "encryption"],
        "compliance": ["compliance", "ai act", "dsgvo", "gdpr"],
        "search": ["search", "suche", "retrieval", "rag", "index"],
        "marketing": ["ads", "kampagne", "seo", "content", "social"],
        "crm": ["crm", "kund", "sales", "pipeline"],
        "finance": ["invoice", "finanz", "buchhaltung", "abrechnung"],
        "hr": ["hr", "bewerb", "recruit", "talent"],
        "support": ["ticket", "support", "helpdesk"],
    }
    scores = {k: 0.0 for k in base}
    for cat, keys in base.items():
        for k in keys:
            if k in text:
                scores[cat] += 1.0
    b = (branche or "").lower()
    for key, pref in INDUSTRY_TUNING.items():
        if key in b:
            for i, cat in enumerate(pref[:5]):
                scores[cat] = scores.get(cat, 0.0) + (0.30 - i * 0.05)
            break
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "general"


def _filter_tools(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in items:
        d = _extract_domain(it.get("url", ""))
        if any(d.endswith(x) or d == x for x in TOOLS_EXCLUDE):
            continue
        title = (it.get("title", "") or "").lower()
        if any(w in title for w in ["leitfaden", "case study", "studie", "news", "überblick", "overview"]):
            continue
        out.append(it)
    return out


def _make_queries(branche: str, leistung: str, bundesland: str, size: str, lang: str) -> Dict[str, List[str]]:
    b = (branche or "").strip()
    l = (leistung or "").strip()
    bl = (bundesland or "").strip()
    s = (size or "").strip()
    if lang == "de":
        news_q = [f"{b} KI Nachrichten {COUNTRY_CODE} letzte {LIVE_DAYS} Tage", f"{b} {l} KI Praxisbeispiele {COUNTRY_CODE}"]
        tools_q = [f"KI Tools für {b} {s} DSGVO-konform", f"Open-Source KI Tools {b} 2025"]
        funding_q = [f"{COUNTRY_CODE} {bl} Förderprogramme KI KMU Frist", f"{COUNTRY_CODE} Innovationsförderung KI Mittelstand"]
    else:
        news_q = [f"{b} AI news {COUNTRY_CODE} last {LIVE_DAYS} days", f"{b} {l} AI case studies {COUNTRY_CODE}"]
        tools_q = [f"best AI tools for {b} {s} company 2025 GDPR-friendly", f"{b} {l} open source AI tools 2025"]
        funding_q = [f"{COUNTRY_CODE} {bl} AI grants SME deadline", f"{COUNTRY_CODE} innovation grant AI small business"]
    return {"news": news_q, "tools": tools_q, "funding": funding_q}


def query_live_items(branche: Optional[str] = "", unternehmensgroesse: Optional[str] = "", leistung: Optional[str] = "", bundesland: Optional[str] = "", lang: Optional[str] = "de") -> Dict[str, List[Dict[str, Any]]]:
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
            "fw": ",".join(FUNDING_INCLUDE),
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

    logger.info("Query for: %s/%s/%s/%s", (branche or "").lower(), (leistung or "").lower(), (bundesland or "").lower(), (unternehmensgroesse or "").lower())
    queries = _make_queries(branche or "", leistung or "", bundesland or "", unternehmensgroesse or "", lang)
    out: Dict[str, List[Dict[str, Any]]] = {"news": [], "tools": [], "funding": []}

    def run_provider(q: str, itype: str) -> List[Dict[str, Any]]:
        inc = FUNDING_INCLUDE if itype == "funding" else (NEWS_INCLUDE if itype == "news" and NEWS_INCLUDE else None)
        exc = TOOLS_EXCLUDE if itype == "tools" else None
        results: List[Dict[str, Any]] = []
        if SEARCH_PROVIDER in ("tavily", "hybrid"):
            results += _query_tavily(q, LIVE_MAX_RESULTS, LIVE_DAYS, itype_hint=itype, include_domains=inc, exclude_domains=exc)
        if SEARCH_PROVIDER in ("perplexity", "hybrid"):
            results += _query_perplexity(q, LIVE_MAX_RESULTS, itype_hint=itype)
        return results

    for itype, qlist in queries.items():
        merged: List[Dict[str, Any]] = []
        for q in qlist:
            merged += run_provider(q, itype)
        merged = _dedupe(merged)
        if itype == "tools":
            merged = _filter_tools(merged)
        out[itype] = _rank(merged)[:LIVE_MAX_RESULTS]

    # Funding: Deadline-Badges
    out["funding"] = _mark_funding_urgency(out["funding"])

    # Optionals
    if ENABLE_CASE_STUDIES:
        cs = []
        for q in [f"{branche} KI Case Study 2025", f"{branche} KI Best Practice {COUNTRY_CODE}"]:
            cs += run_provider(q, "case_studies")
        out["case_studies"] = _rank(_dedupe(cs))[:LIVE_MAX_RESULTS]
    if ENABLE_REGULATORY:
        reg = []
        for q in ["AI Act guidance " + COUNTRY_CODE, "DSGVO KI Leitfaden 2025"]:
            reg += run_provider(q, "regulatory")
        out["regulatory"] = _rank(_dedupe(reg))[:LIVE_MAX_RESULTS]

    # Tool-Badges + EU-Host
    for t in out.get("tools", []):
        t["badges"] = _label_tool(t)
        t["category"] = _infer_tool_category(t.get("title", ""), t.get("summary", ""), branche or "")
        if ENABLE_EU_HOST_CHECK:
            info = _eu_host_info(t.get("url", ""))
            t["host_cc"] = info.get("cc", "")
            if info.get("eu") and "EU-Host" not in t["badges"]:
                t["badges"].append("EU-Host")

    out["vendor_shortlist"] = out["tools"][:5]
    out["tool_alternatives"] = out["tools"][:5]

    _live_cache_set(cache_key, out)
    return out


# --- Funding-Helpers ----------------------------------------------------------

def _parse_date_any(text: str):
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
        text = f"{it.get('title','')} {it.get('summary','')}"
        dline = _parse_date_any(text)
        it = dict(it)
        it["badges"] = it.get("badges", [])
        if dline:
            days = (dline - datetime.now()).days
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
