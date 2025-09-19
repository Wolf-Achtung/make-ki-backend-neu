# gpt_analyze.py — Gold-Standard (2025-09-19)
# -------------------------------------------------
# This module generates the narrative KI-Status report (DE/EN),
# renders it via Jinja2, and returns a single HTML string to the caller.
#
# Key fixes in this version:
# 1) Always provides a `meta` dict to the template (prevents "meta is undefined").
# 2) Reintroduces `_strip_lists_and_numbers` used by various fallbacks.
# 3) Tightens HTML sanitization (no code fences, lists or numbers if not wanted).
# 4) Keeps the one-module import surface (avoid duplicate/backup modules).
# 5) Robust prompt/template/data discovery, but *no* legacy folders that can shadow newer prompts.
#
# Drop this file in your app root as /app/gpt_analyze.py (or project root)
# and ensure the templates live in ./templates next to this file.
#
# Compatible with your current main.py which calls: analyze_briefing(body, lang).

from __future__ import annotations

import os
import re
import csv
import json
import base64
import zipfile
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI

# ----------------------------------------------------------------------------
# Constants & Paths
# ----------------------------------------------------------------------------

BASE_DIR: Path = Path(__file__).resolve().parent
TEMPLATES_DIR: Path = BASE_DIR / "templates"

# Single OpenAI client reused across calls
client = OpenAI()

VERSION_MARKER = "v-gold-2025-09-19"


# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").strip().lower()
    return "de" if l.startswith("de") else "en"


def _as_int(x) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None


def fix_encoding(text: str) -> str:
    if not text:
        return ""
    return (text
            .replace("�", "-")
            .replace("–", "-")
            .replace("“", '"')
            .replace("”", '"')
            .replace("’", "'"))


def strip_code_fences(text: str) -> str:
    """Remove triple-backtick fenced blocks and stray backticks."""
    if not text:
        return ""
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")


def ensure_html(text: str, lang: str = "de") -> str:
    """If not obvious HTML, turn simple lines into <p> paragraphs and lists into <ul>."""
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t
    lines = [ln.rstrip() for ln in t.splitlines() if ln.strip()]
    html = []
    in_ul = False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append("<li>" + re.sub(r"^[-•*]\s+", "", ln).strip() + "</li>")
            continue
        if re.match(r"^#{1,3}\s+", ln):
            level = min(3, max(1, len(ln) - len(ln.lstrip("#"))))
            txt = ln[level:].strip()
            html.append(f"<h{level}>{txt}</h{level}>")
            continue
        if in_ul:
            html.append("</ul>")
            in_ul = False
        html.append("<p>" + ln + "</p>")
    if in_ul:
        html.append("</ul>")
    return "\n".join(html)


def _strip_lists_and_numbers(html_or_text: str) -> str:
    """
    Remove list constructs and (most) numeric expressions to keep narrative style.
    This is intentionally conservative: it avoids breaking words while
    removing obvious list markers, ordinals and percentages.
    """
    if not html_or_text:
        return ""
    t = str(html_or_text)
    # remove list tags, make <li> sentence-ish
    t = re.sub(r"</?(ul|ol)>", "", t, flags=re.I)
    t = re.sub(r"<li[^>]*>\s*", " ", t, flags=re.I)
    t = re.sub(r"</li>", ".", t, flags=re.I)
    # remove line-leading bullets or enumerations like "1) ", "(2) ", "3. "
    t = re.sub(r"(?m)^\s*(?:[\-–•*]\s+|\(?\d+\)?[.)]\s+)", "", t)
    # remove bare numbers & percentages
    t = re.sub(r"\b\d+[.,]?\d*\s*%?", "", t)
    # collapse whitespace and duplicated sentence dots
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\.\s*\.", ".", t)
    return t.strip()


def _sanitize_text(value: str) -> str:
    """Remove zero-width & problematic characters + neutralize vendor/model names."""
    if not value:
        return ""
    bad = ["\uFFFE", "\uFEFF", "\u200B", "\u00AD"]
    text = str(value)
    for ch in bad:
        text = text.replace(ch, "")
    replacements = {
        "GPT-3": "LLM-gestützte Auswertung",
        "GPT‑3": "LLM-gestützte Auswertung",
        "GPT-Analyse": "LLM-gestützte Analyse",
        "GPT‑Analyse": "LLM-gestützte Analyse",
        "GPT-Technologie": "LLM-gestützte Technologie",
        "GPT‑Technologie": "LLM-gestützte Technologie",
        "GPT basierte": "LLM-gestützte",
        "GPT‑basierte": "LLM-gestützte",
        "GPT-ausgewerteten": "LLM-gestützten",
        "GPT‑ausgewerteten": "LLM-gestützten",
        "GPT-ausgewertete": "LLM-gestützte",
        "GPT‑ausgewertete": "LLM-gestützte",
        "GPT-gestützt": "LLM-gestützte",
        "GPT‑gestützt": "LLM-gestützte",
        "GPT-gestützte": "LLM-gestützte",
        "GPT‑gestützte": "LLM-gestützte",
        "GPT-Portal": "KI-Portal",
        "GPT‑Portal": "KI-Portal",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _read_md_table(path: str) -> List[dict]:
    """Parse a simple Markdown table and return rows as dicts."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return []
    if len(lines) < 2 or "|" not in lines[0] or "|" not in lines[1]:
        return []
    headers = [h.strip().strip("|").strip() for h in lines[0].split("|") if h.strip()]
    rows: List[dict] = []
    for ln in lines[2:]:
        if "|" not in ln:
            continue
        cells = [c.strip().strip("|").strip() for c in ln.split("|")]
        if not any(cells):
            continue
        row = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------
# Data discovery helpers
# ----------------------------------------------------------------------------

def ensure_unzipped(zip_name: str, dest_dir: str) -> None:
    try:
        if os.path.exists(zip_name) and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            with zipfile.ZipFile(zip_name, "r") as zf:
                zf.extractall(dest_dir)
    except Exception:
        pass


# Unpack known archives if present
ensure_unzipped("prompts.zip", "prompts_unzip")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")
ensure_unzipped("aus-Data.zip", "data")


def _load_csv_candidates(names: List[str]) -> str:
    # Prefer ./data/name, fallback to ./name, then nested dev path
    for n in names:
        p = os.path.join("data", n)
        if os.path.exists(p):
            return p
    for n in names:
        if os.path.exists(n):
            return n
    nested = os.path.join("ki_backend", "make-ki-backend-neu-main", "data")
    for n in names:
        p = os.path.join(nested, n)
        if os.path.exists(p):
            return p
    return ""


def _read_rows(path: str) -> List[Dict[str, str]]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in rd]
    except Exception:
        return []


# ----------------------------------------------------------------------------
# Domain logic (branche, size etc.)
# ----------------------------------------------------------------------------

def _extract_branche(d: Dict[str, Any]) -> str:
    raw = (str(d.get("branche") or d.get("industry") or d.get("sector") or "")).strip().lower()
    m = {
        "beratung": "beratung", "consulting": "beratung", "dienstleistung": "beratung", "services": "beratung",
        "it": "it", "software": "it", "information technology": "it", "saas": "it", "kollaboration": "it",
        "marketing": "marketing", "werbung": "marketing", "advertising": "marketing",
        "bau": "bau", "construction": "bau", "architecture": "bau",
        "industrie": "industrie", "produktion": "industrie", "manufacturing": "industrie",
        "handel": "handel", "retail": "handel", "e-commerce": "handel", "ecommerce": "handel",
        "finanzen": "finanzen", "finance": "finanzen", "insurance": "finanzen",
        "gesundheit": "gesundheit", "health": "gesundheit", "healthcare": "gesundheit",
        "medien": "medien", "media": "medien", "kreativwirtschaft": "medien",
        "logistik": "logistik", "logistics": "logistik", "transport": "logistik",
        "verwaltung": "verwaltung", "public administration": "verwaltung",
        "bildung": "bildung", "education": "bildung"
    }
    if raw in m:
        return m[raw]
    for k, v in m.items():
        if k in raw:
            return v
    return "default"


def is_self_employed(data: dict) -> bool:
    keys_text = ["beschaeftigungsform", "beschäftigungsform", "arbeitsform", "rolle", "role",
                 "occupation", "unternehmensform", "company_type"]
    txt = " ".join(str(data.get(k, "") or "") for k in keys_text).lower()
    if any(s in txt for s in ["selbst", "freelanc", "solo", "self-employ"]):
        return True
    for k in ["mitarbeiter", "mitarbeiterzahl", "anzahl_mitarbeiter", "employees", "employee_count", "team_size"]:
        n = _as_int(data.get(k))
        if n is not None and n <= 1:
            return True
    return False


def load_yaml(path: str):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_context(data: dict, branche: str, lang: str = "de") -> dict:
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path) if os.path.exists(context_path) else {}

    context.update(data or {})
    context["lang"] = lang

    # company size category & label
    def _get_employee_count(d: dict) -> Optional[int]:
        for key in ["mitarbeiter", "mitarbeiterzahl", "anzahl_mitarbeiter", "employees", "employee_count", "team_size"]:
            v = d.get(key)
            n = _as_int(v)
            if n is not None:
                return n
        sz = (d.get("unternehmensgroesse") or d.get("company_size") or "").strip().lower()
        if sz:
            if any(s in sz for s in ["solo", "einzel", "self"]):
                return 1
            m = re.match(r"(\d+)", sz)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    pass
        return None

    emp_count = _get_employee_count(context)
    self_emp = is_self_employed(context)
    if self_emp:
        category = "solo"
    else:
        if emp_count is None:
            category = "team"
        elif emp_count <= 1:
            category = "solo"
        elif emp_count <= 10:
            category = "team"
        else:
            category = "kmu"

    if lang == "de":
        label = {"solo": "Solo-Unternehmer:in", "team": "Team (2–10 Mitarbeitende)", "kmu": "KMU (11+ Mitarbeitende)"}[category]
    else:
        label = {"solo": "Solo entrepreneur", "team": "Small team (2–10 people)", "kmu": "SME (11+ people)"}[category]

    context["company_size_category"] = category
    context["company_size_label"] = label
    context["unternehmensgroesse"] = label
    context["self_employed"] = "Yes" if self_emp else "No"
    context["selbststaendig"] = "Ja" if self_emp and lang == "de" else ("Nein" if lang == "de" else context["self_employed"])
    context["company_form"] = context.get("rechtsform") or context.get("company_form") or context.get("legal_form") or ""
    if lang != "de":
        _branch_translations = {
            "beratung": "consulting",
            "bau": "construction",
            "bildung": "education",
            "finanzen": "finance",
            "gesundheit": "healthcare",
            "handel": "trade",
            "industrie": "industry",
            "it": "IT",
            "logistik": "logistics",
            "marketing": "marketing",
            "medien": "media",
            "verwaltung": "public administration",
            "default": "industry"
        }
        context["branche"] = _branch_translations.get(branche.lower(), branche)
    else:
        context["branche"] = branche

    context.setdefault("copyright_year", datetime.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")
    context.setdefault("company_size", _as_int(data.get("mitarbeiterzahl") or data.get("employees") or 1) or 1)
    context["is_self_employed"] = is_self_employed(data)
    context["hauptleistung"] = context.get("hauptleistung") or context.get("main_service") or context.get("hauptprodukt") or ""
    context["projektziel"] = context.get("projektziel") or context.get("ziel") or ""

    return context


# ----------------------------------------------------------------------------
# Live search helpers (Tavily/SerpAPI) — optional enhancements
# ----------------------------------------------------------------------------

def _tavily_search(query: str, max_results: int = 5, days: Optional[int] = None) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    payload = {"api_key": key, "query": query, "max_results": max_results, "include_answer": False,
               "search_depth": os.getenv("SEARCH_DEPTH", "basic")}
    if days:
        payload["days"] = days
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
            res = []
            for item in data.get("results", [])[:max_results]:
                res.append({
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "published_date": item.get("published_date"),
                    "score": item.get("score"),
                })
            return res
    except Exception:
        return []


def _serpapi_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        return []
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.get("https://serpapi.com/search.json", params={"q": query, "num": max_results, "api_key": key})
            r.raise_for_status()
            data = r.json()
            res = []
            for item in data.get("organic_results", [])[:max_results]:
                res.append({"title": item.get("title"), "url": item.get("link"), "content": item.get("snippet")})
            return res
    except Exception:
        return []


def build_live_updates_html(data: Dict[str, Any], lang: str = "de", max_results: int = 5) -> Tuple[str, str]:
    branche = _extract_branche(data)
    size = str(data.get("unternehmensgroesse") or data.get("company_size") or "").strip().lower()
    region = str(data.get("bundesland") or data.get("state") or data.get("ort") or data.get("city") or "").strip()
    product = str(data.get("hauptleistung") or data.get("hauptprodukt") or data.get("main_product") or "").strip()
    topic = str(data.get("search_topic") or "").strip()
    days = int(os.getenv("SEARCH_DAYS", "30"))

    if lang.startswith("de"):
        queries = [q for q in [f"Förderprogramm KI {region} {branche} {size}".strip(),
                               f"KI Tool {branche} {product} DSGVO".strip(), topic] if q]
        title = f"Neu seit {datetime.now().strftime('%B %Y')}"
    else:
        queries = [q for q in [f"AI funding {region} {branche} {size}".strip(),
                               f"GDPR-friendly AI tool {branche} {product}".strip(), topic] if q]
        title = f"New since {datetime.now().strftime('%B %Y')}"

    seen = set()
    items = []
    for q in queries:
        res = _tavily_search(q, max_results=max_results, days=days) or _serpapi_search(q, max_results=max_results)
        for r in res:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            date = r.get("published_date") or ""
            li = f'<li><a href="{url}">{(r.get("title") or url)[:120]}</a>'
            if date:
                li += f' <span style="color:#5B6B7C">({date})</span>'
            snippet = (r.get("content") or "")[:240].replace("<", "&lt;").replace(">", "&gt;")
            if snippet:
                li += f"<br><span style='color:#5B6B7C;font-size:12px'>{snippet}</span>"
            li += "</li>"
            items.append(li)
    html = "<ul>" + "".join(items[:max_results]) + "</ul>" if items else ""
    return title, html


# ----------------------------------------------------------------------------
# Funding & Tools (tables + narratives)
# ----------------------------------------------------------------------------

def build_funding_details_struct(data: Dict[str, Any], lang: str = "de", max_items: int = 8):
    path = _load_csv_candidates(["foerdermittel.csv", "foerderprogramme.csv"])
    rows = _read_rows(path) if path else []
    out = []
    size_raw = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()

    def _norm_size(x: str) -> str:
        x = (x or "").lower()
        if x in {"solo", "einzel", "einzelunternehmer", "freelancer", "soloselbstständig", "soloselbststaendig"}: return "solo"
        if x in {"team", "small"}: return "team"
        if x in {"kmu", "sme", "mittelstand"}: return "kmu"
        return ""

    size = _norm_size(size_raw)
    region = (str(data.get("bundesland") or data.get("state") or "")).lower()
    if region in {"be"}:
        region = "berlin"

    for r in rows:
        name = r.get("name") or r.get("programm") or r.get("Program") or r.get("Name") or ""
        if not name:
            continue
        target = (r.get("zielgruppe") or r.get("target") or r.get("Zielgruppe") or "").lower()
        reg = (r.get("region") or r.get("bundesland") or r.get("land") or r.get("Region") or "").lower()
        grant = r.get("foerderart") or r.get("grant") or r.get("quote") or r.get("kosten") or r.get("Fördersumme (€)") or ""
        use_case = r.get("einsatz") or r.get("zweck") or r.get("beschreibung") or r.get("use_case") or r.get("Beschreibung") or ""
        link = r.get("link") or r.get("url") or r.get("Link") or ""
        # size filter
        if size and target:
            if size not in target and not (target == "kmu" and size in {"team", "kmu"}):
                continue
        # region bias
        score = 0
        if region and reg == region:
            score -= 5
        if reg in {"bund", "deutschland", "de"}:
            score -= 1
        out.append({
            "name": name, "target": r.get("zielgruppe") or r.get("target") or r.get("Zielgruppe") or "",
            "region": r.get("region") or r.get("bundesland") or r.get("land") or r.get("Region") or "",
            "grant": grant, "use_case": use_case, "link": link, "_score": score
        })
    out = sorted(out, key=lambda x: x.get("_score", 0))[:max_items]
    for o in out:
        o.pop("_score", None)

    stand = ""
    try:
        ts = os.path.getmtime(path)
        stand = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        pass
    return out, stand


def build_funding_narrative(data: Dict[str, Any], lang: str = "de", max_items: int = 5) -> str:
    rows, _ = build_funding_details_struct(data, lang, max_items)
    if not rows:
        return ""
    ps = []
    if lang.startswith("de"):
        for r in rows:
            p = (f"<p><b>{r['name']}</b> – geeignet für {r.get('target','KMU')}, Region: {r.get('region','DE')}. "
                 f"{r.get('use_case','')} "
                 f"{('<i>Förderart/Kosten: ' + r['grant'] + '</i> ') if r.get('grant') else ''}"
                 f"{(f'<a href=\"{r['link']}\">Zum Programm</a>') if r.get('link') else ''}"
                 f"</p>")
            ps.append(p)
    else:
        for r in rows:
            p = (f"<p><b>{r['name']}</b> – suitable for {r.get('target','SMEs')}, region: {r.get('region','DE')}. "
                 f"{r.get('use_case','')} "
                 f"{('<i>Grant/Costs: ' + r['grant'] + '</i> ') if r.get('grant') else ''}"
                 f"{(f'<a href=\"{r['link']}\">Open</a>') if r.get('link') else ''}"
                 f"</p>")
            ps.append(p)
    return "\n".join(ps)


def build_tools_details_struct(data: Dict[str, Any], branche: str, lang: str = "de", max_items: int = 12):
    path = _load_csv_candidates(["tools.csv", "ki_tools.csv"])
    rows = _read_rows(path) if path else []
    out = []

    size = (str(data.get("unternehmensgroesse") or data.get("company_size") or "").lower())
    if "solo" in size:
        user_size = "solo"
    elif "team" in size or "2" in size or "10" in size:
        user_size = "team"
    elif "kmu" in size or "11" in size:
        user_size = "kmu"
    else:
        user_size = ""

    for r in rows:
        name = r.get("name") or r.get("Tool") or r.get("Tool-Name") or r.get("Name")
        if not name:
            continue
        tags = (r.get("Branche-Slugs") or r.get("Tags") or r.get("Branche") or "").lower()
        row_size = (r.get("Unternehmensgröße") or r.get("Unternehmensgroesse") or r.get("company_size") or "").lower()
        if branche and tags and branche not in tags:
            continue
        if user_size:
            if row_size and row_size not in {"alle", user_size}:
                if not ((row_size == "kmu" and user_size in {"team", "kmu"}) or (row_size == "team" and user_size == "solo")):
                    continue
        out.append({
            "name": name,
            "category": r.get("kategorie") or r.get("category") or "",
            "suitable_for": r.get("eignung") or r.get("use_case") or r.get("einsatz") or "",
            "hosting": r.get("hosting") or r.get("datenschutz") or r.get("data") or "",
            "price": r.get("preis") or r.get("price") or r.get("kosten") or "",
            "link": r.get("link") or r.get("url") or "",
        })
    return out[:max_items], ""


def build_tools_narrative(data: Dict[str, Any], branche: str, lang: str = "de", max_items: int = 6) -> str:
    rows, _ = build_tools_details_struct(data, branche, lang, max_items)
    if not rows:
        return ""
    ps = []
    if lang.startswith("de"):
        for r in rows:
            p = (f"<p><b>{r['name']}</b> ({r.get('category','')}) – geeignet für {r.get('suitable_for','Alltag')}. "
                 f"Hosting/Datenschutz: {r.get('hosting','n/a')}; Preis: {r.get('price','n/a')}. "
                 f"{(f'<a href=\"{r['link']}\">Zur Website</a>') if r.get('link') else ''}"
                 f"</p>")
            ps.append(p)
    else:
        for r in rows:
            p = (f"<p><b>{r['name']}</b> ({r.get('category','')}) – suitable for {r.get('suitable_for','daily work')}. "
                 f"Hosting/data: {r.get('hosting','n/a')}; price: {r.get('price','n/a')}. "
                 f"{(f'<a href=\"{r['link']}\">Website</a>') if r.get('link') else ''}"
                 f"</p>")
            ps.append(p)
    return "\n".join(ps)


# ----------------------------------------------------------------------------
# Prompting
# ----------------------------------------------------------------------------

def render_prompt(template_text: str, context: dict) -> str:
    def replace_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template_text)

    def replace_simple(m):
        key = m.group(1); val = context.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, rendered)


def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
    primary_path = f"prompts/{lang}/{chapter}.md"
    if os.path.exists(primary_path):
        try:
            prompt_text = load_text(primary_path)
        except Exception:
            prompt_text = None
    else:
        prompt_text = None
    if not prompt_text:
        prompt_text = f"[NO PROMPT FOUND for {chapter}/{lang}]"

    prompt = render_prompt(prompt_text, context)
    is_de = (lang == "de")
    base_rules = (
        "Gib die Antwort ausschließlich als gültiges HTML ohne <html>-Wrapper zurück. "
        "Verwende nur <h3> und <p>. Keine Listen, keine Tabellen, keine Aufzählungen. "
        "Formuliere 2–3 zusammenhängende Absätze in freundlicher, motivierender Sprache. "
        "Integriere Best‑Practice‑Geschichten. Keine Zahlen oder Prozentwerte."
        if is_de else
        "Return VALID HTML only (no <html> wrapper). Use only <h3> and <p>. "
        "Avoid lists and tables. Write 2–3 connected paragraphs in a warm, motivating tone. "
        "Integrate short best‑practice stories. Do not include numbers or percentages."
    )
    style = "\n\n---\n" + base_rules
    return prompt + style


def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float] = None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()


def gpt_generate_section(data, branche, chapter, lang="de"):
    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    context = build_context(data, branche, lang)
    # optional: live links, gamechanger blocks can be injected here later
    prompt = build_masterprompt(chapter, context, lang)
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model
    section_text = _chat_complete(
        messages=[
            {"role": "system",
             "content": ("Sie sind TÜV-zertifizierte:r KI-Manager:in, KI-Strategieberater:in sowie Datenschutz- und Fördermittel-Expert:in. "
                         "Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML.")
             if lang == "de" else
                        ("You are a TÜV-certified AI manager and strategy consultant. "
                         "Deliver precise, actionable, up-to-date, sector-relevant content as HTML.")},
            {"role": "user", "content": prompt},
        ],
        model_name=model_name,
        temperature=None,
    )
    return section_text


def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(strip_code_fences(fix_encoding(html)), lang)


# ----------------------------------------------------------------------------
# Minimal chart payload & (deprecated) score
# ----------------------------------------------------------------------------

def calc_score_percent(data: dict) -> int:
    # Deprecated aggregate score; keep for backward compatibility
    return 0


# ----------------------------------------------------------------------------
# Report assembly
# ----------------------------------------------------------------------------

def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "htm"]),
        enable_async=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _pick_template(lang: str) -> Optional[str]:
    if lang == "de" and (TEMPLATES_DIR / "pdf_template.html").exists():
        return "pdf_template.html"
    if (TEMPLATES_DIR / "pdf_template_en.html").exists():
        return "pdf_template_en.html"
    return None


def _data_uri_for(path: str) -> Optional[str]:
    if not path or path.startswith(("http://", "https://", "data:")):
        return path
    candidate_files = [Path(path), TEMPLATES_DIR / path]
    for cand in candidate_files:
        if cand.exists():
            mime = mimetypes.guess_type(str(cand))[0] or "application/octet-stream"
            b64 = base64.b64encode(cand.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{b64}"
    return None


def _inline_local_images(html: str) -> str:
    def repl(m):
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        data = _data_uri_for(src)
        return m.group(0).replace(src, data) if data else m.group(0)
    return re.sub(r'src="([^"]+)"', repl, html)


def _toc_from_report(report: Dict[str, Any], lang: str) -> str:
    toc_items: List[str] = []

    def add(key: str, label: str) -> None:
        if report.get(key):
            toc_items.append(f"<li>{label}</li>")

    if lang == "de":
        add("exec_summary_html", "Executive Summary")
        if report.get("quick_wins_html") or report.get("risks_html"):
            toc_items.append("<li>Quick Wins & Risiken</li>")
        add("recommendations_html", "Empfehlungen")
        add("roadmap_html", "Roadmap")
        if report.get("foerderprogramme_html") or report.get("foerderprogramme_table"):
            toc_items.append("<li>Förderprogramme</li>")
        if report.get("tools_html") or report.get("tools_table"):
            toc_items.append("<li>KI-Tools & Software</li>")
        add("sections_html", "Weitere Kapitel")
    else:
        add("exec_summary_html", "Executive summary")
        if report.get("quick_wins_html") or report.get("risks_html"):
            toc_items.append("<li>Quick wins & key risks</li>")
        add("recommendations_html", "Recommendations")
        add("roadmap_html", "Roadmap")
        if report.get("foerderprogramme_html") or report.get("foerderprogramme_table"):
            toc_items.append("<li>Funding programmes</li>")
        if report.get("tools_html") or report.get("tools_table"):
            toc_items.append("<li>AI tools</li>")
        add("sections_html", "Additional sections")

    return f"<ul>{''.join(toc_items)}</ul>" if toc_items else ""


def generate_preface(lang: str = "de", score_percent: Optional[int] = None) -> str:
    if lang == "de":
        return (
            "<p>Dieser Report setzt auf warmes, narratives Storytelling statt nackter KPIs. "
            "Er ist praxisnah und sowohl DSGVO‑ als auch EU‑AI‑Act‑ready. "
            "Die Empfehlungen sind qualitativ formuliert; Zahlen und Prozentwerte werden bewusst vermieden.</p>"
        )
    else:
        return (
            "<p>This report uses warm, narrative storytelling instead of bare KPIs. "
            "It is practical and compliant with GDPR and the EU AI Act. "
            "Recommendations are expressed qualitatively; numbers and percentages are intentionally avoided.</p>"
        )


def generate_full_report(data: dict, lang: str = "de") -> dict:
    branche = _extract_branche(data)
    lang = _norm_lang(lang)
    data["score_percent"] = None
    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar", "yes", "unsure"}

    chapters = [
        "executive_summary",
        "vision",
        "gamechanger",
        "quick_wins",
        "risks",
        "tools",
    ] + (["foerderprogramme"] if wants_funding else []) + [
        "roadmap",
        "compliance",
        "praxisbeispiel",
        "recommendations",
    ]
    out: Dict[str, Any] = {}
    for chap in chapters:
        try:
            sect_html = gpt_generate_section_html(data, branche, chap, lang=lang)
            out[chap] = ensure_html(strip_code_fences(fix_encoding(sect_html)), lang)
        except Exception as e:
            out[chap] = f"<p>[Fehler in Kapitel {chap}: {e}]</p>"

    # Preface
    out["preface"] = generate_preface(lang=lang, score_percent=data.get("score_percent"))

    # Quick wins / risks / recs
    qw_html = ensure_html(strip_code_fences(fix_encoding(out.get("quick_wins") or "")), lang)
    rk_html = ensure_html(strip_code_fences(fix_encoding(out.get("risks") or "")), lang)
    rec_html = ensure_html(strip_code_fences(fix_encoding(out.get("recommendations") or "")), lang)

    if not qw_html:
        if lang == "de":
            qw_html = (
                "<h3>Quick&nbsp;Wins</h3>"
                "<ul>"
                "<li><b>Dateninventur</b>: Relevante Kunden‑, Projekt‑ und Marketingdaten bündeln und bereinigen.</li>"
                "<li><b>Mini‑Automatisierung</b>: Wiederkehrende Aufgaben mit einem No‑Code‑Workflow automatisieren.</li>"
                "<li><b>KI‑Policy Light</b>: Einseitige Richtlinie für verantwortungsvolle KI‑Nutzung formulieren.</li>"
                "</ul>"
            )
        else:
            qw_html = (
                "<h3>Quick&nbsp;wins</h3>"
                "<ul>"
                "<li><b>Data inventory</b>: Consolidate and clean relevant customer, project and marketing data.</li>"
                "<li><b>Mini automation</b>: Automate repetitive tasks with a simple no‑code workflow.</li>"
                "<li><b>Lightweight AI policy</b>: Draft a one‑page guideline for responsible AI use.</li>"
                "</ul>"
            )
    out["quick_wins_html"] = qw_html
    out["risks_html"] = rk_html
    out["recommendations_html"] = rec_html

    # Tools & funding (narrative fallbacks)
    if not out.get("tools"):
        out["tools_html"] = build_tools_narrative(data, branche, lang=lang, max_items=6)
    else:
        out["tools_html"] = out["tools"]

    if not out.get("foerderprogramme"):
        out["foerderprogramme_html"] = build_funding_narrative(data, lang=lang, max_items=6)
    else:
        out["foerderprogramme_html"] = out["foerderprogramme"]

    # Tables if template wants them
    out["foerderprogramme_table"] = build_funding_details_struct(data, lang=lang, max_items=8)[0]
    out["tools_table"] = build_tools_details_struct(data, branche, lang=lang, max_items=8)[0]

    return out


# ----------------------------------------------------------------------------
# Public entry point used by main.py
# ----------------------------------------------------------------------------

def analyze_briefing(body: dict, lang: str = "de") -> str:
    """
    Main entry point.  Returns a single HTML string ready to be sent to the PDF service.
    We construct a minimal-but-complete context for the Jinja template including `meta`.
    """
    # Extract payload: accept various keys or treat body as the payload
    payload = {}
    if isinstance(body, dict):
        for k in ["payload", "data", "report_payload", "questionnaire", "form", "input"]:
            v = body.get(k)
            if isinstance(v, dict):
                payload = v
                break
        if not payload:
            payload = body
    lang = _norm_lang(body.get("lang") or body.get("language") or body.get("sprache") or lang)
    branche = _extract_branche(payload)

    # Build full report dict with HTML fragments
    report = generate_full_report(payload, lang=lang)

    # --- META (prevents 'meta is undefined') ---
    company = (payload.get("unternehmen") or payload.get("company") or payload.get("firma") or "").strip() or "—"
    person = (payload.get("name") or payload.get("kontakt") or payload.get("ansprechpartner") or "").strip()
    branche_label = payload.get("branche") or branche or "—"
    size_label = payload.get("company_size_label") or payload.get("unternehmensgroesse") or "—"
    location = (payload.get("ort") or payload.get("city") or payload.get("bundesland") or payload.get("state") or "").strip() or "—"

    title = "KI-Statusbericht" if lang == "de" else "AI Status Report"
    subtitle = "Narrativer KI‑Report – DSGVO & EU‑AI‑Act‑ready" if lang == "de" else "Narrative AI report – GDPR & EU AI Act ready"
    today = datetime.now().strftime("%d.%m.%Y") if lang == "de" else datetime.now().strftime("%Y-%m-%d")

    meta = {
        "title": title,
        "subtitle": subtitle,
        "date": today,
        "company": company,
        "contact": person or "—",
        "branche": branche_label or "—",
        "groesse": size_label or "—",
        "location": location or "—",
        "version": VERSION_MARKER,
    }

    # Table of contents derived from available sections
    report["toc_html"] = _toc_from_report({
        "exec_summary_html": report.get("executive_summary"),
        "quick_wins_html": report.get("quick_wins_html"),
        "risks_html": report.get("risks_html"),
        "recommendations_html": report.get("recommendations_html"),
        "roadmap_html": report.get("roadmap"),
        "foerderprogramme_html": report.get("foerderprogramme_html"),
        "foerderprogramme_table": report.get("foerderprogramme_table"),
        "tools_html": report.get("tools_html"),
        "tools_table": report.get("tools_table"),
        "sections_html": "\n".join([
            report.get("vision", ""),
            report.get("gamechanger", ""),
            report.get("praxisbeispiel", ""),
            report.get("compliance", ""),
        ])
    }, lang=lang)

    # Render template
    env = _jinja_env()
    tpl_name = _pick_template(lang) or "pdf_template.html"
    tmpl = env.get_template(tpl_name)

    # Build Jinja context
    ctx: Dict[str, Any] = {
        "lang": lang,
        "meta": meta,
        "now": datetime.now,
        # top matter
        "preface_html": report.get("preface") or "",
        "toc_html": report.get("toc_html") or "",
        # core sections
        "exec_summary_html": report.get("executive_summary") or "",
        "quick_wins_html": report.get("quick_wins_html") or "",
        "risks_html": report.get("risks_html") or "",
        "recommendations_html": report.get("recommendations_html") or "",
        "roadmap_html": report.get("roadmap") or "",
        "vision_html": report.get("vision") or "",
        "gamechanger_html": report.get("gamechanger") or "",
        "compliance_html": report.get("compliance") or "",
        "praxisbeispiel_html": report.get("praxisbeispiel") or "",
        # funding/tools (narrative + tables)
        "foerderprogramme_html": report.get("foerderprogramme_html") or "",
        "foerderprogramme_table": report.get("foerderprogramme_table") or [],
        "tools_html": report.get("tools_html") or "",
        "tools_table": report.get("tools_table") or [],
        # footer
        "version_marker": VERSION_MARKER,
    }

    html = tmpl.render(**ctx)
    html = _inline_local_images(html)
    return html
