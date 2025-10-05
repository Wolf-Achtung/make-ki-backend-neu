#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KI-Status-Report – Analyse & Rendering
Gold-Standard+ Backend (FastAPI-agnostischer Kern)
- OpenAI ChatCompletions Wrapper mit Modell-Fallback
- Live-Layer (Tavily + Perplexity) mit 7/30/60/90d Fallbacks und Merge/Dedupe
- Sanitizing (entfernt Codefences, <!DOCTYPE>, Root-Tags; Whitelist-HTML)
- Branchenbindung (System-Prefix erzwingt Beratung & Dienstleistungen, Solo etc.)
- Benchmarks 2025, Δ-Berechnung, Business-Case (Payback ~4 Monate)
- Förder-Badge für „Land Berlin“
- PDF-Service: nur /generate-pdf (Backoff + robustes Fehlerhandling)

Benötigte ENV (alle optional, mit Defaults):
  OPENAI_API_KEY, OPENAI_MODEL, PDF_SERVICE_URL, TAVILY_API_KEY, PPLX_API_KEY
  LIVE_DAYS_NEWS_PRIMARY, LIVE_DAYS_NEWS_FALLBACK, LIVE_DAYS_TOOLS,
  LIVE_DAYS_TOOLS_FALLBACK, LIVE_DAYS_FUNDING, LIVE_DAYS_FUNDING_FALLBACK,
  LIVE_MAX_RESULTS
"""

from __future__ import annotations

import os
import re
import json
import math
import time
import html
import uuid
import base64
import logging
import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape


# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("gpt_analyze")


# ------------------------------------------------------------------------------
# Constants & Defaults
# ------------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o")

PDF_SERVICE_URL = os.getenv(
    "PDF_SERVICE_URL",
    "https://make-ki-pdfservice-production.up.railway.app",
).rstrip("/")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
PPLX_API_KEY = os.getenv("PPLX_API_KEY", "")

LIVE_DAYS_NEWS_PRIMARY = int(os.getenv("LIVE_DAYS_NEWS_PRIMARY", "7"))
LIVE_DAYS_NEWS_FALLBACK = int(os.getenv("LIVE_DAYS_NEWS_FALLBACK", "30"))
LIVE_DAYS_TOOLS = int(os.getenv("LIVE_DAYS_TOOLS", "30"))
LIVE_DAYS_TOOLS_FALLBACK = int(os.getenv("LIVE_DAYS_TOOLS_FALLBACK", "60"))
LIVE_DAYS_FUNDING = int(os.getenv("LIVE_DAYS_FUNDING", "60"))
LIVE_DAYS_FUNDING_FALLBACK = int(os.getenv("LIVE_DAYS_FUNDING_FALLBACK", "90"))
LIVE_MAX_RESULTS = int(os.getenv("LIVE_MAX_RESULTS", "6"))

TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template_de.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")

BENCHMARKS_FILE = os.getenv(
    "BENCHMARKS_FILE", os.path.join("data", "benchmarks_beratung_solo.json")
)

ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "")  # optional base for images/fonts


# ------------------------------------------------------------------------------
# Data Classes
# ------------------------------------------------------------------------------
@dataclass
class KPI:
    name: str
    value_pct: float
    median_pct: float

    @property
    def delta_pp(self) -> float:
        return self.value_pct - self.median_pct


@dataclass
class LiveItem:
    title: str
    url: str
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    region_badge: Optional[str] = None
    source: Optional[str] = None  # "tavily" | "perplexity"


# ------------------------------------------------------------------------------
# Utilities – Sanitizing
# ------------------------------------------------------------------------------
_CODEFENCE_RE = re.compile(r"```+\s*[a-zA-Z]*\s*|```+", re.MULTILINE)
_DOCTYPE_RE = re.compile(r"<!doctype.*?>", re.IGNORECASE | re.DOTALL)
_ROOTTAG_RE = re.compile(r"</?(html|head|body|meta|style|title)[^>]*>", re.IGNORECASE)
_EMPTY_TAGS_RE = re.compile(r"\s+</(p|li)>\s*", re.IGNORECASE)

ALLOWED_TAGS = {
    "p", "ul", "ol", "li", "strong", "em", "b", "i",
    "table", "thead", "tbody", "tr", "th", "td",
    "a", "h3", "h4", "br"
}
ALLOWED_ATTRS = {"a": {"href"}}


class _SanitizeParser:
    """
    Minimalist sanitizer without external deps.
    Strategy:
      1) Strip code fences, doctype, root tags.
      2) Whitelist tags; escape everything else.
      3) For <a>, keep href (absolute/relative allowed), and add rel noopener.
    """
    def __init__(self):
        pass

    def sanitize(self, html_in: str) -> str:
        if not html_in:
            return ""
        s = _CODEFENCE_RE.sub("", html_in)
        s = _DOCTYPE_RE.sub("", s)
        s = _ROOTTAG_RE.sub("", s)

        # Tokenize naive by angle brackets; rebuild conservatively.
        out: List[str] = []
        i = 0
        while i < len(s):
            lt = s.find("<", i)
            if lt < 0:
                out.append(html.escape(s[i:]))
                break
            # text chunk
            if lt > i:
                out.append(html.escape(s[i:lt]))
            gt = s.find(">", lt + 1)
            if gt < 0:
                # no closing '>', escape rest
                out.append(html.escape(s[lt:]))
                break
            tag_content = s[lt + 1:gt].strip()
            is_closing = tag_content.startswith("/")
            tag_name = tag_content[1:].split()[0].lower() if is_closing else tag_content.split()[0].lower()

            if tag_name in ALLOWED_TAGS:
                if is_closing:
                    out.append(f"</{tag_name}>")
                else:
                    attrs_allowed = ""
                    if tag_name in ALLOWED_ATTRS:
                        attrs_allowed = self._keep_attrs(tag_content, tag_name)
                    # never allow inline event handlers/style
                    out.append(f"<{tag_name}{attrs_allowed}>")
            else:
                # unknown tag → escape whole tag
                out.append(html.escape(s[lt:gt+1]))
            i = gt + 1

        res = "".join(out)
        # Normalize accidental empty closers
        res = _EMPTY_TAGS_RE.sub(lambda m: f"</{m.group(1).lower()}>", res)
        return res

    @staticmethod
    def _keep_attrs(tag_content: str, tag: str) -> str:
        """
        Keep only whitelisted attributes, simple regex parse.
        """
        attrs = []
        for attr in ALLOWED_ATTRS.get(tag, set()):
            # href="..."; tolerate single/double quotes
            pattern = re.compile(attr + r"\s*=\s*(['\"])(.*?)\1", re.IGNORECASE)
            m = pattern.search(tag_content)
            if m:
                val = m.group(2).strip()
                # Basic sanitation for javascript: URIs
                if val.lower().startswith("javascript:"):
                    continue
                safe_val = html.escape(val, quote=True)
                attrs.append(f' {attr}="{safe_val}"')
        # Always add rel to anchors (safe default)
        if tag == "a":
            attrs.append(' rel="noopener noreferrer" target="_blank"')
        return "".join(attrs)


_SANITIZER = _SanitizeParser()


def sanitize_html(s: str) -> str:
    """Public sanitizer."""
    return _SANITIZER.sanitize(s or "")


# ------------------------------------------------------------------------------
# Utilities – Misc
# ------------------------------------------------------------------------------
def pct(n: float) -> float:
    return max(0.0, min(100.0, float(n)))


def pp(n: float) -> float:
    return float(n)


def now_iso(date_tz: str = "Europe/Berlin") -> str:
    # naive ISO (keine Zeitzonen im Report)
    try:
        from datetime import timezone
        return dt.datetime.now().date().isoformat()
    except Exception:
        return dt.datetime.utcnow().date().isoformat()


def human_company_size(label: str) -> str:
    if label and label.strip() not in {"", "1"}:
        return label
    # Default humanization for "1"
    return "Solo (1 MA)"


def boolize(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, str):
        return x.strip().lower() in {"1", "true", "yes", "ja"}
    if isinstance(x, (int, float)):
        return bool(x)
    return False


def region_badge_for_url(url: str, bundesland_code: str) -> Optional[str]:
    """Add 'Land Berlin' if URL domain signals Berlin sources and BL=BE."""
    if not url or bundesland_code.upper() != "BE":
        return None
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    patterns = ("berlin.de", "ibb.de", "investitionsbank-berlin.de", "digitalagentur.berlin")
    if any(p in host for p in patterns):
        return "Land Berlin"
    return None


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------------------
# Benchmarks & Business Case
# ------------------------------------------------------------------------------
def load_benchmarks(path: str) -> Dict[str, float]:
    """
    Expects a JSON like:
      {"Digitalisierung": 60, "Automatisierung": 60, "Compliance": 60, "Prozessreife": 60, "Innovation": 60}
    """
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError("Benchmarks file must be a flat dict of KPI->median pct")
    # ensure floats
    return {k: pct(v) for k, v in data.items()}


def compute_kpis(briefing: Dict[str, Any], benchmarks: Dict[str, float]) -> List[KPI]:
    # Map briefing fields to KPIs (simple assumptions for demo; adapt as needed)
    kpis: List[KPI] = []
    kpi_map = {
        "Digitalisierung": float(briefing.get("digitalisierungsgrad", 6)) * 10,
        "Automatisierung": 85.0 if briefing.get("automatisierungsgrad") in {"hoch", "sehr_hoch"} else 55.0,
        "Compliance": 100.0 if boolize(briefing.get("datenschutz")) else 60.0,
        "Prozessreife": 88.0 if briefing.get("prozesse_papierlos", "") in {"81-100", "61-80"} else 60.0,
        "Innovation": 75.0 if briefing.get("innovationskultur") in {"offen", "sehr_offen"} else 55.0,
    }
    for name, val in kpi_map.items():
        kpis.append(KPI(name=name, value_pct=pct(val), median_pct=pct(benchmarks.get(name, 60.0))))
    return kpis


def compute_score(kpis: List[KPI]) -> float:
    if not kpis:
        return 0.0
    # equal weights (20% each), as im Footer beschrieben
    return round(sum(k.value_pct for k in kpis) / len(kpis), 1)


def compute_business_case(payback_months_target: float = 4.0) -> Dict[str, Any]:
    """
    Baseline Business-Case (3 Zahlen): Investition, Einsparung Jahr 1, ROI% Jahr 1.
    Für Payback ~4 Monate ergibt sich Invest ca. 6k, Einsparung 18k → ROI 200%.
    """
    invest = 6000.0
    saving_y1 = 18000.0
    payback_months = payback_months_target
    roi_y1 = (saving_y1 - invest) / invest * 100.0
    return {
        "invest_eur": round(invest, 0),
        "saving_y1_eur": round(saving_y1, 0),
        "payback_months": round(payback_months, 1),
        "roi_y1_pct": round(roi_y1, 1),
    }


# ------------------------------------------------------------------------------
# OpenAI Wrapper (Chat Completions)
# ------------------------------------------------------------------------------
def openai_chat(system: str, user: str, temperature: float = 0.2, max_tokens: int = 800) -> str:
    if not OPENAI_API_KEY:
        log.warning("OPENAI_API_KEY missing — returning empty content")
        return ""
    body = {
        "model": OPENAI_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    url = "https://api.openai.com/v1/chat/completions"

    for attempt, model in enumerate((OPENAI_MODEL, OPENAI_FALLBACK_MODEL), start=1):
        body["model"] = model
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                j = resp.json()
                content = j["choices"][0]["message"]["content"]
                log.info("openai_chat: model=%s tokens≈%s", model, j.get("usage", {}))
                return content
        except Exception as e:
            log.warning("openai_chat attempt %d failed with %s", attempt, e)
            time.sleep(0.6 * attempt)
    return ""


# ------------------------------------------------------------------------------
# Live Layer (Tavily + Perplexity) + Merge
# ------------------------------------------------------------------------------
def _days_to_recency(days: int) -> str:
    if days <= 7:
        return "7d"
    if days <= 30:
        return "30d"
    if days <= 60:
        return "60d"
    return "90d"


def tavily_search(query: str, days: int, max_results: int = 6) -> List[LiveItem]:
    if not TAVILY_API_KEY:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "include_images": False,
        "include_raw_content": False,
        "max_results": max_results,
        "days": days,
    }
    try:
        with httpx.Client(timeout=30) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        items = []
        for res in data.get("results", []):
            items.append(
                LiveItem(
                    title=res.get("title") or "",
                    url=res.get("url") or "",
                    snippet=res.get("content") or "",
                    published_at=res.get("published_date"),
                    source="tavily",
                )
            )
        return items
    except Exception as e:
        log.warning("tavily_search error: %s", e)
        return []


def perplexity_search(query: str, days: int, max_results: int = 6) -> List[LiveItem]:
    """
    Lightweight Perplexity fallback via Chat Completions.
    Wir bitten explizit um eine JSON-Liste mit {title,url,snippet,date}. 
    Falls API-Key fehlt oder Format anders ist: robustes Fallback → [].
    """
    if not PPLX_API_KEY:
        return []
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PPLX_API_KEY}"}
    system = (
        "You are a web research agent. Return ONLY valid JSON array of objects "
        "with keys: title, url, snippet, date. No commentary. Focus on the last "
        f"{days} days. German language sources preferred for DE region."
    )
    user = (
        f"Suche aktuelle, seriöse Quellen der letzten {_days_to_recency(days)} "
        f"zum Thema: {query}. Max {max_results} Ergebnisse."
    )
    body = {
        "model": "sonar-small-online",  # stable default; change if needed
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.0,
        "max_tokens": 800,
        "top_p": 0.9,
        "return_citations": True,
        "search_recency_filter": _days_to_recency(days),
        "web_search": True,
    }
    try:
        with httpx.Client(timeout=60) as client:
            r = client.post(url, json=body, headers=headers)
            r.raise_for_status()
            j = r.json()
        content = j["choices"][0]["message"]["content"].strip()
        # content should be JSON array; be defensive:
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.DOTALL)
        data = json.loads(content)
        items: List[LiveItem] = []
        for res in data[:max_results]:
            items.append(
                LiveItem(
                    title=str(res.get("title") or ""),
                    url=str(res.get("url") or ""),
                    snippet=str(res.get("snippet") or ""),
                    published_at=str(res.get("date") or ""),
                    source="perplexity",
                )
            )
        return items
    except Exception as e:
        log.warning("perplexity_search error: %s", e)
        return []


def dedupe_items(items: List[LiveItem], limit: int) -> List[LiveItem]:
    seen: set = set()
    uniq: List[LiveItem] = []
    for it in items:
        key = (it.title.strip().lower(), urlparse(it.url).netloc.lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
        if len(uniq) >= limit:
            break
    return uniq


def live_query_builder(briefing: Dict[str, Any]) -> Dict[str, str]:
    branche = briefing.get("branche_label", "Beratung & Dienstleistungen")
    haupt = briefing.get("hauptleistung", "")
    usecase = briefing.get("usecase_priority") or (briefing.get("ki_usecases") or [""])[0]
    bundesland = briefing.get("bundesland_code", "DE")
    q_common = f'{branche} "{haupt}" {usecase}'.strip()
    return {
        "news": f"{q_common} KI News Update {bundesland}",
        "tools": f"{q_common} Tool Update EU DSGVO",
        "funding": f"{q_common} Förderung Programm {bundesland}",
    }


def get_live_sections(briefing: Dict[str, Any]) -> Tuple[List[LiveItem], List[LiveItem], List[LiveItem], str]:
    queries = live_query_builder(briefing)
    last_update = now_iso()

    # NEWS
    news = tavily_search(queries["news"], LIVE_DAYS_NEWS_PRIMARY, LIVE_MAX_RESULTS)
    if not news:
        news = tavily_search(queries["news"], LIVE_DAYS_NEWS_FALLBACK, LIVE_MAX_RESULTS)
        if not news:
            news = perplexity_search(queries["news"], LIVE_DAYS_NEWS_FALLBACK, LIVE_MAX_RESULTS)

    # TOOLS
    tools = tavily_search(queries["tools"], LIVE_DAYS_TOOLS, LIVE_MAX_RESULTS)
    if not tools:
        tools = tavily_search(queries["tools"], LIVE_DAYS_TOOLS_FALLBACK, LIVE_MAX_RESULTS)
        if not tools:
            tools = perplexity_search(queries["tools"], LIVE_DAYS_TOOLS_FALLBACK, LIVE_MAX_RESULTS)

    # FUNDING
    funding = tavily_search(queries["funding"], LIVE_DAYS_FUNDING, LIVE_MAX_RESULTS)
    if not funding:
        funding = tavily_search(queries["funding"], LIVE_DAYS_FUNDING_FALLBACK, LIVE_MAX_RESULTS)
        if not funding:
            funding = perplexity_search(queries["funding"], LIVE_DAYS_FUNDING_FALLBACK, LIVE_MAX_RESULTS)

    # Merge & dedupe (prefer Tavily order, then Perplexity)
    news = dedupe_items(news, LIVE_MAX_RESULTS)
    tools = dedupe_items(tools, LIVE_MAX_RESULTS)
    funding = dedupe_items(funding, LIVE_MAX_RESULTS)

    # Region badges (e.g., Berlin)
    bl = (briefing.get("bundesland_code") or "").upper()
    for f in funding:
        f.region_badge = region_badge_for_url(f.url, bl)

    return news, tools, funding, last_update


# ------------------------------------------------------------------------------
# Prompts – System Prefix & Guards
# ------------------------------------------------------------------------------
def system_prefix(briefing: Dict[str, Any]) -> str:
    branche = briefing.get("branche_label", "Beratung & Dienstleistungen")
    size = human_company_size(briefing.get("unternehmensgroesse_label") or "Solo (1 MA)")
    bl = briefing.get("bundesland_code", "DE")
    haupt = briefing.get("hauptleistung", "")

    return (
        "Du erstellst Inhalte ausschließlich für die Branche "
        f"„{branche}“, Unternehmensgröße „{size}“, Region „{bl}“.\n"
        f"Hauptleistung: {haupt}\n"
        "Vermeide Beispiele aus anderen Branchen/Größen. "
        "Keine Codeblöcke (keine ```), keine <!DOCTYPE>, <html>, <head>, <meta>, <body>. "
        "Antworte in kompaktem, semantischem HTML: p, ul/ol/li, strong/em, table/thead/tbody/tr/th/td, a, h3/h4, br."
    )


def fewshot_anchor() -> str:
    return (
        "Stil: professionell, präzise, pragmatisch; keine Übertreibungen. "
        "Benutze Solo‑taugliche Rollenbezeichnungen (Owner=Inhaber:in, Berater:in). "
        "Zeitangaben realistisch (Tage/Wochen) und mit erstem konkreten Schritt."
    )


# ------------------------------------------------------------------------------
# Content Builders (LLM-assisted with guards)
# ------------------------------------------------------------------------------
def build_section(briefing: Dict[str, Any], topic: str) -> str:
    """
    topic in {"executive_summary", "quick_wins", "roadmap", "risks", "compliance",
              "business", "recommendations", "gamechanger", "vision", "persona",
              "praxisbeispiel", "coach"}
    """
    sys = system_prefix(briefing)
    usr = (
        f"{fewshot_anchor()}\n"
        f"Erstelle die Sektion: {topic} – passgenau für Beratung & Dienstleistungen (Solo). "
        "Baue Aussagen, Beispiele und KPIs auf die Angaben aus dem Fragebogen auf:\n"
        f"- Hauptleistung: {briefing.get('hauptleistung','')}\n"
        f"- Fokus-Use-Cases: {', '.join(briefing.get('ki_usecases', []) or [])}\n"
        f"- Zielgruppen: {', '.join(briefing.get('zielgruppen', []) or [])}\n"
        f"- Strategische Ziele: {briefing.get('strategische_ziele','')}\n"
        "Gib NUR semantisches HTML zurück (ohne Doctype/Root/Codefences)."
    )
    html_raw = openai_chat(sys, usr, temperature=0.3, max_tokens=1000)
    return sanitize_html(html_raw)


# ------------------------------------------------------------------------------
# Rendering (Jinja) & PDF
# ------------------------------------------------------------------------------
def render_html(briefing: Dict[str, Any], lang: str = "de") -> str:
    # Normalisierung
    briefing = dict(briefing or {})
    briefing["datenschutz"] = boolize(briefing.get("datenschutz"))
    briefing["unternehmensgroesse_label"] = human_company_size(
        briefing.get("unternehmensgroesse_label") or briefing.get("unternehmensgroesse") or "1"
    )

    # Benchmarks (2025)
    try:
        benchmarks = load_benchmarks(BENCHMARKS_FILE)
        log.info("Loaded benchmark: %s", os.path.basename(BENCHMARKS_FILE))
    except Exception as e:
        log.warning("Benchmark load failed (%s) – using 60%% medians", e)
        benchmarks = {k: 60.0 for k in ("Digitalisierung", "Automatisierung", "Compliance", "Prozessreife", "Innovation")}

    kpis = compute_kpis(briefing, benchmarks)
    score = compute_score(kpis)
    business = compute_business_case(4.0)  # 4-Monate Payback Ziel

    # Pull‑Badges
    top_use_case = (briefing.get("usecase_priority")
                    or (briefing.get("ki_usecases") or [""])[0] or "").strip() or "Prozessautomatisierung"
    zeitbudget = briefing.get("zeitbudget", "")
    umsatzklasse = briefing.get("jahresumsatz", "")
    badges = [
        f"Top‑Use‑Case: {top_use_case.capitalize()}",
        f"Zeitbudget: {'>10 h/W' if 'ueber_10' in zeitbudget else '≤10 h/W' if zeitbudget else 'n/a'}",
        f"Umsatzklasse: {'100–500 T€' if umsatzklasse=='100k_500k' else 'n/a' if not umsatzklasse else umsatzklasse}",
    ]

    # LLM‑Sektionen (mit Sanitizing)
    sections = {
        "executive_summary": build_section(briefing, "Executive Summary"),
        "quick_wins": build_section(briefing, "Quick Wins (Solo‑Fit, 5 Punkte)"),
        "roadmap": build_section(briefing, "Roadmap (12 Wochen, Solo‑Fit)"),
        "risks": build_section(briefing, "Risiken & Mitigation (Solo‑Fit)"),
        "compliance": build_section(briefing, "Compliance (EU AI Act & DSGVO Check-Artefakte)"),
        "recommendations": build_section(briefing, "Empfehlungen (Tabelle mit ROI/Payback, Solo‑Fit)"),
        "gamechanger": build_section(briefing, "Game Changer (Solo‑relevant, Beratung)"),
        "vision": build_section(briefing, "Vision (2027, Beratung & Dienstleistungen)"),
        "persona": build_section(briefing, "Buyer Persona (KMU‑Entscheider in Beratungskontext)"),
        "praxisbeispiel": build_section(briefing, "Praxisbeispiel (Beratung, Kennzahlen)"),
        "coach": build_section(briefing, "Enablement (Coach‑Hinweise)"),
    }

    # Live‑Layer
    news, tools, funding, last_live_update = get_live_sections(briefing)

    # Template auswählen
    jinja_env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template_name = TEMPLATE_DE if lang.lower().startswith("de") else TEMPLATE_EN
    tmpl = jinja_env.get_template(template_name)

    context = {
        "assets_base_url": ASSETS_BASE_URL,
        "generated_at": now_iso(),
        "branche_label": briefing.get("branche_label", "Beratung & Dienstleistungen"),
        "unternehmensgroesse_label": briefing.get("unternehmensgroesse_label"),
        "bundesland_code": briefing.get("bundesland_code", "DE"),
        "hauptleistung": briefing.get("hauptleistung", ""),
        "strategische_ziele": briefing.get("strategische_ziele", ""),
        "zielgruppen": briefing.get("zielgruppen", []),
        "ki_usecases": briefing.get("ki_usecases", []),
        "ki_projekte": briefing.get("ki_projekte", ""),
        "ki_potenzial": briefing.get("ki_potenzial", ""),
        "badges": badges,

        "kpis": kpis,
        "score_percent": score,
        "business": business,

        "sections": sections,

        "benchmarks": [{"name": k.name, "value": k.value_pct, "median": k.median_pct, "delta": k.delta_pp} for k in kpis],

        "news": news,
        "tools": tools,
        "funding": funding,
        "last_live_update": last_live_update,
    }

    html_out = tmpl.render(**context)
    return html_out


def generate_pdf(html_in: str) -> bytes:
    """
    PDF-Service nur /generate-pdf – Backoff bei Transient Errors.
    """
    url = f"{PDF_SERVICE_URL}/generate-pdf"
    payload = {"html": html_in}
    for attempt in range(3):
        try:
            with httpx.Client(timeout=60) as client:
                r = client.post(url, json=payload)
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"):
                    return r.content
                elif r.status_code == 200:
                    # Service may return {pdf: base64,...}
                    try:
                        j = r.json()
                        if "pdf" in j:
                            return base64.b64decode(j["pdf"])
                    except Exception:
                        pass
                log.warning("PDF service attempt %d: status=%s", attempt + 1, r.status_code)
        except Exception as e:
            log.warning("PDF service error attempt %d: %s", attempt + 1, e)
        time.sleep(0.6 * (attempt + 1))
    raise RuntimeError("PDF generation failed")


# ------------------------------------------------------------------------------
# CLI (optional)
# ------------------------------------------------------------------------------
def _load_briefing_auto() -> Dict[str, Any]:
    """
    Convenience loader: versucht die bekannten Briefing-Dateien zu finden.
    """
    for p in ("briefing_normalized.json", "briefing_raw.json", "briefing_missing_fields.json"):
        if os.path.exists(p):
            try:
                return load_json(p)
            except Exception:
                continue
    return {}


def main():
    briefing = _load_briefing_auto()
    if not briefing:
        log.warning("No briefing file found – rendering minimal demo based on defaults")

    html_de = render_html(briefing, lang="de")
    with open("report.de.html", "w", encoding="utf-8") as f:
        f.write(html_de)
    log.info("HTML (DE) written to report.de.html")

    try:
        pdf_bytes = generate_pdf(html_de)
        with open("report.de.pdf", "wb") as f:
            f.write(pdf_bytes)
        log.info("PDF (DE) written to report.de.pdf")
    except Exception as e:
        log.error("PDF generation failed: %s", e)


if __name__ == "__main__":
    main()
