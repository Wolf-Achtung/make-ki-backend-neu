# gpt_analyze.py — Gold-Standard (Teil 1/4)
import os
import re
import json
import base64
import zipfile
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional, List
# Optional post-processing: clamp lists, add missing fields (quick wins, roadmap, trade-offs).
# Attempt to import the helper.  If unavailable, default to None so that
# report generation still works without post-processing.
try:
    from postprocess_report import postprocess_report_dict  # type: ignore[attr-defined]
except Exception:
    postprocess_report_dict = None


# --- Injected Best-of-both helpers (Model resolver / Branche / Live / Details) ---
from typing import Optional, List, Dict, Any
import datetime as _dt

# Patch A: robust model resolver to avoid OpenAI 400s when invalid model is configured
def _resolve_model(wanted: Optional[str]) -> str:
    fallbacks = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    w = (wanted or "").strip().lower()
    if not w or w.startswith("gpt-5"):
        return fallbacks[0]
    # known-good set
    known = set(fallbacks) | {"gpt-4o-audio-preview", "gpt-4.1", "gpt-4.1-mini"}
    return w if w in known else fallbacks[0]

# Patch B: Branche extractor from questionnaire with robust synonyms
def _extract_branche(d: Dict[str, Any]) -> str:
    raw = (str(d.get("branche") or d.get("industry") or d.get("sector") or "")).strip().lower()
    m = {
        "beratung":"beratung","consulting":"beratung","dienstleistung":"beratung","services":"beratung",
        "it":"it","software":"it","information technology":"it","saas":"it","kollaboration":"it",
        "marketing":"marketing","werbung":"marketing","advertising":"marketing",
        "bau":"bau","construction":"bau","architecture":"bau",
        "industrie":"industrie","produktion":"industrie","manufacturing":"industrie",
        "handel":"handel","retail":"handel","e-commerce":"handel","ecommerce":"handel",
        "finanzen":"finanzen","finance":"finanzen","insurance":"finanzen",
        "gesundheit":"gesundheit","health":"gesundheit","healthcare":"gesundheit",
        "medien":"medien","media":"medien","kreativwirtschaft":"medien",
        "logistik":"logistik","logistics":"logistik","transport":"logistik",
        "verwaltung":"verwaltung","public administration":"verwaltung",
        "bildung":"bildung","education":"bildung"
    }
    if raw in m: 
        return m[raw]
    for k,v in m.items():
        if k in raw:
            return v
    return "default"

# ---- Live Layer (Tavily -> SerpAPI fallback) ----
import httpx, json

def _tavily_search(query: str, max_results: int = 5, days: int = None) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "search_depth": os.getenv("SEARCH_DEPTH","basic"),
    }
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
            # Use SerpAPI Google search
            r = c.get("https://serpapi.com/search.json", params={"q": query, "num": max_results, "api_key": key})
            r.raise_for_status()
            data = r.json()
            res = []
            for item in data.get("organic_results", [])[:max_results]:
                res.append({"title": item.get("title"), "url": item.get("link"), "content": item.get("snippet")})
            return res
    except Exception:
        return []

def build_live_updates_html(data: Dict[str, Any], lang: str = "de", max_results: int = 5) -> (str, str):
    branche = _extract_branche(data)
    size = str(data.get("unternehmensgroesse") or data.get("company_size") or "").strip().lower()
    region = str(data.get("bundesland") or data.get("state") or data.get("ort") or data.get("city") or "").strip()
    product = str(data.get("hauptleistung") or data.get("hauptprodukt") or data.get("main_product") or "").strip()
    topic = str(data.get("search_topic") or "").strip()
    days = int(os.getenv("SEARCH_DAYS", "30"))
    queries = []
    base_de = f"Förderprogramm KI {region} {branche} {size}".strip()
    base_en = f"AI funding {region} {branche} {size}".strip()
    t_de = f"KI Tool {branche} {product} DSGVO".strip()
    t_en = f"GDPR-friendly AI tool {branche} {product}".strip()
    if lang.startswith("de"):
        queries = [q for q in [base_de, t_de, topic] if q]
        title = f"Neu seit {_dt.datetime.now().strftime('%B %Y')}"
    else:
        queries = [q for q in [base_en, t_en, topic] if q]
        title = f"New since {_dt.datetime.now().strftime('%B %Y')}"
    seen = set(); items = []
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
            snippet = (r.get("content") or "")[:240].replace("<","&lt;").replace(">","&gt;")
            if snippet:
                li += f"<br><span style='color:#5B6B7C;font-size:12px'>{snippet}</span>"
            li += "</li>"
            items.append(li)
    html = "<ul>" + "".join(items[:max_results]) + "</ul>" if items else ""
    return title, html

# ---- Funding/Tools details + narrative (CSV-driven, size/region aware) ----
import csv

def _load_csv_candidates(names: List[str]) -> str:
    # prefer ./data/name, fallback to ./name, then nested ./ki_backend/... paths
    for n in names:
        p = os.path.join("data", n)
        if os.path.exists(p): return p
    for n in names:
        if os.path.exists(n): return n
    nested = os.path.join("ki_backend","make-ki-backend-neu-main","data")
    for n in names:
        p = os.path.join(nested, n)
        if os.path.exists(p): return p
    return ""

def _read_rows(path: str) -> List[Dict[str,str]]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k,v in r.items()} for r in rd]
    except Exception:
        return []

def _norm_size(x: str) -> str:
    x = (x or "").lower()
    if x in {"solo","einzel","einzelunternehmer","freelancer","soloselbstständig","soloselbststaendig"}: return "solo"
    if x in {"team","small"}: return "team"
    if x in {"kmu","sme","mittelstand"}: return "kmu"
    return ""

def build_funding_details_struct(data: Dict[str,Any], lang: str="de", max_items: int=8):
    path = _load_csv_candidates(["foerdermittel.csv","foerderprogramme.csv"])
    rows = _read_rows(path) if path else []
    out = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")
    region = (str(data.get("bundesland") or data.get("state") or "")).lower()
    if region in {"be"}: region = "berlin"
    for r in rows:
        name = r.get("name") or r.get("programm") or r.get("Program") or ""
        if not name: continue
        target = (r.get("zielgruppe") or r.get("target") or "").lower()
        reg = (r.get("region") or r.get("bundesland") or r.get("land") or "").lower()
        grant = r.get("foerderart") or r.get("grant") or r.get("quote") or r.get("kosten") or ""
        use_case = r.get("einsatz") or r.get("zweck") or r.get("beschreibung") or r.get("use_case") or ""
        link = r.get("link") or r.get("url") or ""
        # size filter (permissive)
        if size and target:
            if size not in target and not (target=="kmu" and size in {"team","kmu"}):
                continue
        # region bias: prefer region or "bund"
        score = 0
        if region and reg == region: score -= 5
        if reg in {"bund","deutschland","de"}: score -= 1
        out.append({"name":name, "target":r.get("zielgruppe") or r.get("target") or "",
                    "region":r.get("region") or r.get("bundesland") or r.get("land") or "",
                    "grant":grant, "use_case":use_case, "link":link, "_score": score})
    out = sorted(out, key=lambda x: x.get("_score",0))[:max_items]
    stand = ""
    try:
        ts = os.path.getmtime(path)
        import datetime as _d
        stand = _d.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        pass
    for o in out:
        o.pop("_score", None)
    return out, stand

def build_funding_narrative(data: Dict[str,Any], lang: str="de", max_items: int=5) -> str:
    rows, _ = build_funding_details_struct(data, lang, max_items)
    if not rows: return ""
    ps = []
    if lang.startswith("de"):
        for r in rows:
            p = f"<p><b>{r['name']}</b> – geeignet für {r.get('target','KMU')}, Region: {r.get('region','DE')}. " \
                f"{r.get('use_case','')} <i>{('Förderart/Kosten: ' + r['grant']) if r.get('grant') else ''}</i> "
            if r.get("link"): p += f'<a href="{r["link"]}">Zum Programm</a>'
            p += "</p>"
            ps.append(p)
    else:
        for r in rows:
            p = f"<p><b>{r['name']}</b> – suitable for {r.get('target','SMEs')}, region: {r.get('region','DE')}. " \
                f"{r.get('use_case','')} <i>{('Grant/Costs: ' + r['grant']) if r.get('grant') else ''}</i> "
            if r.get("link"): p += f'<a href="{r["link"]}">Open</a>'
            p += "</p>"
            ps.append(p)
    return "\n".join(ps)

def build_tools_details_struct(data: Dict[str,Any], branche: str, lang: str="de", max_items: int=12):
    path = _load_csv_candidates(["tools.csv","ki_tools.csv"])
    rows = _read_rows(path) if path else []
    out = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")
    for r in rows:
        name = r.get("name") or r.get("Tool") or r.get("Tool-Name")
        if not name: continue
        tags = (r.get("Branche-Slugs") or r.get("Tags") or r.get("Branche") or "").lower()
        row_size = (r.get("Unternehmensgröße") or r.get("Unternehmensgroesse") or r.get("company_size") or "").lower()
        if branche and tags and branche not in tags: 
            continue
        if size and row_size and row_size not in {"alle", size}:
            if not ((row_size=="kmu" and size in {"team","kmu"}) or (row_size=="team" and size=="solo")):
                continue
        out.append({
            "name": name,
            "category": r.get("kategorie") or r.get("category") or "",
            "suitable_for": r.get("eignung") or r.get("use_case") or r.get("einsatz") or "",
            "hosting": r.get("hosting") or r.get("datenschutz") or r.get("data") or "",
            "price": r.get("preis") or r.get("price") or r.get("kosten") or "",
            "link": r.get("link") or r.get("url") or "",
        })
    # keep first N
    return out[:max_items], ""

def build_tools_narrative(data: Dict[str,Any], branche: str, lang: str="de", max_items: int=6) -> str:
    rows, _ = build_tools_details_struct(data, branche, lang, max_items)
    if not rows: return ""
    ps = []
    if lang.startswith("de"):
        for r in rows:
            p = f"<p><b>{r['name']}</b> ({r.get('category','')}) – geeignet für {r.get('suitable_for','Alltag')}. " \
                f"Hosting/Datenschutz: {r.get('hosting','n/a')}; Preis: {r.get('price','n/a')}. "
            if r.get("link"): p += f'<a href="{r["link"]}">Zur Website</a>'
            p += "</p>"
            ps.append(p)
    else:
        for r in rows:
            p = f"<p><b>{r['name']}</b> ({r.get('category','')}) – suitable for {r.get('suitable_for','daily work')}. " \
                f"Hosting/data: {r.get('hosting','n/a')}; price: {r.get('price','n/a')}. "
            if r.get("link"): p += f'<a href="{r["link"]}">Website</a>'
            p += "</p>"
            ps.append(p)
    return "\n".join(ps)
# --- End injected helpers ---
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI
# Absolute path helpers for templates and assets
from pathlib import Path

# Base directory of this module
BASE_DIR = Path(__file__).resolve().parent
# Templates directory relative to this module
TEMPLATES_DIR = BASE_DIR / "templates"

client = OpenAI()

# VERSION_MARKER: v-gold-2025-09-16

# ---------- optionale Domain-Bausteine ----------
try:
    from gamechanger_blocks import build_gamechanger_blocks
    from gamechanger_features import GAMECHANGER_FEATURES
    from innovation_intro import INNOVATION_INTRO
except Exception:
    build_gamechanger_blocks = lambda data, feats: []
    GAMECHANGER_FEATURES = {}
    INNOVATION_INTRO = {}

try:
    from websearch_utils import serpapi_search
except Exception:
    serpapi_search = lambda query, num_results=5: []

# ---------- ZIP-Autounpack (Prompts/Kontexte/Daten) ----------
def ensure_unzipped(zip_name: str, dest_dir: str):
    try:
        if os.path.exists(zip_name) and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            with zipfile.ZipFile(zip_name, "r") as zf:
                zf.extractall(dest_dir)
    except Exception:
        pass

ensure_unzipped("prompts.zip", "prompts_unzip")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")
# Automatically unpack additional data archives such as aus-Data.zip.  This
# allows the report generator to find updated CSVs or Markdown tables
# packaged externally.  If aus-Data.zip is present it will be extracted
# into the ``data`` directory the first time this module is imported.
ensure_unzipped("aus-Data.zip", "data")

# ---------- kleine Helfer ----------
def _as_int(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").lower().strip()
    return "de" if l.startswith("de") else "en"

def fix_encoding(text: str) -> str:
    """
    Normalize a text snippet by replacing common problematic unicode characters
    with ASCII equivalents.  This helper is used before any HTML is parsed to
    avoid character encoding issues in the generated report.  It leaves most
    content untouched but ensures dashes and quotes are consistent.
    """
    return (text or "").replace("�", "-").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'")

# Remove hidden or zero‑width unicode characters that sometimes leak from
# questionnaires or copy/paste operations.  Without sanitisation these
# characters show up as squares (e.g. "￾") in the rendered PDF.  Apply to
# every string output produced by the report generator.
def _sanitize_text(value: str) -> str:
    if not value:
        return value
    # Define a set of invisible or problematic code points to remove
    bad_chars = ["\uFFFE", "\uFEFF", "\u200B", "\u00AD"]
    text = str(value)
    for ch in bad_chars:
        text = text.replace(ch, "")
    # Replace legacy model or product names with technology‑agnostic terms.
    # For example, GPT‑3 or GPT‑Analyse is replaced by "LLM‑gestützte Auswertung"
    # to stay vendor neutral.  The replacements apply across all languages.
    replacements = {
        # Vendor-specific model names and phrases
        "GPT-3": "LLM-gestützte Auswertung",
        "GPT‑3": "LLM-gestützte Auswertung",
        # Analysis phrasing
        "GPT-Analyse": "LLM-gestützte Analyse",
        "GPT‑Analyse": "LLM-gestützte Analyse",
        # Technology phrasing
        "GPT-Technologie": "LLM-gestützte Technologie",
        "GPT‑Technologie": "LLM-gestützte Technologie",
        # Generic base phrasing
        "GPT basierte": "LLM-gestützte",
        "GPT‑basierte": "LLM-gestützte",
        # Past participle variations
        "GPT-ausgewerteten": "LLM-gestützten",
        "GPT‑ausgewerteten": "LLM-gestützten",
        "GPT-ausgewertete": "LLM-gestützte",
        "GPT‑ausgewertete": "LLM-gestützte",
        # Prototype references
        "GPT-Prototyp": "KI-Prototyp",
        "GPT‑Prototyp": "KI-Prototyp",
        "GPT-Prototypen": "KI-Prototypen",
        "GPT‑Prototypen": "KI-Prototypen",
        # Gestützte phrasing (both dashed and hyphenated variations)
        "GPT-gestützt": "LLM-gestützte",
        "GPT‑gestützt": "LLM-gestützte",
        "GPT-gestützte": "LLM-gestützte",
        "GPT‑gestützte": "LLM-gestützte",
        "GPT-gestützten": "LLM-gestützten",
        "GPT‑gestützten": "LLM-gestützten",
        # Combined phrases with Auswertung/Technologie
        "GPT-gestützte Auswertung": "LLM-gestützte Auswertung",
        "GPT‑gestützte Auswertung": "LLM-gestützte Auswertung",
        "GPT-gestützte Technologie": "LLM-gestützte Technologie",
        "GPT‑gestützte Technologie": "LLM-gestützte Technologie",
        # Portal/Flow terminology
        "GPT-Portal": "KI-Portal",
        "GPT‑Portal": "KI-Portal",
        "GPT-Flow": "KI-Flow",
        "GPT‑Flow": "KI-Flow",
        # Additional past participle forms (lowercase variants)
        "gpt-ausgewertete": "LLM-gestützte",
        "gpt-ausgewerteten": "LLM-gestützten",
        "gpt-gestützt": "LLM-gestützte"
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new)
    return text

def strip_code_fences(text: str) -> str:
    """
    Entfernt ```-Fences & Backticks, damit Templates nicht 'leere PDFs' produzieren.
    """
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")

def ensure_html(text: str, lang: str = "de") -> str:
    """
    Wenn kein HTML erkennbar, eine einfache HTML-Struktur aus Markdown-ähnlichem Text erzeugen.
    """
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

def _read_md_table(path: str) -> List[dict]:
    """
    Parse a Markdown table into a list of dictionaries.

    This helper supports simple tables with a header line and a
    delimiter line (---).  All subsequent lines are treated as rows.
    Empty or missing cells are converted to the empty string.  If the
    file does not exist or lacks a valid header, an empty list is
    returned.  The function is tolerant of whitespace and ignores
    completely empty lines.

    Parameters
    ----------
    path : str
        The file system path to the Markdown file.  If the file does not
        exist an empty list is returned.

    Returns
    -------
    List[dict]
        A list of row dictionaries keyed by the header names.
    """
    if not os.path.exists(path):
        return []
    try:
        lines = [ln.rstrip("\n") for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]
    except Exception:
        return []
    # A valid markdown table must have at least two lines: header and delimiter
    if len(lines) < 2 or "|" not in lines[0] or "|" not in lines[1]:
        return []
    # Extract header cells, trimming leading/trailing pipes and spaces
    headers = [h.strip().strip("|").strip() for h in lines[0].split("|") if h.strip()]
    rows: List[dict] = []
    # Skip the delimiter row (second line); process subsequent lines as data
    for ln in lines[2:]:
        # Skip lines that do not contain any pipe delimiters
        if "|" not in ln:
            continue
        cells = [c.strip().strip("|").strip() for c in ln.split("|")]
        # Skip completely empty rows
        if not any(cells):
            continue
        # Build row dictionary.  If there are fewer cells than headers,
        # missing values default to an empty string.
        row = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}
        rows.append(row)
    return rows

# -----------------------------------------------------------------------------
# Fallback Vision Generator
#
# In some cases the LLM may fail to produce a vision section (e.g. due to
# missing or invalid input in the questionnaire).  To avoid leaving the
# reader without a vision, we generate a simple fallback based on common
# patterns.  The fallback includes a bold idea tailored to SMEs, a short
# MVP description and three KPIs.  It is localised to the report language.
def fallback_vision(data: dict, lang: str = "de") -> str:
    """
    Generate a default vision section when the LLM does not provide one.

    In the Gold‑Standard version we avoid lists, tables and numeric values.  The
    fallback therefore produces narrative paragraphs describing a bold
    innovation concept for small and medium‑sized enterprises (SMEs).  The
    wording is adapted to the report language (German or English).  This
    function does not rely on the questionnaire data today but can be
    extended in the future to personalise the vision.

    Parameters
    ----------
    data: dict
        The questionnaire data.  Currently unused.
    lang: str
        Report language ("de" or "en").

    Returns
    -------
    str
        An HTML fragment with a heading and narrative paragraphs.
    """
    lang = _norm_lang(lang)
    if lang == "de":
        paragraphs = [
            ("<p><b>Kühne Idee:</b> KI‑Serviceportal für KMU – ein digitales Ökosystem, das "
             "kleinen und mittleren Unternehmen den Zugang zu KI‑gestützten Fragebögen, Tools "
             "und praxisnahen Benchmarks eröffnet. Durch intuitive Workflows und kuratierte "
             "Best‑Practice‑Beispiele entsteht ein Raum, in dem Innovationsimpulse wachsen können.</p>"),
            ("<p>Als erster Schritt könnten Sie einen schlanken Prototypen aufsetzen, der ein "
             "Fragebogen‑Tool mit unmittelbarem Feedback und einer unkomplizierten Terminvereinbarung "
             "kombiniert. Dieses Portal dient als Drehscheibe für Ihr KI‑Programm und erleichtert "
             "Ihren Kundinnen und Kunden den Einstieg.</p>"),
            ("<p>Langfristig entwickelt sich das Portal zu einem lebendigen Wissenswerk, das "
             "Erfahrungen aus unterschiedlichen Projekten zusammenführt und Ihnen hilft, neue "
             "Dienstleistungen zu entwickeln. Es geht nicht um nackte Zahlen, sondern um eine "
             "gemeinsame Lernreise, bei der Sie sich als Vorreiter im Mittelstand positionieren.</p>")
        ]
    else:
        paragraphs = [
            ("<p><b>Bold idea:</b> AI service portal for SMEs – a digital ecosystem that opens up "
             "AI‑powered questionnaires, tools and practical benchmarks to small and midsized "
             "businesses. By providing intuitive workflows and curated best‑practice examples, "
             "it creates a space where innovation impulses can flourish.</p>"),
            ("<p>As an initial step you might build a lean prototype combining a questionnaire "
             "tool, immediate feedback and an easy appointment system. This portal will be the hub "
             "for your AI programme, guiding your clients gently into the world of AI.</p>"),
            ("<p>Over time, the portal evolves into a living knowledge platform that brings together "
             "experience from diverse projects and helps you develop new services. The focus is not "
             "on numbers but on a shared learning journey where you position yourself as an "
             "innovator in your industry.</p>")
        ]
    return "".join(paragraphs)

# -----------------------------------------------------------------------------
# Fallback practice example loader
#
# When the language model returns a case study from an unrelated industry
# (e.g. Maschinenbau instead of Consulting), we need a deterministic
# alternative.  This helper reads ``data/praxisbeispiele.md`` and extracts the
# first case for the specified branch.  It transforms the bullet points
# (Problem, Lösung, Ergebnis) into a short descriptive paragraph and applies
# the number/list sanitiser.  If no matching branch is found, it falls back
# to the "Sonstige" section.  Returns an HTML paragraph.
def _fallback_praxisbeispiel(branche: str, lang: str = "de") -> str:
    try:
        # Normalise branch name for matching
        br = (branche or "").strip().lower()
        branch_map = {
            "beratung": "Beratung & Dienstleistungen",
            "dienstleistungen": "Beratung & Dienstleistungen",
            "it": "IT & Software",
            "it & software": "IT & Software",
            "marketing": "Marketing & Werbung",
            "werbung": "Marketing & Werbung",
            "bau": "Bauwesen",
            "bausektor": "Bauwesen",
            "industrie": "Industrie/Produktion",
            "produktion": "Industrie/Produktion",
            "finanzen": "Finanzen & Versicherungen",
            "versicherung": "Finanzen & Versicherungen",
            "gesundheit": "Gesundheitswesen",
            "gesundheitswesen": "Gesundheitswesen",
            "handel": "Handel & E-Commerce",
            "e-commerce": "Handel & E-Commerce",
            "bildung": "Bildung",
            "handwerk": "Handwerk",
            "sonstige": "Sonstige",
        }
        header = branch_map.get(br, None)
        md_path = Path(__file__).resolve().parent / "data" / "praxisbeispiele.md"
        if not md_path.exists():
            return ""
        content = md_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        # Locate the branch section
        start = None
        header_pattern = f"## {header}" if header else None
        if header_pattern:
            for idx, ln in enumerate(lines):
                if ln.strip().lower() == header_pattern.lower():
                    start = idx
                    break
        # Fallback to Sonstige if branch not found
        if start is None:
            for idx, ln in enumerate(lines):
                if ln.strip().lower() == "## sonstige":
                    start = idx
                    break
        if start is None:
            return ""
        # Extract lines until next section
        section_lines: List[str] = []
        for ln in lines[start + 1:]:
            if ln.startswith("## "):
                break
            section_lines.append(ln)
        # Find first case block after a "Case" marker
        case_lines: List[str] = []
        in_case = False
        for ln in section_lines:
            if ln.strip().startswith("**Case"):
                if in_case:
                    break
                in_case = True
                continue
            if in_case:
                if not ln.strip():
                    break
                case_lines.append(ln)
        # Combine bullet lines into a descriptive sentence
        text_parts: List[str] = []
        for ln in case_lines:
            stripped = ln.strip().lstrip("- •*").strip()
            if not stripped:
                continue
            # Replace heading prefixes with more narrative phrases
            lowered = stripped.lower()
            if lowered.startswith("pain point"):
                stripped = stripped.split(":", 1)[-1].strip()
                stripped = "Problem: " + stripped
            elif lowered.startswith("ki-lösung") or lowered.startswith("ki‑lösung"):
                stripped = stripped.split(":", 1)[-1].strip()
                stripped = "Lösung: " + stripped
            elif lowered.startswith("outcome"):
                stripped = stripped.split(":", 1)[-1].strip()
                stripped = "Ergebnis: " + stripped
            text_parts.append(stripped)
        description = " ".join(text_parts)
        # Strip any markdown emphasis
        description = description.replace("**", "").replace("__", "")
        # Sanitise numbers and lists
        description = _strip_lists_and_numbers(description)
        return f"<p>{description}</p>"
    except Exception:
        return ""
# gpt_analyze.py — Gold-Standard (Teil 2/4)

def is_self_employed(data: dict) -> bool:
    keys_text = ["beschaeftigungsform", "beschäftigungsform", "arbeitsform", "rolle", "role", "occupation", "unternehmensform", "company_type"]
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

    # -------------------------------------------------------------------------
    # Normalize and classify the company size.  Many prompts rely on a unified
    # variable name (company_size_label) and a category (company_size_category)
    # to tailor recommendations.  Without this classification the templates
    # cannot personalise the content or generate the correct feedback links.
    # Determine the employee count from various possible fields.  If the
    # organisation is self‑employed (solo) this overrides other counts.
    def _get_employee_count(d: dict) -> Optional[int]:
        for key in [
            "mitarbeiter", "mitarbeiterzahl", "anzahl_mitarbeiter", "employees",
            "employee_count", "team_size", "anzahl_mitarbeiterinnen"
        ]:
            v = d.get(key)
            n = _as_int(v)
            if n is not None:
                return n
        # sometimes the size is encoded as a string category like "Solo",
        # "2-10", "11-100"; extract lower bound
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
    # Determine the category and human‑readable label based on language
    category = "solo" if self_emp else None
    if category is None:
        if emp_count is None:
            # fallback: if no information, treat as team
            category = "team"
        elif emp_count <= 1:
            category = "solo"
        elif emp_count <= 10:
            category = "team"
        else:
            category = "kmu"
    # Assign labels per language
    if lang == "de":
        if category == "solo":
            label = "Solo-Unternehmer:in"
        elif category == "team":
            label = "Team (2–10 Mitarbeitende)"
        else:
            label = "KMU (11+ Mitarbeitende)"
    else:
        if category == "solo":
            label = "Solo entrepreneur"
        elif category == "team":
            label = "Small team (2–10 people)"
        else:
            label = "SME (11+ people)"

    context["company_size_category"] = category
    context["company_size_label"] = label
    # Provide backwards‑compatibility aliases
    context["unternehmensgroesse"] = label  # German alias used in some templates
    context["self_employed"] = "Yes" if self_emp else "No"
    context["selbststaendig"] = "Ja" if self_emp and lang == "de" else ("Nein" if lang == "de" else context["self_employed"])
    # Normalise company_form: if provided, leave as is; else derive from context
    cf = context.get("rechtsform") or context.get("company_form") or context.get("legal_form")
    context["company_form"] = cf or ""
    # Set the branch name.  For English reports, translate common German branch names to
    # their English counterparts to prevent untranslated terms like "Beratung" appearing
    # in the output.  If a branch is unknown, fall back to the original name.
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
            "verwaltung": "public administration"
        }
        context["branche"] = _branch_translations.get(branche.lower(), branche)
    else:
        context["branche"] = branche
    context.setdefault("copyright_year", datetime.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")
    context.setdefault("company_size", _as_int(data.get("mitarbeiterzahl") or data.get("employees") or 1) or 1)
    context["is_self_employed"] = is_self_employed(data)

    # bequeme Aliase
    context["hauptleistung"] = context.get("hauptleistung") or context.get("main_service") or context.get("hauptprodukt") or ""
    context["projektziel"] = context.get("projektziel") or context.get("ziel") or ""
    return context

def add_innovation_features(context, branche, data):
    context["branchen_innovations_intro"] = INNOVATION_INTRO.get(branche, "")
    try:
        context["gamechanger_blocks"] = build_gamechanger_blocks(data, GAMECHANGER_FEATURES)
    except Exception:
        context["gamechanger_blocks"] = []
    return context

def add_websearch_links(context, branche, projektziel):
    year = datetime.now().year
    try:
        context["websearch_links_foerder"] = serpapi_search(
            f"aktuelle Förderprogramme {branche} {projektziel} Deutschland {year}", num_results=5
        )
        context["websearch_links_tools"] = serpapi_search(
            f"aktuelle KI-Tools {branche} Deutschland {year}", num_results=5
        )
    except Exception:
        context["websearch_links_foerder"] = []
        context["websearch_links_tools"] = []
    return context

def render_prompt(template_text: str, context: dict) -> str:
    def replace_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)
    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template_text)
    def replace_simple(m):
        key = m.group(1); val = context.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, template_text)

def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
    """
    Construct the full prompt for a given chapter and language.

    In the Gold‑Standard, we intentionally restrict prompt resolution to the
    canonical `prompts/{lang}/{chapter}.md` file and avoid falling back to
    legacy directories (e.g. `prompts_unzip`, `de_unzip`). This ensures that
    only the most up‑to‑date templates are used and prevents stale versions
    from overriding new content.
    """
    # Always prefer the primary prompts directory.  Do not use fallback paths.
    primary_path = f"prompts/{lang}/{chapter}.md"
    if os.path.exists(primary_path):
        try:
            prompt_text = load_text(primary_path)
        except Exception:
            prompt_text = None
    else:
        prompt_text = None
    if not prompt_text:
        # No prompt found in the expected location.
        prompt_text = f"[NO PROMPT FOUND for {chapter}/{lang}]"

    # Render the prompt with context variables.  Support {{ var }} and {{ list|join(', ') }} syntax.
    prompt = render_prompt(prompt_text, context)
    is_de = (lang == "de")
    #
    # In der Gold‑Standard-Version sollen alle Kapitel in warmen, narrativen Absätzen
    # formuliert werden. Listen (<ul>, <ol>) und Tabellen sollen vermieden
    # werden. Stattdessen sollen zusammenhängende Absätze entstehen, die
    # Beispiele und Best‑Practice‑Geschichten integriert erzählen. Die
    # folgenden Regeln definieren dieses Verhalten global für alle Kapitel.
    base_rules = (
        "Gib die Antwort ausschließlich als gültiges HTML ohne <html>-Wrapper zurück. "
        "Verwende nur <h3> und <p>. Keine Listen, keine Tabellen, keine Aufzählungen. "
        "Formuliere 2–3 zusammenhängende Absätze mit freundlicher, motivierender Sprache. "
        "Integriere Best‑Practice‑Beispiele als kurze Geschichten. Keine Zahlen oder Prozentwerte."
        if is_de else
        "Return VALID HTML only (no <html> wrapper). Use only <h3> and <p>. "
        "Avoid lists and tables. Write 2–3 connected paragraphs in a warm, motivating tone. "
        "Integrate best‑practice examples as short stories. Do not include numbers or percentages."
    )
    style = "\n\n---\n" + base_rules

    # Keine kapitelabhängigen Listen- oder Tabellenvorgaben mehr; die Prompts selbst
    # enthalten bereits den inhaltlichen Rahmen (z. B. Abschnittsüberschriften). Wir
    # fügen hier keine zusätzlichen Anweisungen hinzu.
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
    context = add_innovation_features(context, branche, data)
    context = add_websearch_links(context, branche, context.get("projektziel", ""))
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f: md = f.read()
            ctx_list = [f"<li>{ln[2:].strip()}</li>" for ln in md.splitlines() if ln.strip().startswith("- ")]
            context["checklisten"] = "<ul>" + "\n".join(ctx_list) + "</ul>" if ctx_list else ""
        else:
            context["checklisten"] = ""
    prompt = build_masterprompt(chapter, context, lang)
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model
    section_text = _chat_complete(
        messages=[
            {
                "role": "system",
                "content": (
                    "Sie sind TÜV-zertifizierte:r KI-Manager:in, KI-Strategieberater:in sowie Datenschutz- und Fördermittel-Expert:in. "
                    "Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
                )
                if lang == "de"
                else (
                    "You are a TÜV-certified AI manager and strategy consultant. "
                    "Deliver precise, actionable, up-to-date, sector-relevant content as HTML."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model_name=model_name,
        temperature=None,
    )
    return section_text

def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(strip_code_fences(fix_encoding(html)), lang)
# gpt_analyze.py — Gold-Standard (Teil 3/4)

def build_chart_payload(data: dict, score_percent: int, lang: str = "de") -> dict:
    def as_int(v, d=0):
        try: return int(v)
        except Exception: return d

    auto_map = {"sehr_niedrig": 1, "eher_niedrig": 2, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5,
                "very_low": 1, "rather_low": 2, "medium": 3, "rather_high": 4, "very_high": 5}
    pap_map  = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5}
    know_map = {"keine": 1, "grundkenntnisse": 2, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5,
                "none": 1, "basic": 2, "medium": 3, "advanced": 4, "expert": 5}
    dq_map   = {"hoch": 5, "mittel": 3, "niedrig": 1, "high": 5, "medium": 3, "low": 1}
    roadmap_map = {"ja": 5, "in_planung": 3, "nein": 1, "yes": 5, "planning": 3, "no": 1}
    gov_map  = {"ja": 5, "teilweise": 3, "nein": 1, "yes": 5, "partial": 3, "no": 1}
    inov_map = {"sehr_offen": 5, "eher_offen": 4, "neutral": 3, "eher_zurueckhaltend": 2, "sehr_zurückhaltend": 1,
                "very_open": 5, "rather_open": 4, "neutral": 3, "rather_reluctant": 2, "very_reluctant": 1}

    dataset = [
        as_int(data.get("digitalisierungsgrad", 1), 1),
        auto_map.get(str(data.get("automatisierungsgrad", "")).lower(), 1),
        pap_map.get(str(data.get("prozesse_papierlos", "0-20")).lower(), 1),
        know_map.get(str(data.get("ki_knowhow", data.get("ai_knowhow", "keine"))).lower(), 1),
        as_int(data.get("risikofreude", data.get("risk_appetite", 1)), 1),
        dq_map.get(str(data.get("datenqualitaet", data.get("data_quality", ""))).lower(), 0),
        roadmap_map.get(str(data.get("ai_roadmap", "")).lower(), 0),
        gov_map.get(str(data.get("governance", "")).lower(), 0),
        inov_map.get(str(data.get("innovationskultur", data.get("innovation_culture", ""))).lower(), 0),
    ]
    labels_de = ["Digitalisierung","Automatisierung","Papierlos","KI-Know-how","Risikofreude","Datenqualität","Roadmap","Governance","Innovationskultur"]
    labels_en = ["Digitalisation","Automation","Paperless","AI know-how","Risk appetite","Data quality","AI roadmap","Governance","Innovation culture"]
    labels = labels_de if lang == "de" else labels_en

    risk_level = 1
    dq, gov, roadmap = dataset[5], dataset[7], dataset[6]
    if dq == 1 or gov == 1: risk_level = 3
    elif roadmap in {1,3}:  risk_level = 2

    return {"score": score_percent, "dimensions": {"labels": labels, "values": dataset}, "risk_level": risk_level}

def _weights_from_env() -> Dict[str, int]:
    raw = os.getenv("SCORE_WEIGHTS")
    if not raw: return {}
    try: return {k:int(v) for k,v in json.loads(raw).items()}
    except Exception: return {}

def calc_score_percent(data: dict) -> int:
    """
    Deprecated global readiness score.

    The Gold‑Standard version of the KI‑Readiness report no longer uses an
    aggregated readiness score. To maintain backwards compatibility this
    function now always returns ``0``.  The individual readiness dimensions
    (digitalisation, automation, paperless processes and AI know‑how) are
    displayed separately as KPI tiles instead of a single score.
    """
    # Previously this function computed an average of the digitalisation and
    # automation degrees.  Returning zero ensures any legacy code expecting
    # an integer still functions without surfacing a misleading aggregate.
    return 0

def build_funding_table(data: dict, lang: str = "de", max_items: int = 8) -> List[Dict[str, str]]:
    import csv, os
    # Determine the path to the funding CSV.  Prefer the ``data`` directory, then
    # nested ``data/data`` and finally a project‑root CSV.  If no CSV exists
    # the subsequent fallback will use a Markdown file.
    path = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path):
        alt = os.path.join("data", "data", "foerdermittel.csv")
        if os.path.exists(alt):
            path = alt
        else:
            root_csv = "foerdermittel.csv"
            if os.path.exists(root_csv):
                path = root_csv
    # Load rows from the CSV if present.  We read the raw CSV rows without
    # filtering so that the filtering logic below operates on the full set.
    rows: List[Dict[str, str]] = []
    if os.path.exists(path):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
        except Exception:
            rows = []
    # If no rows were loaded from the CSV, attempt to parse a Markdown table
    # stored alongside the data.  This fallback allows the report to function
    # when only a ``check_foerdermittel.md`` file is provided (e.g. when the
    # user packages data in MD format).  A missing or invalid MD file will
    # simply result in an empty list and thus no funding entries.
    if not rows:
        md_path = os.path.join("data", "check_foerdermittel.md")
        rows = _read_md_table(md_path)
    # Determine the respondent's company size and map to target group tokens.
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    # Expand the target group synonyms to recognise more variations used in the
    # funding dataset.  Solo entrepreneurs and startups are often described
    # interchangeably, so include related terms such as "startups", "start‑up",
    # "gründung" and synonyms for self‑employment.  The team and SME buckets
    # likewise accept broader descriptors.  This ensures that entries with
    # slightly different spellings (e.g. "Startups", "Gründungs", "soloselbstständig")
    # are considered a match.
    targets_map = {
        "solo": [
            "solo", "solo-", "solo/self", "freelancer", "freiberuflich", "einzel",
            # Solo-Profiles often fall under "kmu" in the funding database.  Include "kmu"
            # here so that small one-person businesses also match SME funding programmes.
            "kmu",
            "startups", "startup", "start-up", "start-up", "gründung", "gründungs",
            "unternehmer", "gründer", "selbstständig", "soloselbstständig", "soloselbststaendig", "freiberufler"
        ],
        "team": [
            "team", "small", "kmu", "kmus", "startup", "startups", "start-up",
            "gründung", "gründungs", "selbstständig", "selbststaendig"
        ],
        "kmu": [
            "kmu", "kmus", "sme", "mittelstand", "small", "mid-sized"
        ]
    }
    targets = targets_map.get(size, [])
    # Normalise the requested region and map common abbreviations to full names.
    region = (data.get("bundesland") or data.get("state") or "").lower()
    alias_map = {
        "nrw": "nordrhein-westfalen",
        "by": "bayern",
        "bw": "baden-württemberg",
        "be": "berlin",
        "bb": "brandenburg",
        "he": "hessen",
        "hh": "hamburg",
        "sl": "saarland",
        "sn": "sachsen",
        "st": "sachsen-anhalt",
        "sh": "schleswig-holstein",
        "th": "thüringen",
        "mv": "mecklenburg-vorpommern",
        "rp": "rheinland-pfalz",
        "ni": "niedersachsen",
        "hb": "bremen",
        "nds": "niedersachsen",
    }
    region = alias_map.get(region, region)
    # Build a list of selected funding rows that match the target group and
    # region criteria.  Normalise strings to lower case before comparison.  If
    # no targets are specified we accept all entries.  We also accept
    # federal programmes (region == "bund").
    selected: List[Dict[str, str]] = []
    for row in rows:
        # Guard against non‑dict rows (may come from MD parser)
        if not isinstance(row, dict):
            continue
        zg = ((row.get("Zielgruppe") or "").lower()) if isinstance(row.get("Zielgruppe"), str) else ""
        reg = ((row.get("Region") or "").lower()) if isinstance(row.get("Region"), str) else ""
        # Filter by target group
        t_ok = True if not targets else any(t in zg for t in targets)
        # Filter by region: if region is specified, require exact region or federal (bund)
        r_ok = True if not region else (reg == region or reg == "bund")
        if t_ok and r_ok:
            selected.append({
                "name": row.get("Name", ""),
                "zielgruppe": row.get("Zielgruppe", ""),
                "region": row.get("Region", ""),
                "foerderhoehe": row.get("Fördersumme (€)", ""),
                "zweck": row.get("Beschreibung", row.get("Purpose", "")),
                "deadline": row.get("Deadline", ""),
                "link": row.get("Link", "")
            })
    # Sort the selected entries: exact regional matches first, then federal (bund), then others.
    if region:
        selected = sorted(
            selected,
            key=lambda p: 0 if ((p.get("region", "").lower()) == region) else (1 if ((p.get("region", "").lower()) == "bund") else 2)
        )

        # Ensure that at least two region‑specific programmes are present.  If
        # there are fewer than two region matches in the initial selection,
        # search the full dataset for additional entries matching the
        # respondent's region and append them.  This prevents the table from
        # listing mostly federal programmes when suitable local programmes
        # exist.  Duplicate entries are avoided by checking against the
        # selected list.  Only names and essential fields are extracted to
        # preserve privacy and formatting.
        region_specific = [p for p in selected if p.get("region", "").lower() == region]
        if len(region_specific) < 2:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if ((row.get("Region") or "").lower()) == region:
                    candidate = {
                        "name": row.get("Name", ""),
                        "zielgruppe": row.get("Zielgruppe", ""),
                        "region": row.get("Region", ""),
                        "foerderhoehe": row.get("Fördersumme (€)", ""),
                        "zweck": row.get("Beschreibung", row.get("Purpose", "")),
                        "deadline": row.get("Deadline", ""),
                        "link": row.get("Link", "")
                    }
                    # only append if not already selected
                    if not any((candidate.get("name") == s.get("name") and candidate.get("region") == s.get("region")) for s in selected):
                        selected.append(candidate)
                        region_specific.append(candidate)
                    if len(region_specific) >= 2:
                        break

        # Guarantee inclusion of the Berlin Gründungsbonus when the region is Berlin.
        # The existing selection may exclude this programme if the target group
        # filtering misses the "Startups" tag.  Explicitly add it by name when
        # appropriate.
        if region == "berlin":
            found = any("gründungsbonus berlin" in (p.get("name") or "").lower() for p in selected)
            if not found:
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    name_lc = (row.get("Name", "").lower())
                    if "gründungsbonus" in name_lc and "berlin" in name_lc:
                        candidate = {
                            "name": row.get("Name", ""),
                            "zielgruppe": row.get("Zielgruppe", ""),
                            "region": row.get("Region", ""),
                            "foerderhoehe": row.get("Fördersumme (€)", ""),
                            "zweck": row.get("Beschreibung", row.get("Purpose", "")),
                            "deadline": row.get("Deadline", ""),
                            "link": row.get("Link", "")
                        }
                        if not any((candidate.get("name") == s.get("name") and candidate.get("region") == s.get("region")) for s in selected):
                            selected.append(candidate)
                        break

    # Finally, cap the list to the maximum number of items.  The max_items
    # parameter is raised to 8 in the Gold‑Standard to provide a richer set
    # of programmes while still keeping the table concise.  If the caller
    # specifies a smaller value via the function argument, that override is
    # respected.
    return selected[:max_items]

def build_tools_table(data: dict, branche: str, lang: str = "de", max_items: int = 8) -> List[Dict[str, str]]:
    """
    Assemble a list of AI tools filtered by the respondent's industry/branch.

    The original tools CSV uses German column names such as "Tool-Name"
    and "Funktion/Zweck" rather than the English names used in earlier
    iterations.  To support both formats, this function now attempts to
    retrieve values from multiple possible column headings.  It also
    gracefully handles missing cost information by falling back to the
    effort (Aufwand) fields.

    Parameters
    ----------
    data: dict
        The questionnaire response data.  Not currently used but kept for
        consistency with other build_* functions.
    branche: str
        A lowercased branch name to filter tools.  If empty, no filter is
        applied.
    lang: str
        Language code (unused here but reserved for future localisation).
    max_items: int
        Maximum number of tools to return.

    Returns
    -------
    List[Dict[str, str]]
        A list of dicts with keys ``name``, ``usecase``, ``cost`` and ``link``.
    """
    import csv, os
    # Determine the CSV path.  By default the file is extracted to the
    # `data` directory when `data.zip` is unzipped.  If this path does not
    # exist (e.g. when running outside the unzipped context), fall back to
    # a top‑level ``tools.csv`` so that updated tool information is still
    # loaded.  Without a valid CSV we return an empty list.
    # Try to locate the tools CSV in a variety of locations.  When running
    # outside of the original repository context there may be no ``data``
    # directory at the project root.  To remain robust we attempt the
    # conventional ``data/tools.csv`` first, then fall back to a top level
    # ``tools.csv``, and finally look inside the nested backend folder used
    # during development (``ki_backend/make-ki-backend-neu-main/data/tools.csv``).
    # Locate the tools CSV by searching several potential paths.  We prefer the
    # ``data/tools.csv`` location but fall back to a project‑root CSV or the
    # nested backend CSV.  If none exist, we will later attempt to parse
    # a Markdown table.
    path = os.path.join("data", "tools.csv")
    if not os.path.exists(path):
        for cand in [
            "tools.csv",
            os.path.join("ki_backend", "make-ki-backend-neu-main", "data", "tools.csv"),
        ]:
            if os.path.exists(cand):
                path = cand
                break
    rows_csv: List[dict] = []
    # Read the CSV if available
    if os.path.exists(path):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                rows_csv = list(csv.DictReader(f))
        except Exception:
            rows_csv = []
    # If the CSV is empty or missing, attempt to parse a Markdown table in
    # ``data/tools.md``.  This fallback ensures tool information is still
    # available when provided in markdown format.
    if not rows_csv:
        md_tools = os.path.join("data", "tools.md")
        rows_csv = _read_md_table(md_tools)
    out: List[Dict[str, str]] = []
    # Determine the respondent's company size category to filter tools by size.
    size = (data.get("company_size_category") or data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    if size:
        if "solo" in size:
            user_size = "solo"
        elif "team" in size or "2" in size or "10" in size:
            user_size = "team"
        elif "kmu" in size or "11" in size:
            user_size = "kmu"
        else:
            user_size = ""
    else:
        user_size = ""
    # Iterate over the parsed rows (CSV or MD) and apply filtering by branch and
    # company size.  Column names may vary between datasets so we attempt
    # multiple fallbacks for each field.
    for row in rows_csv:
        if not isinstance(row, dict):
            continue
        # Skip comment or header rows that start with '#'
        name_field = row.get("Tool-Name") or row.get("Name") or row.get("Tool") or ""
        if isinstance(name_field, str) and name_field.strip().startswith("#"):
            continue
        # Branch tags may be under "Branche-Slugs", "Tags" or "Branche"
        tags = (row.get("Branche-Slugs") or row.get("Tags") or row.get("Branche") or "").lower()
        row_size = (row.get("Unternehmensgröße") or row.get("Unternehmensgroesse") or row.get("Unternehmensgröße (DE)") or "").lower()
        # Filter by branch if provided
        if branche:
            if tags and branche not in tags:
                continue
        # Filter by company size: include if row_size is empty ("alle") or matches
        # the user's size or is more general (e.g. "kmu" applies to both team and kmu)
        if user_size:
            if row_size and row_size not in ("alle", user_size):
                # Allow kmu tools for team and solo, and team tools for solo
                if not ((row_size == "kmu" and user_size in ("team", "kmu")) or (row_size == "team" and user_size == "solo")):
                    continue
        # Prepare fields with fallbacks
        name = name_field
        usecase = row.get("Funktion/Zweck") or row.get("Einsatz") or row.get("Usecase") or row.get("Funktion") or ""
        # English use-case labels (friendly wording)
        if lang and str(lang).lower().startswith("en"):
            de2en = {
                "Projektmanagement": "Project management",
                "Online-Whiteboard & KI-Brainstorming": "Online whiteboard & AI brainstorming",
                "Automatisierung": "Automation",
                "KI-Content & Text": "AI content & text",
                "Consulting-Wissensmanagement": "Consulting knowledge management",
                "Teamkommunikation & Chat": "Team communication & chat",
                "CRM & Vertriebsmanagement": "CRM & sales management"
            }
            if isinstance(usecase, str):
                usecase = de2en.get(usecase, usecase)
        cost_raw = (
            row.get("Kosten")
            or row.get("Cost")
            or row.get("Aufwand")
            or row.get("Beispiel-Aufwand")
            or row.get("Kostenkategorie")
            or ""
        )
        # Local helper to map cost codes to descriptive categories
        def _map_cost(value: str, lang: str) -> str:
            if not value:
                return ""
            v = str(value).strip()
            try:
                n = int(float(v))
            except Exception:
                n = None
            if lang.lower().startswith("de"):
                num_map = {1: "sehr gering", 2: "gering", 3: "mittel", 4: "hoch", 5: "sehr hoch"}
                cat_map = {
                    "sehr gering": "sehr gering",
                    "gering": "gering",
                    "mittel": "mittel",
                    "hoch": "hoch",
                    "sehr hoch": "sehr hoch",
                }
            else:
                num_map = {1: "very low", 2: "low", 3: "medium", 4: "high", 5: "very high"}
                cat_map = {
                    "sehr gering": "very low",
                    "gering": "low",
                    "mittel": "medium",
                    "hoch": "high",
                    "sehr hoch": "very high",
                }
            if n is not None and n in num_map:
                return num_map[n]
            lv = v.lower()
            for key, translated in cat_map.items():
                if lv == key:
                    return translated
            return v
        cost = _map_cost(cost_raw, lang)
        if not cost:
            cost = "n/a"
        link = row.get("Link/Website") or row.get("Link") or row.get("Website") or row.get("URL") or ""
        datenschutz = row.get("Datenschutz") or row.get("Datensitz") or row.get("Datensitz (EU/US)") or row.get("Datenschutz (EU/US)") or ""
        if not datenschutz:
            datenschutz = "n/a"
        out.append({
            "name": name,
            "usecase": usecase,
            "cost": cost,
            "link": link,
            "datenschutz": datenschutz
        })
    # If few tools were matched, enrich with defaults.  Maintain at least one
    # open‑source alternative and fill up to max_items with a curated list.  We
    # always ensure cost and datenschutz fields are set.
    try:
        min_needed = max(0, max_items - len(out))
        open_source_names = {"OpenProject", "EspoCRM", "Mattermost"}
        if lang.lower().startswith("de"):
            defaults = [
                {"name": "Notion", "usecase": "Wissensmanagement & Projektplanung", "cost": "sehr gering", "link": "https://www.notion.so", "datenschutz": "USA/EU"},
                {"name": "Zapier", "usecase": "Automatisierung & Integration", "cost": "gering", "link": "https://zapier.com", "datenschutz": "USA/EU"},
                {"name": "Asana", "usecase": "Projekt- und Aufgabenmanagement", "cost": "sehr gering", "link": "https://asana.com", "datenschutz": "USA/EU"},
                {"name": "Miro", "usecase": "Visuelle Zusammenarbeit & Brainstorming", "cost": "gering", "link": "https://miro.com", "datenschutz": "USA/EU"},
                {"name": "Jasper", "usecase": "KI-gestützte Texterstellung", "cost": "gering", "link": "https://www.jasper.ai", "datenschutz": "USA"},
                {"name": "Slack", "usecase": "Teamkommunikation & Kollaboration", "cost": "sehr gering", "link": "https://slack.com", "datenschutz": "USA"},
                {"name": "n8n", "usecase": "No-Code Automatisierung", "cost": "gering", "link": "https://n8n.io", "datenschutz": "EU"},
                {"name": "OpenProject", "usecase": "Projektmanagement & Aufgabenverwaltung", "cost": "sehr gering", "link": "https://www.openproject.org", "datenschutz": "EU"},
                {"name": "EspoCRM", "usecase": "CRM & Vertriebsmanagement", "cost": "sehr gering", "link": "https://www.espocrm.com", "datenschutz": "EU"},
                {"name": "Mattermost", "usecase": "Teamkommunikation & Chat", "cost": "sehr gering", "link": "https://mattermost.com", "datenschutz": "EU"},
            ]
        else:
            defaults = [
                {"name": "Notion", "usecase": "Knowledge management & project planning", "cost": "very low", "link": "https://www.notion.so", "datenschutz": "USA/EU"},
                {"name": "Zapier", "usecase": "Automation & integration", "cost": "low", "link": "https://zapier.com", "datenschutz": "USA/EU"},
                {"name": "Asana", "usecase": "Project & task management", "cost": "very low", "link": "https://asana.com", "datenschutz": "USA/EU"},
                {"name": "Miro", "usecase": "Visual collaboration & brainstorming", "cost": "low", "link": "https://miro.com", "datenschutz": "USA/EU"},
                {"name": "Jasper", "usecase": "AI-powered content generation", "cost": "low", "link": "https://www.jasper.ai", "datenschutz": "USA"},
                {"name": "Slack", "usecase": "Team communication & collaboration", "cost": "very low", "link": "https://slack.com", "datenschutz": "USA"},
                {"name": "n8n", "usecase": "No-code automation", "cost": "low", "link": "https://n8n.io", "datenschutz": "EU"},
                {"name": "OpenProject", "usecase": "Project management & task tracking", "cost": "very low", "link": "https://www.openproject.org", "datenschutz": "EU"},
                {"name": "EspoCRM", "usecase": "CRM & sales management", "cost": "very low", "link": "https://www.espocrm.com", "datenschutz": "EU"},
                {"name": "Mattermost", "usecase": "Team communication & chat", "cost": "very low", "link": "https://mattermost.com", "datenschutz": "EU"},
            ]
        # Insert open-source tools if not present
        for t in defaults:
            if t["name"] in open_source_names and all((t["name"] != existing.get("name")) for existing in out):
                if not t.get("datenschutz"):
                    t["datenschutz"] = "n/a"
                if not t.get("cost"):
                    t["cost"] = "n/a"
                out.append(t)
        # Append further defaults if too few tools were matched
        if len(out) < 4 and min_needed > 0:
            for t in defaults:
                if len(out) >= max_items:
                    break
                if any((t["name"] == existing.get("name")) for existing in out):
                    continue
                if not t.get("datenschutz"):
                    t["datenschutz"] = "n/a"
                if not t.get("cost"):
                    t["cost"] = "n/a"
                out.append(t)
        # Ensure at least one open-source tool for teams and SMEs
        try:
            size_raw = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
        except Exception:
            size_raw = ""
        if size_raw in {"team", "kmu", "kmus", "kmu (11–100)", "11-100", "2-10"}:
            has_os = any(item.get("name") in open_source_names for item in out)
            if not has_os:
                for t in defaults:
                    if t["name"] in open_source_names and all((t["name"] != existing.get("name")) for existing in out):
                        if not t.get("datenschutz"):
                            t["datenschutz"] = "n/a"
                        if not t.get("cost"):
                            t["cost"] = "n/a"
                        out.append(t)
                        break
    except Exception:
        pass
    return out[:max_items]

def build_dynamic_funding(data: dict, lang: str = "de", max_items: int = 5) -> str:
    import csv, os
    path = os.path.join("data", "foerdermittel.csv")
    # If the expected file is missing (e.g. due to nested archive structure),
    # fall back to a nested ``data/data/foerdermittel.csv`` or a top‑level
    # ``foerdermittel.csv`` before aborting.  This makes the function more
    # resilient to different project layouts and ensures the dynamic funding
    # section is populated even when the ``data`` directory is absent.
    if not os.path.exists(path):
        alt1 = os.path.join("data", "data", "foerdermittel.csv")
        alt2 = "foerdermittel.csv"
        if os.path.exists(alt1):
            path = alt1
        elif os.path.exists(alt2):
            path = alt2
        else:
            return ""
    try:
        with open(path, newline="", encoding="utf-8") as csvfile:
            programmes = list(csv.DictReader(csvfile))
            # Filter out empty or null rows to avoid NoneType errors.  Some CSV files
            # may contain blank lines or partially filled rows; these produce
            # dictionaries with all values None.  Skip such entries.
            programmes = [p for p in programmes if p and any(v for v in p.values())]
    except Exception:
        return ""
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    # Expand the target group mapping: solo respondents may also be eligible for KMU programmes, since
    # many funding schemes target both freelancers and small businesses.  We include common
    # synonyms to improve matching.  For teams and KMU we include general SME terms.
    # Expand the target group mapping: Solo respondents may also be eligible for
    # programmes targeting KMU/startups since many funding schemes use diverse
    # terminology (e.g. "Start-up", "Gründung").  Add common synonyms here.
    targets = {
        "solo": ["solo", "freelancer", "freiberuflich", "einzel", "kmu", "startup", "start-up", "gründung", "gründungs", "unternehmer"] ,
        "team": ["kmu", "team", "small"],
        "kmu": ["kmu", "sme"]
    }.get(size, [])
    region = (data.get("bundesland") or data.get("state") or "").strip()
    region_lower = region.lower()
    # Map Bundesland abbreviations to full names to improve region matching
    alias_map = {
        "nrw": "nordrhein-westfalen",
        "by": "bayern",
        "bw": "baden-württemberg",
        "be": "berlin",
        "bb": "brandenburg",
        "he": "hessen",
        "hh": "hamburg",
        "sl": "saarland",
        "sn": "sachsen",
        "st": "sachsen-anhalt",
        "sh": "schleswig-holstein",
        "th": "thüringen",
        "mv": "mecklenburg-vorpommern",
        "rp": "rheinland-pfalz",
        "ni": "niedersachsen",
        # Additional abbreviations for Bremen and Niedersachen to increase coverage
        "hb": "bremen",
        "nds": "niedersachsen",
    }
    # Use the mapped region if available; otherwise fall back to the original
    region_mapped = alias_map.get(region_lower, region_lower)
    region = region_mapped

    def matches(row: dict) -> bool:
        """
        Determine whether a funding row matches the desired target group and region.  We
        perform case-insensitive substring matching for regions to handle cases
        where the CSV contains combined regions (e.g. "Berlin / Brandenburg").
        The row is considered a match if either the row's region exactly matches
        the selected region, the selected region is contained within the row's
        region string, or the row is a federal programme (region == "bund").
        Target groups are matched by substring as before.
        """
        # Guard against non-dictionary rows (e.g. None or lists) that may slip
        # through the CSV parser.  Without this check the code below would
        # raise an AttributeError when calling row.get.
        if not isinstance(row, dict):
            return False
        zg_val = row.get("Zielgruppe", "")
        reg_val = row.get("Region", "")
        # Normalise to empty strings when None
        zg = (zg_val or "").lower() if isinstance(zg_val, str) else ""
        reg = (reg_val or "").lower() if isinstance(reg_val, str) else ""
        # Match target groups via substring if any target token appears
        t_ok = True if not targets else any(t in zg for t in targets)
        if not region:
            return t_ok
        regmatch = (reg == region) or (region in reg) or (reg == "bund")
        return t_ok and regmatch

    # Filter programmes by region and target group.  If a specific region is
    # provided, prioritise exact regional programmes first, then federal
    # ("bund") programmes, then all others.  This ensures regionally
    # relevant offers like "Coaching BONUS Berlin" appear before general
    # listings.
    # Filter programmes by region/target group.  If a specific region is provided,
    # prioritise exact regional programmes first, then federal programmes.  If
    # fewer than ``max_items`` programmes match, append additional entries from
    # the full list (excluding duplicates) so that the reader always sees a
    # representative set of opportunities.  This addresses cases where only a
    # single regional programme exists (e.g. Berlin), ensuring that the list
    # never appears empty or too short.
    # Collect programmes matching the desired region exactly to prioritise regional schemes.
    region_matches = []
    if region:
        for p in programmes:
            # Safely lower-case the region value to avoid NoneType errors
            reg_val = p.get("Region") if isinstance(p, dict) else None
            reg = ((reg_val or "").lower()) if isinstance(reg_val, str) else ""
            try:
                name = p.get("Name", "").strip()
            except Exception:
                name = ""
            if not name:
                continue
            if reg == region:
                region_matches.append(p)
    # Filter programmes by region and target group.
    filtered = [p for p in programmes if matches(p)]
    if region:
        # Sort matches: exact region first, then federal ('bund'), then others.
        filtered = sorted(
            filtered,
            key=lambda p: 0
            if (((p.get("Region") or "").lower()) == region)
            else (1 if (((p.get("Region") or "").lower()) == "bund") else 2),
        )
    # Build the selected list: include regional programmes first (if available).
    selected: List[dict] = []
    used_names = set()
    # Prioritise all programmes whose region exactly matches the user's region.
    if region_matches:
        for p in region_matches:
            name = p.get("Name", "").strip() if p.get("Name") else ""
            if name and name not in used_names:
                selected.append(p)
                used_names.add(name)
            # Do not prematurely break here; include all region matches up to max_items.
            if len(selected) >= max_items:
                break
    # Then add further programmes from the filtered list up to max_items.
    for p in filtered:
        if len(selected) >= max_items:
            break
        name = p.get("Name", "").strip() if p.get("Name") else ""
        if not name or name in used_names:
            continue
        selected.append(p)
        used_names.add(name)
    # If still not enough programmes, append from all programmes matching region or 'bund'
    if len(selected) < max_items:
        for p in programmes:
            if len(selected) >= max_items:
                break
            name = p.get("Name", "").strip() if p.get("Name") else ""
            if not name or name in used_names:
                continue
            if region:
                # Safely lower-case region for fill programmes
                reg_val = p.get("Region") if isinstance(p, dict) else None
                reg = ((reg_val or "").lower()) if isinstance(reg_val, str) else ""
                if not (reg == region or reg == "bund"):
                    continue
            selected.append(p)
            used_names.add(name)
    # Ensure at least one non-federal programme is displayed when possible.  If after selection
    # only federal (bund) programmes are present, append the first non-federal programme
    # from the full list that has not been selected yet.  This helps surface regional
    # programmes for awareness even when the user is not from that region.
    has_non_federal = any(((p.get("Region") or "").lower() != "bund") for p in selected)
    if not has_non_federal:
        for p in programmes:
            try:
                name = p.get("Name", "").strip()
            except Exception:
                name = ""
            reg_val = p.get("Region") if isinstance(p, dict) else None
            reg = ((reg_val or "").lower()) if isinstance(reg_val, str) else ""
            if not name or name in used_names:
                continue
            if reg and reg != "bund":
                selected.append(p)
                used_names.add(name)
                break
    if not selected:
        return ""
    # Determine current month/year for the 'Stand' note.  This helps the
    # reader understand when the funding list was generated.  We fall back
    # gracefully if obtaining the current date fails.
    try:
        now = datetime.now()
        if lang == "de":
            stand = now.strftime("%m/%Y")
        else:
            # Use full month name in English for clarity
            stand = now.strftime("%B %Y")
    except Exception:
        stand = ""
    title = "Dynamische Förderprogramme" if lang == "de" else "Dynamic funding programmes"
    # Prepare a hint when no region was specified.  We select an example
    # programme from the first non-federal entry to give readers an idea of
    # what a state-level funding scheme looks like.  This hint appears
    # before the list of programmes.
    note_html = ""
    if not region:
        example = None
        # Find the first programme with a specific region (not 'bund').
        for p in programmes:
            try:
                reg = (p.get("Region", "") or "").strip()
            except Exception:
                reg = ""
            if reg and reg.lower() != "bund":
                example = p
                break
        if example:
            ex_name = example.get("Name", "").strip()
            ex_reg = example.get("Region", "").strip()
            if lang == "de":
                note_html = f"<p><em>Kein Bundesland ausgewählt – Beispiel Landesprogramm: <b>{ex_name}</b> ({ex_reg}).</em></p>"
            else:
                note_html = f"<p><em>No state selected – example regional programme: <b>{ex_name}</b> ({ex_reg}).</em></p>"
    out = [f"<h3>{title}</h3>"]
    if note_html:
        out.append(note_html)
    out.append("<ul>")
    for p in selected:
        name = p.get("Name", "")
        desc = (p.get("Beschreibung", "") or "").strip()
        link = p.get("Link", "")
        grant = p.get("Fördersumme (€)", "")
        # Construct the description based on language and availability of a grant value
        if lang == "de":
            line = f"<b>{name}</b>: {desc}"
            if grant:
                line += f" – Förderhöhe: {grant}"
        else:
            line = f"<b>{name}</b>: {desc}"
            if grant:
                line += f" – Funding amount: {grant}"
        if link:
            line += f' – <a href="{link}" target="_blank">Link</a>'
        out.append(f"<li>{line}</li>")
    out.append("</ul>")
    # Append a note about when the funding list was compiled
    if stand:
        if lang == "de":
            out.append(f"<p style=\"font-size:10px;color:var(--muted);margin-top:.2rem\">Stand: {stand}</p>")
        else:
            out.append(f"<p style=\"font-size:10px;color:var(--muted);margin-top:.2rem\">Updated: {stand}</p>")
    return "\n".join(out)
# gpt_analyze.py — Gold-Standard (Teil 4/4)

def distill_quickwins_risks(source_html: str, lang: str = "de") -> Dict[str, str]:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    # For the Gold‑Standard version we limit the number of items in the quick wins and risks
    # lists to at most three.  The prompt explicitly instructs the model to extract no
    # more than three bullets per list.  This reduces information overload and keeps
    # the report focused on the most important actions and challenges.
    if lang == "de":
        sys = "Sie extrahieren präzise Listen aus HTML."
        # In German: 'maximal 3 Punkte je Liste'.  Only HTML output is allowed.
        usr = f"<h3>Quick Wins</h3><ul>…</ul><h3>Hauptrisiken</h3><ul>…</ul>\n- maximal 3 Punkte je Liste, nur HTML.\n\nHTML:\n{source_html}"
    else:
        sys = "You extract precise lists from HTML."
        # In English: 'up to 3 bullets each'.  Only HTML output is allowed.
        usr = f"<h3>Quick wins</h3><ul>…</ul><h3>Key risks</h3><ul>…</ul>\n- up to 3 bullets each, HTML only.\n\nHTML:\n{source_html}"
    try:
        out = _chat_complete([{"role":"system","content":sys},{"role":"user","content":usr}], model_name=model, temperature=0.2)
        html = ensure_html(out, lang)
    except Exception:
        return {"quick_wins_html":"","risks_html":""}

    m = re.split(r"(?i)<h3[^>]*>", html)
    if len(m) >= 3:
        a = "<h3>" + m[1]; b = "<h3>" + m[2]
        if "Quick" in a: return {"quick_wins_html": a, "risks_html": b}
        else:           return {"quick_wins_html": b, "risks_html": a}
    return {"quick_wins_html": html, "risks_html": ""}

def distill_recommendations(source_html: str, lang: str = "de") -> str:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if lang == "de":
        sys = "Sie destillieren Maßnahmen aus HTML."
        usr = (
            "Extrahieren Sie 5 TOP‑Empfehlungen als <ol>. Jede Zeile besteht aus 1 Satz und enthält "
            "Impact(H/M/L) und Aufwand(H/M/L) in Klammern."
        )
    else:
        sys = "You distill actions from HTML."
        usr = (
            "Extract the Top 5 recommendations as an ordered list (<ol>). Each line should be one sentence, "
            "with Impact (H/M/L) and Effort (H/M/L) in brackets."
        )
    try:
        out = _chat_complete([{"role":"system","content":sys},{"role":"user","content":source_html}], model_name=model, temperature=0.2)
        return ensure_html(out, lang)
    except Exception:
        return ""

def _jinja_env():
    """
    Construct a Jinja2 environment that loads templates from the absolute
    ``TEMPLATES_DIR``.  Using absolute paths prevents failures when the
    current working directory differs from the location of this file.
    """
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "htm"]),
        enable_async=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )

def _pick_template(lang: str) -> Optional[str]:
    """
    Determine which template file to use based on language.  Template files
    are looked up relative to the ``TEMPLATES_DIR`` defined at module load time.
    This avoids dependence on the current working directory.
    """
    if lang == "de" and (TEMPLATES_DIR / "pdf_template.html").exists():
        return "pdf_template.html"
    if (TEMPLATES_DIR / "pdf_template_en.html").exists():
        return "pdf_template_en.html"
    return None

def _data_uri_for(path: str) -> Optional[str]:
    if not path or path.startswith(("http://", "https://", "data:")):
        return path
    # Attempt absolute or cwd-relative path first
    if os.path.exists(path):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    # Then attempt to resolve relative to TEMPLATES_DIR
    candidate = TEMPLATES_DIR / path
    if candidate.exists():
        mime = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        with open(candidate, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return None

def _inline_local_images(html: str) -> str:
    def repl(m):
        src = m.group(1)
        if src.startswith(("http://","https://","data:")): return m.group(0)
        data = _data_uri_for(src)
        return m.group(0).replace(src, data) if data else m.group(0)
    return re.sub(r'src="([^"]+)"', repl, html)

def _toc_from_report(report: Dict[str, Any], lang: str) -> str:
    """
    Build a simple table of contents based on which sections of the report
    actually contain content.  The Gold‑Standard no longer includes a
    separate entry for a visualisation page; charts and bars are embedded
    directly within the relevant sections (e.g. Dimensionen).  Therefore we
    omit any TOC items for visualisation or visuals entirely.

    Parameters
    ----------
    report: dict
        The assembled report context with optional HTML strings for each
        section.
    lang: str
        Either "de" or "en", used to translate the labels.

    Returns
    -------
    str
        An unordered list (``<ul>...</ul>``) with list items for each
        section that has content.  If no sections are present, an empty
        string is returned.
    """
    toc_items: List[str] = []

    def add(key: str, label: str) -> None:
        if report.get(key):
            toc_items.append(f"<li>{label}</li>")

    if lang == "de":
        add("exec_summary_html", "Executive Summary")
        # Do not append a separate 'Visualisierung' entry; visuals live in
        # the Dimensionen section in the Gold‑Standard.
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
        # No visuals entry in English either
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

def generate_full_report(data: dict, lang: str = "de") -> dict:
    branche = _extract_branche(data)
    lang = _norm_lang(lang)
    # Gold‑Standard: do not calculate an aggregate score.  Instead, we rely on the
    # four core readiness dimensions (digitalisation, automation, paperless and AI
    # know‑how) which are presented as individual KPI tiles.  Explicitly set
    # score_percent to None to avoid including the score in the preface.
    data["score_percent"] = None
    solo = is_self_employed(data)
    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja","unklar","yes","unsure"}

    # Gold‑Standard: separate quick wins, risks and recommendations into their own GPT calls
    # Compose the list of chapters that will be generated by the LLM.  In the
    # Gold‑Standard version we separate key sections into their own calls to
    # avoid overlap (e.g. quick wins vs. roadmap).  We also explicitly
    # include a "gamechanger" chapter immediately after the vision.  The
    # corresponding HTML is stored in out["gamechanger_html"] and passed to
    # the template.  Without this entry the Innovation & Gamechanger card
    # will not show LLM content.
    chapters = [
        "executive_summary",
        "vision",
        # generate gamechanger recommendations directly after the vision
        "gamechanger",
        # generate quick wins independently so they don't overlap with roadmap
        "quick_wins",
        # generate key risks independently
        "risks",
        "tools",
    ] + (["foerderprogramme"] if wants_funding else []) + [
        "roadmap",
        "compliance",
        "praxisbeispiel",
        # generate top recommendations separately
        "recommendations",
    ]
    out: Dict[str, Any] = {}
    for chap in chapters:
        try:
            sect_html = gpt_generate_section_html(data, branche, chap, lang=lang)
            out[chap] = ensure_html(strip_code_fences(fix_encoding(sect_html)), lang)
        except Exception as e:
            out[chap] = f"<p>[Fehler in Kapitel {chap}: {e}]</p>"
    # After generating all chapter HTML, apply the optional post-processing.  This
    # helper will clamp lengthy lists (e.g. quick wins, risks, recommendations),
    # enrich roadmap entries with owner/dependencies fields and add trade‑off
    # descriptions to gamechanger items.  If the helper is not available,
    # simply skip this step without raising an exception.
    if postprocess_report_dict:
        try:
            locale_code = "de" if (lang or "").lower().startswith("de") else "en"
            out = postprocess_report_dict(out, locale=locale_code)
        except Exception:
            pass

    # Präambel
    out["preface"] = generate_preface(lang=lang, score_percent=data.get("score_percent"))

    # Use the explicitly generated chapters for quick wins, risks and recommendations
    # Instead of distilling them from other sections.  If the chapter result is
    # empty, fall back to distillation for backwards compatibility.
    qw_html = ensure_html(strip_code_fences(fix_encoding(out.get("quick_wins") or "")), lang)
    rk_html = ensure_html(strip_code_fences(fix_encoding(out.get("risks") or "")), lang)
    rec_html = ensure_html(strip_code_fences(fix_encoding(out.get("recommendations") or "")), lang)
    # Fallback to distillation if no content was generated
    if not qw_html and not rk_html:
        src_for_qr = (out.get("executive_summary") or "") + "\n\n" + (out.get("roadmap") or "")
        q_r = distill_quickwins_risks(src_for_qr, lang=lang)
        qw_html, rk_html = q_r.get("quick_wins_html", ""), q_r.get("risks_html", "")

    # ------------------------------------------------------------------
    # Ensure that the quick wins section is never empty.  In some rare
    # cases the LLM returns no quick wins (or simply states that no quick
    # wins can be derived), which leaves the reader without actionable
    # next steps.  When this happens we fall back to a set of generic
    # quick wins tailored to organisations of all sizes.  The fallback
    # emphasises a data inventory, simple automation and a lean AI policy.
    # Each fallback is localised according to the report language.
    def _default_quick_wins(lang: str) -> str:
        if lang == "de":
            return (
                "<h3>Quick&nbsp;Wins</h3>"
                "<ul>"
                "<li><b>Dateninventur</b>: Erfassen Sie alle relevanten Kunden‑, Projekt‑ und Marketingdaten an einem Ort und bereinigen Sie sie, um eine solide Datengrundlage aufzubauen.</li>"
                "<li><b>Mini‑Automatisierung</b>: Automatisieren Sie wiederkehrende Aufgaben mit einem einfachen No‑Code‑Workflow, um sich Zeit für die Beratung zu verschaffen.</li>"
                "<li><b>KI‑Policy Light</b>: Formulieren Sie eine einseitige Richtlinie, die den internen Umgang mit generativer KI und Datenschutz regelt.</li>"
                "</ul>"
            )
        else:
            return (
                "<h3>Quick&nbsp;wins</h3>"
                "<ul>"
                "<li><b>Data inventory</b>: Consolidate all relevant customer, project and marketing data in one place and clean it to build a solid foundation.</li>"
                "<li><b>Mini automation</b>: Use a simple no‑code workflow to automate repetitive tasks and free up time for consulting.</li>"
                "<li><b>Lightweight AI policy</b>: Draft a one‑page guideline that defines how to use generative AI responsibly and protect data.</li>"
                "</ul>"
            )

    # If quick wins section is blank or contains a placeholder indicating
    # that no quick wins could be derived, insert the default quick wins.
    if not qw_html or re.search(r"keine\s*quick", qw_html, re.I):
        qw_html = _default_quick_wins(lang)
    if not rec_html:
        src_for_rec = (out.get("roadmap") or "") + "\n\n" + (out.get("compliance") or "")
        rec_html = distill_recommendations(src_for_rec, lang=lang)
        # Remove duplicate list items if any
        if rec_html:
            try:
                items = re.findall(r"<li[^>]*>(.*?)</li>", rec_html, re.S)
                seen = set()
                unique_items = []
                for it in items:
                    txt = re.sub(r"<[^>]+>", "", it).strip()
                    if txt and txt not in seen:
                        seen.add(txt)
                        unique_items.append(it)
                if unique_items:
                    rec_html = "<ol>" + "".join([f"<li>{it}</li>" for it in unique_items]) + "</ol>"
            except Exception:
                pass
    out["quick_wins_html"] = qw_html
    # If the risks list is too short, append default items to ensure at least 3 risks are shown.
    # Parse the current risks_html for list items
    risks_list_html = rk_html or ""
    try:
        items = re.findall(r"<li[^>]*>(.*?)</li>", risks_list_html, re.S)
    except Exception:
        items = []
    # Provide fallback risk items by language.  The Gold‑Standard version limits
    # the number of risks to a maximum of three, focusing on the most
    # pressing hurdles for small and mid‑sized companies.  Items are ordered by
    # typical severity and relevance for AI projects.  Each entry contains a
    # short title and a succinct description separated by a colon.
    if lang == "de":
        fallback_risks = [
            "Rechtslage & Datenschutz: Unklare Compliance- und Haftungsfragen sowie Datenschutzpflichten können juristische Risiken bergen",
            "Datenqualität & Nachvollziehbarkeit: Unstrukturierte oder unvollständige Daten erschweren aussagekräftige Analysen und gefährden die Transparenz",
            "Ressourcen- & Budgetdruck: Begrenztes Budget oder fehlende Kapazitäten verlangsamen Projekte und reduzieren die Erfolgswahrscheinlichkeit"
        ]
    else:
        fallback_risks = [
            "Regulatory & data protection: Unclear compliance obligations and privacy duties pose legal risks",
            "Data quality & traceability: Unstructured or incomplete data hampers meaningful analysis and undermines transparency",
            "Resource & budget constraints: Limited funds or capacity slow down projects and reduce the likelihood of success"
        ]

    # ------------------------------------------------------------------
    # Fallback compliance
    #
    # Define a helper that returns a generic compliance section if the
    # language model fails to produce any content for the compliance
    # chapter.  The narrative covers key EU regulations (GDPR/DSGVO,
    # ePrivacy, DSA and the forthcoming EU AI Act) in qualitative terms
    # and avoids numbers or percentage values.  This ensures that the
    # report always contains guidance on legal and data protection issues.
    def _fallback_compliance(lang: str) -> str:
        """
        Return a generic compliance section advising on key European regulations
        such as DSGVO/GDPR, ePrivacy, DSA and the EU AI Act.  The text avoids
        numbers and provides narrative paragraphs suitable for SMEs and consultants.
        """
        if lang == "de":
            return (
                "<p>Bei der Einführung von KI-Systemen sollten Sie die wesentlichen rechtlichen Rahmenbedingungen im Blick behalten. "
                "Dazu gehören die Datenschutz-Grundverordnung (DSGVO) und die ePrivacy-Richtlinie, die klare Anforderungen an den Schutz "
                "personenbezogener Daten und die Zustimmung der Nutzer stellen.</p>"
                "<p>Außerdem tritt der Digital Services Act (DSA) mit Regeln für Transparenz und Plattformverantwortung sowie der kommende "
                "EU AI Act in Kraft, der einen risikobasierten Ansatz für den Einsatz von KI vorsieht. Informieren Sie sich über diese "
                "Regelwerke und passen Sie Prozesse und Dokumentation entsprechend an, um Ihre Datenverarbeitung rechtssicher zu gestalten "
                "und Vertrauen bei Kunden und Partnern zu schaffen.</p>"
            )
        else:
            return (
                "<p>When adopting AI systems, you should pay attention to the key European legal frameworks. "
                "These include the General Data Protection Regulation (GDPR) and the ePrivacy directive, which set clear requirements "
                "for protecting personal data and obtaining user consent.</p>"
                "<p>The Digital Services Act (DSA) introduces rules for transparency and platform accountability, and the forthcoming "
                "EU AI Act will establish a risk-based approach to the use of AI. Familiarise yourself with these regulations and adapt "
                "your processes and documentation accordingly to ensure lawful data processing and to build trust with customers and partners.</p>"
            )
    # Determine target number of risks: limit to 3 for a concise overview.
    target_count = 3
    if len(items) < target_count:
        needed = target_count - len(items)
        for fr in fallback_risks:
            if needed <= 0:
                break
            # avoid adding if similar category already present
            if not any(fr.split(":")[0] in re.sub(r"<[^>]+>", "", it) for it in items):
                risks_list_html += f"<li>{fr}</li>"
                items.append(fr)
                needed -= 1
        # ensure at least a <ul> wrapper
        if risks_list_html.strip() and not risks_list_html.strip().startswith("<ul"):
            risks_list_html = "<ul>" + risks_list_html + "</ul>"
    # Use the augmented risks list
    out["risks_html"] = risks_list_html
    out["recommendations_html"] = rec_html
    out["roadmap_html"] = out.get("roadmap", "")
    # Initialise the executive summary HTML.  We will clean stray KPI lines below.
    out["exec_summary_html"] = out.get("executive_summary", "")

    # ------------------------------------------------------------------------
    # Ensure that the compliance chapter is not empty.  If the language model
    # returned no compliance content (or only whitespace/HTML tags), provide
    # a fallback compliance section.  The fallback text offers generic
    # guidance on GDPR/DSGVO, ePrivacy, DSA and the EU AI Act.  This
    # assignment must happen after the main chapters are generated but
    # before sections_html is constructed.
    comp_txt = re.sub(r"<[^>]+>", "", out.get("compliance", "") or "").strip()
    if not comp_txt:
        out["compliance"] = _fallback_compliance(lang)

    # ------------------------------------------------------------------------
    # Add the gamechanger HTML.  The LLM returns raw HTML for the
    # "gamechanger" chapter which may be wrapped in code fences.  Convert it
    # into safe HTML using the same helper functions as other sections.  If
    # the gamechanger chapter is empty or missing, an empty string is stored.
    try:
        gc_raw = out.get("gamechanger") or ""
        gc_html = ensure_html(strip_code_fences(fix_encoding(gc_raw)), lang)
        # Remove any Jinja-style placeholders that the language model may have
        # accidentally emitted into the Gamechanger chapter.  Expressions
        # enclosed in ``{{ ... }}`` are not meant to appear in the final
        # report and will confuse the reader.  Strip them out to ensure
        # clean HTML.  If the LLM respects the prompt, this has no effect.
        gc_html = re.sub(r"\{\{[^\{\}]*\}\}", "", gc_html)
        # Rename the Moonshot section to avoid marketing jargon and add a note
        # explaining that the maturity benchmark in this chapter is use-case
        # specific and not the same as the overall KPI tiles.  This
        # replacement works both for DE and EN.  Only perform the change if
        # the heading exists in the generated HTML.
        if "<h3>Moonshot</h3>" in gc_html:
            if lang == "de":
                gc_html = gc_html.replace(
                    "<h3>Moonshot</h3>",
                    "<h3>Langfristige Initiative</h3><p><em>Hinweis: Kapitel-Benchmark (Use-Case-bezogen), nicht die Gesamt-KPI-Kacheln.</em></p>"
                )
            else:
                gc_html = gc_html.replace(
                    "<h3>Moonshot</h3>",
                    "<h3>Long-term Initiative</h3><p><em>Note: chapter benchmarks are use-case specific and differ from the overall KPI tiles.</em></p>"
                )
    except Exception:
        gc_html = ""
    out["gamechanger_html"] = gc_html

    # Narrative-first rendering: provide HTML for funding, tools and compliance
    # before any table fallbacks. The template will prefer these narrative blocks
    # when present.
    try:
        fp_raw = out.get("foerderprogramme") or ""
        if fp_raw:
            out["foerderprogramme_html"] = ensure_html(strip_code_fences(fix_encoding(fp_raw)), lang)
    except Exception:
        out["foerderprogramme_html"] = out.get("foerderprogramme_html", "")
    try:
        tools_raw = out.get("tools") or ""
        if tools_raw:
            out["tools_html"] = ensure_html(strip_code_fences(fix_encoding(tools_raw)), lang)
    except Exception:
        out["tools_html"] = out.get("tools_html", "")

    # Ensure compliance HTML is always provided (with fallback text if missing)
    try:
        comp_txt_plain = re.sub(r"<[^>]+>", "", out.get("compliance", "") or "").strip()
    except Exception:
        comp_txt_plain = ""
    if not comp_txt_plain:
        out["compliance"] = _fallback_compliance(lang)
    out["compliance_html"] = ensure_html(strip_code_fences(fix_encoding(out.get("compliance") or "")), lang)

    # -------------------------------------------------------------------------
        # Remove stray KPI category lines from the executive summary
        #
        # In some drafts the LLM may insert lines containing only the KPI
        # category names (e.g. "Digitalisierung", "Papierlos" or the full
        # sequence "Digitalisierung Automatisierung Papierlos Know‑how").  These
        # terms are metrics and should not appear in the narrative text.  We
        # remove any line whose plain text consists solely of KPI keywords in
        # either German or English (with optional hyphens or spaces).  Lines
        # containing additional narrative are preserved.  In addition, remove
        # standalone occurrences of these keywords between list items.  This logic
        # is robust to various hyphen types and whitespace variations.
    try:
        esc_html = out.get("exec_summary_html") or ""
        if esc_html:
            # First remove any sequences of KPI terms separated by spaces, hyphens or slashes.
            # This catches lines like "Digitalisierung Automatisierung Papierlos Know‑how" as well as
            # "Digitalisation / Automation / Paperless / AI know‑how" in either language.  We allow
            # between one and three separators to match up to four terms in a row.
            pattern_multi = (
                r"(?i)\b(?:digitalisierung|digitalisation|automatisierung|automation|papierlos(?:igkeit)?|paperless|know[\-\s]?how|ai\s*know\s*how|ki\s*know\s*how)"
                r"(?:\s*[\/-–]\s*(?:digitalisierung|digitalisation|automatisierung|automation|papierlos(?:igkeit)?|paperless|know[\-\s]?how|ai\s*know\s*how|ki\s*know\s*how)){1,3}\b"
            )
            esc_html = re.sub(pattern_multi, "", esc_html)
            # Remove <p> or <li> elements that contain only KPI terms or sequences.  Use a broad
            # pattern to capture variants with spaces, hyphens or slashes.  This removes cases
            # like <p>Digitalisierung / Automatisierung</p> or <li>Papierlos Know-how</li>.
            pattern_wrapped = (
                r"(?is)<(p|li)[^>]*>\s*(?:"  # start tag
                r"(?:digitalisierung|digitalisation|automatisierung|automation|papierlos(?:igkeit)?|paperless|know[\-\s]?how|ai\s*know\s*how|ki\s*know\s*how)"
                r"(?:\s*[\/-–]\s*(?:digitalisierung|digitalisation|automatisierung|automation|papierlos(?:igkeit)?|paperless|know[\-\s]?how|ai\s*know\s*how|ki\s*know\s*how))*)"  # allow multiple terms
                r"\s*</\1>"
            )
            esc_html = re.sub(pattern_wrapped, "", esc_html)
            # Define a comprehensive list of single KPI terms (case-insensitive).  Include variations
            # with and without hyphens and different spellings.  These will be stripped when they
            # appear as standalone paragraphs or list items.
            kpi_single = [
                "digitalisierung", "digitalisation",
                "automatisierung", "automation",
                "papierlos", "paperless",
                "papierlosigkeit",
                "know-how", "know how", "know‑how", "knowhow",
                "ai know-how", "ai know how", "ai know‑how", "ki know-how", "ki know how",
            ]
            # Remove isolated occurrences wrapped in <p> or <li> tags (case-insensitive).
            for term in kpi_single:
                esc_html = re.sub(rf"<p>\s*{term}\s*</p>", "", esc_html, flags=re.I)
                esc_html = re.sub(rf"<li>\s*{term}\s*</li>", "", esc_html, flags=re.I)
            # Split by lines and filter out lines that consist solely of KPI terms (ignoring HTML tags).
            lines = esc_html.splitlines()
            cleaned: List[str] = []
            # For exact match removal, prepare a set of KPI strings without HTML.
            kpi_exact = set([
                "digitalisierung", "digitalisation",
                "automatisierung", "automation",
                "papierlos", "paperless",
                "papierlosigkeit",
                "know-how", "know how", "knowhow",
                "ki know-how", "ki know how", "ai know-how", "ai know how", "ai know‑how",
                "ki knowhow", "ai knowhow"
            ])
            # Define a token set of KPI terms across languages.  Any line that
            # splits into tokens all contained within this set will be removed.
            kpi_tokens = {
                "digitalisierung", "digitalisation",
                "automatisierung", "automation",
                "papierlos", "paperless", "papierlosigkeit",
                "know", "how", "knowhow",
                "ki", "ai"
            }
            for ln in lines:
                # Remove HTML tags and strip whitespace.
                plain = re.sub(r"<[^>]+>", "", ln).strip()
                if not plain:
                    continue
                # Normalise hyphens, slashes and NBSPs to spaces and lowercase the text.
                norm_plain = re.sub(r"[\xa0\-–\u2011/]+", " ", plain).lower().strip()
                # Remove punctuation (except letters and spaces).
                norm_plain = re.sub(r"[^a-zäöüß\s]", "", norm_plain)
                # Collapse multiple spaces
                norm_plain = re.sub(r"\s+", " ", norm_plain).strip()
                if not norm_plain:
                    continue
                # If the entire line matches exactly a KPI term, drop it.
                if norm_plain in kpi_exact:
                    continue
                # Split into tokens and drop if the entire set of tokens consists only of KPI words.
                tokens = [t for t in norm_plain.split() if t]
                # Drop lines consisting solely of KPI tokens or where at least three KPI tokens appear.
                if tokens:
                    # If all tokens are KPI tokens, skip this line.
                    if all(tok in kpi_tokens for tok in tokens):
                        continue
                    # If at least three tokens are KPI tokens (e.g. "digitalisierung automatisierung papierlos know how"), drop.
                    kpi_count = sum(1 for tok in tokens if tok in kpi_tokens)
                    if kpi_count >= 3 and kpi_count == len(tokens):
                        continue
                cleaned.append(ln)
            out["exec_summary_html"] = "\n".join(cleaned)
    except Exception:
        # If cleaning fails, leave the original executive summary unchanged
        pass

    # Perform an additional pass to remove any residual KPI-only lines that may remain.
    # This pass scans each line of the executive summary after the initial
    # cleaning and drops lines composed solely of KPI terms (e.g.
    # "Digitalisierung / Automatisierung / Papierlos / Know-how").  It is
    # agnostic to case, hyphens, slashes and non-breaking spaces.  Without
    # this extra step, isolated KPI lines may occasionally persist at the end
    # of the summary due to subtle encoding variations.
    try:
        esc_html2 = out.get("exec_summary_html") or ""
        if esc_html2:
            def _is_kpi_only(line: str) -> bool:
                # Remove HTML tags, trim whitespace and normalise separators
                import re as _re
                plain = _re.sub(r"<[^>]+>", "", line or "").strip()
                if not plain:
                    return False
                # Replace NBSP (\xa0) and various dash/slash characters with spaces
                norm = _re.sub(r"[\u00A0\u2011\u2012\u2013\u2014\u2015/\\-]+", " ", plain).lower()
                # Remove punctuation except letters and spaces
                norm = _re.sub(r"[^a-zäöüß\s]", "", norm)
                tokens = [t for t in norm.split() if t]
                if not tokens:
                    return False
                kpi_terms = {
                    "digitalisierung", "digitalisation",
                    "automatisierung", "automation",
                    "papierlos", "paperless", "papierlosigkeit",
                    "know", "how", "knowhow", "knowhow", "knowhow",  # duplicates for robustness
                    "ki", "ai"
                }
                # If all tokens are KPI terms (or combinations like "know how"), mark for removal
                return all(tok in kpi_terms for tok in tokens)
            lines = esc_html2.splitlines()
            cleaned_lines = []
            for ln in lines:
                if _is_kpi_only(ln):
                    continue
                cleaned_lines.append(ln)
            out["exec_summary_html"] = "\n".join(cleaned_lines)
    except Exception:
        pass

    # Vision separat (NICHT in sections_html mischen).  Wenn der LLM keine Vision liefert
    # oder ein Fehlertext vorhanden ist, generiere eine Fallback‑Vision.
    try:
        vision_raw = out.get("vision") or ""
        # If vision is empty or contains error indicators (in multiple languages), fallback.
        err_keywords = [
            "fehler", "invalid", "ungültig", "ungültige", "fehlende eingabedaten",
            "missing input", "error", "fehlende eingabe"
        ]
        lower_vision = vision_raw.lower() if isinstance(vision_raw, str) else ""
        if not vision_raw or any(kw in lower_vision for kw in err_keywords):
            out["vision"] = fallback_vision(data, lang)
    except Exception:
        out["vision"] = fallback_vision(data, lang)
    out["vision_html"] = f"<div class='vision-card'>{out['vision']}</div>" if out.get("vision") else ""

# Vision-Normalisierung: Ersetze veraltete Überschrift 'Kühne Idee' durch 'Vision'
try:
    if isinstance(out.get("vision"), str):
        vis = out["vision"]
        vis = vis.replace("Kühne Idee:", "Vision:").replace("Kühne Idee", "Vision")
        vis = vis.replace("Bold idea:", "Vision:").replace("Bold idea", "Vision")
        out["vision"] = vis
        out["vision_html"] = f"<div class='vision-card'>{out['vision']}</div>"
except Exception:
    pass

    # sections_html (ohne Vision)
    # Praxisbeispiel (Compliance wird separat als eigener Abschnitt gerendert)
    parts = []
    if out.get("praxisbeispiel"):
        parts.append(f"<h2>{'Praxisbeispiel' if lang=='de' else 'Case study'}</h2>\n" + out["praxisbeispiel"])
    out["sections_html"] = "\n\n".join(parts)


    # dynamische Förderliste separat bereitstellen (falls Tabelle leer)
    out["dynamic_funding_html"] = ""
    if wants_funding:
        dyn = build_dynamic_funding(data, lang=lang)
        if dyn: out["dynamic_funding_html"] = dyn

    # Diagrammdaten
    out["score_percent"] = data["score_percent"]
    out["chart_data"] = build_chart_payload(data, out["score_percent"], lang=lang)
    out["chart_data_json"] = json.dumps(out["chart_data"], ensure_ascii=False)


    # Tabellen (CSV)

    try:

        out["foerderprogramme_table"] = build_funding_table(data, lang=lang)

    except Exception:

        out["foerderprogramme_table"] = []

    try:

        out["tools_table"] = build_tools_table(data, branche=branche, lang=lang)

    except Exception:

        out["tools_table"] = []


    # --- Narrative + Details + Live-Layer (robust) ---

    try:

        # Narrative-first HTML (erzählerisch)

        out["foerderprogramme_html"] = build_funding_narrative(data, lang=lang, max_items=5)

        out["tools_html"]            = build_tools_narrative(data, branche=branche, lang=lang, max_items=6)

    

        # Detail-Tabellen (CSV-gestützt; optional)

        out["funding_details"], out["funding_stand"] = build_funding_details_struct(data, lang=lang, max_items=8)

        out["tools_details"],   out["tools_stand"]   = build_tools_details_struct(data, branche=branche, lang=lang, max_items=12)

    

        # Live-Updates (optional)

        _title, _html = build_live_updates_html(data, lang=lang, max_results=5)

        out["live_updates_title"] = _title

        out["live_updates_html"]  = _html

        out["live_box_html"]      = _html

    except Exception:

        # Defensive Defaults – verhindern Import-/Render-Abbruch

        out["foerderprogramme_html"] = out.get("foerderprogramme_html","")

        out["tools_html"]            = out.get("tools_html","")

        out["funding_details"]       = out.get("funding_details", [])

        out["tools_details"]         = out.get("tools_details", [])

        out["funding_stand"]         = out.get("funding_stand") or out.get("datum") or out.get("date")

        out["tools_stand"]           = out.get("tools_stand") or out.get("datum") or out.get("date")

        out["live_updates_title"]    = out.get("live_updates_title","")

        out["live_updates_html"]     = out.get("live_updates_html","")

        out["live_box_html"]         = out.get("live_box_html","")

    

    # Fallbacks (aus HTML) nur wenn CSV leer blieb

    if not out.get("foerderprogramme_table"):

        teaser = out.get("foerderprogramme_html") or out.get("sections_html","")

        rows = []

        for m in re.finditer(r'(?:<b>)?([^<]+?)(?:</b>)?\s*(?:Fö(r|e)derh(ö|o)he|Fördersumme|amount)[:\s]*([^<]+).*?<a[^>]*href="([^"]+)"', teaser, re.I|re.S):

            name, _, _, amount, link = m.groups()

            rows.append({"name":(name or "").strip(),"zielgruppe":"","foerderhoehe":(amount or "").strip(),"link":link})

        out["foerderprogramme_table"] = rows[:6]

    

    if not out.get("tools_table"):

        html_tools = out.get("tools_html") or out.get("sections_html","")

        rows = []

        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html_tools, re.I):

            link, name = m.group(1), m.group(2)

            if name and link:

                rows.append({"name":name.strip(),"usecase":"","cost":"","link":link})

        out["tools_table"] = rows[:8]


    def _to_num(v):
        """Try to parse a percentage or numeric string into an int between 0 and 100."""
        if v is None:
            return 0
        try:
            # accept values like "35", "35%", "0.35", "7" (slider 1–10)
            s = str(v).strip().replace(",", ".")
            m = re.search(r"(\d+[\.,]?\d*)", s)
            if m:
                num = float(m.group(1))
                # If the number is a fraction (<=1), scale to percentage
                if num <= 1.0:
                    num = num * 100.0
                # If the number is between 1 and 10 and an integer (slider), scale to 0–100
                elif num <= 10 and num == int(num):
                    num = num * 10.0
                return max(0, min(100, int(round(num))))
        except Exception:
            pass
        return 0

    def _map_scale_text(value: str, mapping: Dict[str, int]) -> int:
        """
        Map textual responses to a numeric score.  The questionnaire uses verbal
        scales (e.g. "Eher hoch", "Mittel").  Provide a dictionary mapping of
        normalised lowercase responses to a value between 0 and 100.  If the
        exact key is not found, perform a fuzzy match where a mapping key
        appears as a substring of the user input.  This allows responses such
        as "eher hoch" or "hoch (schätzung)" to map correctly.  Unknown
        responses default to ``0``.
        """
        if not value:
            return 0
        key = str(value).strip().lower()
        # First try exact match
        if key in mapping:
            return mapping[key]
        # Fuzzy substring matching: check longer keys first to avoid
        # matching "hoch" inside "eher hoch" incorrectly.
        for k in sorted(mapping.keys(), key=len, reverse=True):
            if k and k in key:
                return mapping[k]
        return 0

    # ----------------------------------------------------------------------
    # KPI tiles: show the four core readiness dimensions instead of a single
    # aggregate score.  Each dimension is displayed with its own value.  The
    # keys for these values are mapped from the questionnaire responses.
    # ----------------------------------------------------------------------
    # Helper to normalise numeric strings to an integer percentage
    def _dim_value(key: str) -> int:
        return _to_num(data.get(key) or 0)
    own_digi = _dim_value("digitalisierungsgrad") or _dim_value("digitalisierungsgrad (%)") or _dim_value("digitalisierungs_score")
    # Automatisierungsgrad kann verbal angegeben sein (z. B. "Eher hoch").  Verwende eine Mapping-Tabelle.
    auto_mapping = {
        "gar nicht": 0,
        "nicht": 0,
        "eher niedrig": 25,
        "niedrig": 25,
        "mittel": 50,
        "eher hoch": 75,
        "hoch": 75,
        "sehr hoch": 90,
    }
    know_mapping = {
        "sehr niedrig": 10,
        "niedrig": 25,
        "mittel": 50,
        "hoch": 75,
        "sehr hoch": 90,
    }
    # Read raw responses
    raw_auto = data.get("automatisierungsgrad") or data.get("automatisierungsgrad (%)") or data.get("automatisierungs_score")
    raw_know = data.get("ki_knowhow") or data.get("knowhow") or data.get("ai_knowhow")
    own_auto = _dim_value("automatisierungsgrad") or _dim_value("automatisierungsgrad (%)") or _dim_value("automatisierungs_score") or _map_scale_text(raw_auto, auto_mapping)
    own_paper = _dim_value("prozesse_papierlos") or _dim_value("papierlos") or _dim_value("paperless")
    own_know = _dim_value("ki_knowhow") or _dim_value("knowhow") or _dim_value("ai_knowhow") or _map_scale_text(raw_know, know_mapping)

    kpis = []
    kpis.append({
        "label": "Digitalisierung" if lang == "de" else "Digitalisation",
        "value": f"{own_digi}%"
    })
    kpis.append({
        "label": "Automatisierung" if lang == "de" else "Automation",
        "value": f"{own_auto}%"
    })
    kpis.append({
        "label": "Papierlos" if lang == "de" else "Paperless",
        "value": f"{own_paper}%"
    })
    kpis.append({
        "label": "KI-Know-how" if lang == "de" else "AI know‑how",
        "value": f"{own_know}%"
    })
    out["kpis"] = kpis

    # Benchmarks für horizontale Balken (Ihr Wert vs. Branche)
    # Verwendet die zuvor berechneten eigenen Werte (own_digi, own_auto, own_paper, own_know)
    # anstatt sie erneut mit _to_num neu zu bestimmen. Dadurch bleiben Mapping
    # Ergebnisse (z. B. „eher hoch" → 75) konsistent in KPI-Kacheln und Benchmarks.
    # Branchen-Benchmarks aus dem Kontext (falls vorhanden)
    dig_bench = 0
    aut_bench = 0
    try:
        if ctx_bench:
            bstr = str(ctx_bench.get("benchmark", ""))
            m_d = re.search(r"Digitalisierungsgrad\s*[:=]\s*(\d+)", bstr)
            m_a = re.search(r"Automatisierungsgrad\s*[:=]\s*(\d+)", bstr)
            if m_d:
                dig_bench = int(m_d.group(1))
            if m_a:
                aut_bench = int(m_a.group(1))
    except Exception:
        # Wenn Benchmarks nicht geparst werden können, verbleiben sie bei 0
        pass
    # Fallback: wenn keine Automatisierungs-Benchmark erkannt, setze einen neutralen Standardwert (35%).
    if aut_bench == 0:
        aut_bench = 35
    # Setze für den Digitalisierungs-Benchmark einen neutralen Wert (50 %), falls er nicht vorhanden ist.
    if dig_bench == 0:
        dig_bench = 50
    # Papierlos und Know-how haben keine Branchenwerte in YAML; setze 50 als neutralen Richtwert
    paper_bench = 50
    know_bench = 50
    # Erstelle Benchmark‑Dictionary, das die eigenen Werte aus den vorab
    # berechneten KPI-Variablen übernimmt. So stimmen Balken und KPI-Kacheln überein.
    benchmarks = {
        ("Digitalisierung" if lang == "de" else "Digitalisation"): {"self": own_digi, "industry": dig_bench},
        ("Automatisierung" if lang == "de" else "Automation"): {"self": own_auto, "industry": aut_bench},
        ("Papierlos" if lang == "de" else "Paperless"): {"self": own_paper, "industry": paper_bench},
        ("Know-how" if lang == "de" else "Know‑how"): {"self": own_know, "industry": know_bench},
    }
    out["benchmarks"] = benchmarks

    # ------------------------------------------------------------------
    # KPI‑Klassifizierung & Badges
    #
    # Auf Basis der eigenen Werte und Branchen-Benchmarks wird für jede
    # Dimension (Digitalisierung, Automatisierung, Papierlos, KI-Know-how)
    # der relative Vorsprung oder Rückstand berechnet.  Die Toleranz
    # (Schwellenwert für "gleichauf") wird branchenabhängig festgelegt:
    # In produktionsnahen Bereichen ist die Automatisierung strenger
    # (8 pp), in beratungsnahen Branchen großzügiger (12 pp).  Der
    # Basistoleranzwert kann über die Umgebungsvariable KPI_TOLERANCE
    # angepasst werden (Standard: 10 pp).  Zusätzlich erzeugen wir für
    # jede Dimension ein Badge mit einem Icon (↑ für Vorsprung, ↔ für
    # gleichauf, ↓ für Rückstand), dem Delta und dem Statuswort.
    # Die generierten HTML‑Snippets werden im Report verwendet, sowohl
    # im Executive‑Summary‑Kasten als auch im Inhaltsverzeichnis.

    def _tol_base() -> int:
        """Lies den Basistoleranzwert aus der Umgebungsvariable oder verwende 10."""
        try:
            return int(os.getenv("KPI_TOLERANCE", "10"))
        except Exception:
            return 10

    def _tol_for(label: str, branche: str) -> int:
        """
        Bestimme die Toleranz für eine Dimension anhand der Branche.
        In der Produktion/Industrie wird die Automatisierung strenger
        bewertet, während in Beratungs-/Dienstleistungsbranchen eine
        großzügigere Toleranz gilt.  Für alle anderen Kombinationen
        wird der Basistoleranzwert verwendet.
        """
        base = _tol_base()
        br = (branche or "").lower()
        lab = (label or "").lower()
        # Strenger (kleineres Toleranzband) in Produktion/Industrie für Automatisierung
        if any(k in br for k in ["industrie", "produktion", "fertigung", "manufactur", "manufacturing"]):
            if "autom" in lab:
                return min(base, 8)
        # Großzügiger (größeres Toleranzband) in Beratung/Dienstleistung für Automatisierung
        if any(k in br for k in ["beratung", "consult", "dienstleistung", "service"]):
            if "autom" in lab:
                return max(base, 12)
        return base

    def _classify(self_v: int, bench_v: int, lang: str, tol: int):
        """
        Vergleiche eigenen Wert (self_v) mit dem Benchmark (bench_v) und
        liefere das Delta sowie das Statuswort abhängig von der Toleranz.
        Ist das Delta >= Toleranz → Vorsprung/lead,
        Delta <= - Toleranz → Rückstand/behind, sonst gleichauf/on par.
        """
        try:
            delta = int(self_v) - int(bench_v)
        except Exception:
            delta = 0
        if delta >= tol:
            return delta, ("Vorsprung" if lang == "de" else "lead")
        if delta <= -tol:
            return delta, ("Rückstand" if lang == "de" else "behind")
        return delta, ("gleichauf" if lang == "de" else "on par")

    # Label-Liste für DE und EN
    labels_de = ["Digitalisierung", "Automatisierung", "Papierlos", "KI-Know-how"]
    labels_en = ["Digitalisation", "Automation", "Paperless", "AI know-how"]
    _labels = labels_de if lang == "de" else labels_en

    # Paarliste aus Label, eigenem Wert und Benchmark
    _pairs = [
        (_labels[0], own_digi, dig_bench),
        (_labels[1], own_auto, aut_bench),
        (_labels[2], own_paper, paper_bench),
        (_labels[3], own_know, know_bench),
    ]

    kpi_status: List[dict] = []
    for lbl, self_v, bench_v in _pairs:
        tol = _tol_for(lbl, branche)
        delta, stat_word = _classify(self_v, bench_v, lang, tol)
        kpi_status.append({
            "label": lbl,
            "self": self_v,
            "bench": bench_v,
            "delta": delta,
            "status": stat_word,
        })
    out["kpi_status"] = kpi_status

    # Badge-HTML generieren: Icon + Label + Delta (pp) + Status.  Für DE/EN
    # verwenden wir dieselben Icons.  Die CSS-Klassen (z. B. kpi-vorsprung)
    # werden später in den Templates definiert.
    def _badge_html(label: str, delta: int, status: str) -> str:
        sign = "+" if delta > 0 else ("" if delta == 0 else "−")
        delta_txt = f"{sign}{abs(delta)} pp"
        # Icon je Richtung
        icon = "↑" if delta > 0 else ("↔" if delta == 0 else "↓")
        # CSS-Klasse: Status in Kleinbuchstaben, Leerzeichen und Sonderzeichen entfernen
        cls = status.lower().replace(" ", "-").replace("ß", "ss").replace("ü", "u").replace("ö", "o").replace("ä", "a")
        return f'<span class="kpi-badge kpi-{cls}">{icon}&nbsp;{label} {delta_txt} ({status})</span>'

    badges_html = "<div class=\"kpi-badges\">" + "".join(
        _badge_html(item["label"], item["delta"], item["status"]) for item in kpi_status
    ) + "</div>"
    out["kpi_badges_html"] = badges_html

    # ------------------------------------------------------------------
    # KPI‑Übersicht: Ergänze eine prägnante Zusammenfassung der vier
    # Dimensionen direkt vor der vom LLM generierten Executive Summary.
    # Die LLM‑Prompts liefern oft vage oder widersprüchliche Aussagen
    # (z. B. „keine Werte vorliegend“), obwohl die Kachelwerte bekannt sind.
    # Daher erzeugen wir hier einen einheitlichen Satz, der die eigenen
    # Werte und die Branchenwerte gegenüberstellt.  Für die deutsche
    # Version wird der Benchmark der Automatisierung aus dem Kontext
    # (dig_bench, aut_bench) übernommen, Papierlosigkeit und Know‑how
    # verwenden den neutralen Wert 50 % als Vergleich.  Für die
    # englische Version wird ein entsprechender englischer Satz erzeugt.
    try:
        if lang == "de":
            # Zugriff auf lokale Variablen aus den Benchmarks
            dig = own_digi
            aut = own_auto
            paper = own_paper
            know = own_know
            dig_bm = dig_bench
            aut_bm = aut_bench
            paper_bm = paper_bench
            know_bm = know_bench
            # Übersetze die Prozentwerte in verbale Skalen (hoch/mittel/niedrig).  Diese
            # Einordnung sorgt dafür, dass Text und Kachelwerte konsistent sind.
            def _level_de(v: int) -> str:
                try:
                    val = int(v)
                except Exception:
                    return ""
                if val >= 80:
                    return "hoch"
                elif val >= 60:
                    return "mittel"
                else:
                    return "niedrig"
            digi_desc = _level_de(dig)
            aut_desc = _level_de(aut)
            paper_desc = _level_de(paper)
            know_desc = _level_de(know)
            # Compose a qualitative status overview without explicit percentages or numerical
            # benchmarks.  Use descriptive levels (hoch, mittel, niedrig) instead of
            # numbers and state the biggest gap qualitatively.  This avoids
            # quantitative KPI language in the narrative.
            summary_sentence = (
                f" Ihr Digitalisierungsgrad ist {digi_desc}, der Automatisierungsgrad ist {aut_desc}, "
                f"die Papierlosigkeit ist {paper_desc} und das KI‑Know‑how ist {know_desc}."
            )
            # Ermitteln Sie das größte Gap basierend auf der größten absoluten Differenz
            gaps = [
                (abs(own_digi - dig_bench), _labels[0]),
                (abs(own_auto - aut_bench), _labels[1]),
                (abs(own_paper - paper_bench), _labels[2]),
                (abs(own_know - know_bench), _labels[3]),
            ]
            gaps.sort(key=lambda x: x[0], reverse=True)
            summary_sentence += f" Größtes Gap: {gaps[0][1]}."
            # Use a generic heading "Statusübersicht" instead of "KPI‑Überblick" to
            # avoid duplication with model-generated sections.
            #summary_prefix = "<p><strong>Statusübersicht:</strong>" + summary_sentence + "</p>"
        else:
            dig = own_digi
            aut = own_auto
            paper = own_paper
            know = own_know
            dig_bm = dig_bench
            aut_bm = aut_bench
            paper_bm = paper_bench
            know_bm = know_bench
            def _level_en(v: int) -> str:
                try:
                    val = int(v)
                except Exception:
                    return ""
                if val >= 80:
                    return "high"
                elif val >= 60:
                    return "medium"
                else:
                    return "low"
            digi_desc = _level_en(dig)
            aut_desc = _level_en(aut)
            paper_desc = _level_en(paper)
            know_desc = _level_en(know)
            # Compose a qualitative status overview for English reports without
            # explicit percentages.  Use high/medium/low descriptors and state
            # the largest gap qualitatively.
            summary_sentence = (
                f" Your digitalisation level is {digi_desc}, automation is {aut_desc}, "
                f"paperless processes are {paper_desc}, and AI know‑how is {know_desc}."
            )
            gaps = [
                (abs(own_digi - dig_bench), _labels[0]),
                (abs(own_auto - aut_bench), _labels[1]),
                (abs(own_paper - paper_bench), _labels[2]),
                (abs(own_know - know_bench), _labels[3]),
            ]
            gaps.sort(key=lambda x: x[0], reverse=True)
            summary_sentence += f" Largest gap: {gaps[0][1]}."
            # Use "Status overview" instead of "KPI overview" to avoid duplication.
            summary_prefix = "<p><strong>Status overview:</strong>" + summary_sentence + "</p>"
        # Prepend the summary only if an executive summary exists
        if out.get("exec_summary_html"):
            out["exec_summary_html"] = summary_prefix + "\n" + out["exec_summary_html"]
        # After prepending the summary, remove any additional KPI overview paragraphs
        # that may have been generated by the language model. These paragraphs often
        # begin with a heading like "KPI‑Überblick" (DE) or "KPI overview" (EN) and
        # include their own interpretation of the four metrics, which can
        # contradict the deterministic summary. Use a broad regex to remove
        # everything from the heading up to the next section (h3 or list/start of
        # another heading) or the next major heading (e.g. Top Chancen, Zentrale
        # Risiken, Nächste Schritte).  This prevents conflicting narratives.
        try:
            esc = out.get("exec_summary_html") or ""
            if esc:
                # Remove DE KPI overview blocks.  Handle headings wrapped in <h3>
                # as well as plain text paragraphs starting with "KPI-Überblick".  Do
                # not remove the subsequent narrative paragraph – only the heading.
                # First remove heading+content variants generated in complex structures.
                esc = re.sub(
                    r"(?is)(?:<h3[^>]*>\s*)?KPI[\s\-]*Überblick\s*:?\s*</h3>?\s*.*?(?=(<h3|<p\s*><strong|<p\s*>Top\s*-?Chancen|<p\s*>Zentrale\s*-?Risiken|<p\s*>Nächste\s*-?Schritte|$))",
                    "",
                    esc,
                )
                # Then remove any plain paragraph containing only the KPI heading.
                esc = re.sub(r"(?is)<p>\s*KPI[\s\-]*Überblick\s*</p>", "", esc)
                # Remove EN KPI overview blocks.  Catch both heading and plain text forms
                esc = re.sub(
                    r"(?is)(?:<h3[^>]*>\s*)?KPI\s*overview\s*:?\s*</h3>?\s*.*?(?=(<h3|<p\s*><strong|<p\s*>Top\s*opportunities|<p\s*>Key\s*risks|<p\s*>Next\s*steps|$))",
                    "",
                    esc,
                )
                # Remove the plain paragraph containing only the KPI heading.
                esc = re.sub(r"(?is)<p>\s*KPI\s*overview\s*</p>", "", esc)
                out["exec_summary_html"] = esc
        except Exception:
            # Ignore any errors during removal; keep the current summary
            pass
    except Exception:
        # In case of unexpected errors, leave the summary untouched
        pass

    # Timeline-Sektion aus der Roadmap extrahieren (30/3M/12M)
    def _distill_timeline_sections(source_html: str, lang: str = "de") -> Dict[str, List[str]]:
        """Extrahiert 2–3 stichpunktartige Maßnahmen für 30 Tage, 3 Monate, 12 Monate."""
        if not source_html:
            return {}
        model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
        if lang == "de":
            sys = "Sie extrahieren präzise Listen aus HTML."
            usr = (
                "<h3>30 Tage</h3><ul>…</ul><h3>3 Monate</h3><ul>…</ul><h3>12 Monate</h3><ul>…</ul>\n"
                "- 2–3 Punkte je Liste (Stichworte ohne Erklärungen)\n\nHTML:\n" + source_html
            )
        else:
            sys = "You extract concise lists from HTML."
            usr = (
                "<h3>30 days</h3><ul>…</ul><h3>3 months</h3><ul>…</ul><h3>12 months</h3><ul>…</ul>\n"
                "- 2–3 bullets per list (short phrases only)\n\nHTML:\n" + source_html
            )
        try:
            out_html = _chat_complete([
                {"role": "system", "content": sys},
                {"role": "user", "content": usr}
            ], model_name=model, temperature=0.2)
            html = ensure_html(out_html, lang)
        except Exception:
            return {}
        # parse lists
        res = {"t30": [], "t90": [], "t365": []}
        for match in re.finditer(r"<h3[^>]*>([^<]+)</h3>\s*<ul>(.*?)</ul>", html, re.S|re.I):
            header = match.group(1).lower()
            items_html = match.group(2)
            items = re.findall(r"<li[^>]*>(.*?)</li>", items_html, re.S)
            items = [re.sub(r"<[^>]+>", "", it).strip() for it in items]
            items = [it for it in items if it]
            if '30' in header:
                res['t30'] = items[:3]
            elif '3' in header and ('monate' in header or 'months' in header):
                res['t90'] = items[:3]
            elif '12' in header:
                res['t365'] = items[:3]
        return res

    timeline_sections = _distill_timeline_sections(out.get("roadmap_html", ""), lang=lang)
    out["timeline"] = timeline_sections

    # Risiko-Heatmap heuristisch erstellen
    risk_rows = []
    # Bias/Transparenz – höheres Risiko bei geringem KI-Know-how
    know = own_know
    if know < 30:
        bias_lvl = 'hoch'
    elif know < 60:
        bias_lvl = 'mittel'
    else:
        bias_lvl = 'niedrig'
    risk_rows.append({"category": "Bias/Transparenz" if lang == "de" else "Bias/Transparency", "level": bias_lvl})
    # Datenschutz/AVV – höheres Risiko bei niedrigen Papierlos-Werten
    if own_paper < 30:
        ds_lvl = 'hoch'
    elif own_paper < 60:
        ds_lvl = 'mittel'
    else:
        ds_lvl = 'niedrig'
    risk_rows.append({"category": "Datenschutz/AVV" if lang == "de" else "Data protection/AV", "level": ds_lvl})
    # Lieferantenrisiko – setze medium als Default
    risk_rows.append({"category": "Lieferanten-Risiko" if lang == "de" else "Supplier risk", "level": 'mittel' if lang == 'de' else 'medium'})
    # Abhängigkeit Anbieter – Risiko hoch bei geringem Digitalisierungsgrad
    if own_digi < 30:
        dep_lvl = 'hoch'
    elif own_digi < 60:
        dep_lvl = 'mittel'
    else:
        dep_lvl = 'niedrig'
    risk_rows.append({"category": "Abhängigkeit Anbieter" if lang == "de" else "Vendor lock-in", "level": dep_lvl})
    out["risk_heatmap"] = risk_rows

    # ---------------------------------------------------------------------
    # Fallback practice example if the generated case study does not match
    # the respondent's sector.  Occasionally the language model returns a
    # Maschinenbau example for consulting or other industries.  When this
    # happens, replace the case study with a deterministic one from
    # ``data/praxisbeispiele.md`` based on the branch.  Only trigger if the
    # text mentions "Maschinenbau" and the branch is not Bau/Industrie/Produktion.
    try:
        if branche and isinstance(out.get("praxisbeispiel"), str):
            pb_lower = out["praxisbeispiel"].lower()
            # If the case study references Maschinenbau but the client's
            # branch is different, use the fallback.
            if "maschinenbau" in pb_lower and not any(b in branche for b in ["bau", "industrie", "produktion"]):
                fallback_html = _fallback_praxisbeispiel(branche, lang)
                if fallback_html:
                    out["praxisbeispiel"] = fallback_html
    except Exception:
        # Silently ignore fallback errors
        pass

    # Förder-Badges aus erster Programmeinträgen
    badges = []
    try:
        # Only generate badges from the first funding entry.  We convert
        # abbreviations to full names and capitalise the region.  A maximum of
        # one funding row is used to avoid cluttering the report with badges.
        if (out.get("foerderprogramme_table") or []):
            row = (out.get("foerderprogramme_table") or [])[0]
            zg = (row.get("zielgruppe") or "").lower()
            # Solo/KMU badge
            # In the Gold‑Standard report we deliberately omit explicit
            # "Solo-geeignet" or "KMU-geeignet" badges from the funding
            # section.  Including these labels led to stray lines such as
            # "Solo-geeignet" appearing after the funding table in the PDF.
            # If desired, these badges can be re-enabled by uncommenting
            # the code below.
            # if any(tok in zg for tok in ["solo", "freelanc", "freiberuf", "einzel"]):
            #     badges.append("Solo-geeignet" if lang == "de" else "solo-friendly")
            # elif any(tok in zg for tok in ["kmu", "sme"]):
            #     badges.append("KMU-geeignet" if lang == "de" else "SME-friendly")
            # Region badge: map abbreviations to full names via alias_map.  We
            # no longer append the region name as a badge to avoid stray
            # abbreviations like "be" appearing in the funding table.  If
            # desired, a region badge can be added here by uncommenting the
            # following lines.
            # user_region = (data.get("bundesland") or data.get("state") or "").strip()
            # alias_map_local = {
            #     "nrw": "Nordrhein-Westfalen",
            #     "by": "Bayern",
            #     "bw": "Baden-Württemberg",
            #     "be": "Berlin",
            #     "bb": "Brandenburg",
            #     "he": "Hessen",
            #     "hh": "Hamburg",
            #     "sl": "Saarland",
            #     "sn": "Sachsen",
            #     "st": "Sachsen-Anhalt",
            #     "sh": "Schleswig-Holstein",
            #     "th": "Thüringen",
            #     "mv": "Mecklenburg-Vorpommern",
            #     "rp": "Rheinland-Pfalz",
            #     "ni": "Niedersachsen",
            # }
            # if user_region:
            #     region_key = user_region.lower()
            #     full_region = alias_map_local.get(region_key, user_region)
            #     badges.append(full_region if full_region.istitle() else full_region.title())
            # Förderhöhe badge: parse percentage values
            fstr = row.get("foerderhoehe") or row.get("amount") or ""
            m = re.search(r"(\d+\s*%|\d+[\.,]\d+\s*%)", fstr.replace('bis zu','').replace('bis','').replace('up to',''))
            if m:
                percent = m.group(1).strip()
                badges.append(("bis " + percent) if lang == "de" else ("up to " + percent))
    except Exception:
        pass
    # Remove duplicates while preserving order
    seen = set(); unique_badges = []
    for b in badges:
        if b and b not in seen:
            seen.add(b); unique_badges.append(b)
    out["funding_badges"] = unique_badges

    # One-Pager & TOC
    out["one_pager_html"] = ""  # optionaler Block (nicht genutzt)
    out["toc_html"] = _toc_from_report(out, lang)

    # Append personal and glossary sections
    out["ueber_mich_html"] = build_ueber_mich_section(lang=lang)
    out["glossary_html"] = build_glossary_section(lang=lang)

    # Sanitize all string outputs to remove invisible or problematic unicode characters.
    # This prevents stray characters like "\uFFFE" appearing in the rendered PDF.
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = _sanitize_text(v)

    # Strip internal prompt guidelines (e.g. "Zusätzliche Anweisungen" or "Additional Instructions")
    # from all HTML sections.  These guidelines are intended only for the language
    # model and must not appear in the final report.  The removal targets both
    # German and English headings and deletes everything up to the next heading.
    def _strip_internal_guidelines(html: str) -> str:
        """
        Remove internal instruction sections from a block of HTML.  Sections
        beginning with headings like "Zusätzliche Anweisungen…" or
        "Additional Instructions…" (in any h2/h3 level) are excised along with
        their content until the next heading or end of the HTML.

        Parameters
        ----------
        html : str
            The HTML to clean.

        Returns
        -------
        str
            The cleaned HTML without internal instruction sections.
        """
        try:
            if not html or not isinstance(html, str):
                return html
            # Remove DE/EN guidelines within h2/h3 tags or plain text headings.
            # First handle general "Zusätzliche/Additional Instructions" sections as before.
            html = re.sub(
                r"(?is)<h[23][^>]*>\s*Zusätzliche\s+Anweisungen[^<]*</h[23]>.*?(?=<h[23]|$)",
                "",
                html,
            )
            html = re.sub(
                r"(?is)<h[23][^>]*>\s*Additional\s+Instructions[^<]*</h[23]>.*?(?=<h[23]|$)",
                "",
                html,
            )
            html = re.sub(
                r"(?is)##\s*Zusätzliche\s+Anweisungen[^\n]*\n.*", "", html
            )
            html = re.sub(
                r"(?is)##\s*Additional\s+Instructions[^\n]*\n.*", "", html
            )
            # Remove any internal guidance headings specified in the list below.
            internal_heads = [
                r"Listen\s+kürzen\s+und\s+zusammenfassen",
                r"Struktur\s+der\s+Quick\s+Wins",
                r"12[\-\u2010-\u2015]?Monats[\-\u2010-\u2015]?Roadmap",
                r"Gamechanger[\-\u2010-\u2015]?Kapitel",
                r"Förderlogik",
                r"KI[\-\u2010-\u2015]?Tools[\-\u2010-\u2015]?Tabelle",
                r"Weitere\s+Hinweise",
                r"Gold\+\s*Ergänzungen",
            ]
            for h in internal_heads:
                # Remove sections wrapped in h2/h3 tags
                html = re.sub(
                    rf"(?is)<h[23][^>]*>\s*{h}\s*</h[23]>.*?(?=<h[23]|$)",
                    "",
                    html,
                )
                # Remove plain text headings up to the next heading
                html = re.sub(
                    rf"(?is)\b{h}\b.*?(?=<h[23]|$)",
                    "",
                    html,
                )
            return html
        except Exception:
            return html

    # Apply guideline stripping to HTML fields
    for _k in [
        "exec_summary_html",
        "quick_wins_html",
        "risks_html",
        "recommendations_html",
        "roadmap_html",
        "foerderprogramme_html",
        "tools_html",
        "compliance_html",
        "gamechanger_html",
        "sections_html",
    ]:
        if out.get(_k):
            out[_k] = _strip_internal_guidelines(out.get(_k) or "")

    # -------------------------------------------------------------------------
    # Add branch innovation introduction and gamechanger blocks to the report
    #
    # The Innovation & Gamechanger section of the PDF relies on two context
    # variables: ``branchen_innovations_intro`` and ``gamechanger_blocks``.
    # These are normally computed via ``build_context`` and
    # ``add_innovation_features`` during prompt generation.  However, the
    # HTML returned from GPT does not expose these values directly.  To
    # ensure that the corresponding section is rendered in the final PDF, we
    # recompute the context here using the questionnaire data and branch.
    # If any error occurs (e.g. missing helper functions), the values
    # default to empty strings so that the template simply omits the card.
    try:
        tmp_ctx = build_context(data, branche, lang)
        tmp_ctx = add_innovation_features(tmp_ctx, branche, data)
        out["branchen_innovations_intro"] = tmp_ctx.get("branchen_innovations_intro", "")
        out["gamechanger_blocks"] = tmp_ctx.get("gamechanger_blocks", "")
    except Exception:
        # In case of failure, ensure the keys exist but are empty to avoid
        # template errors.
        out.setdefault("branchen_innovations_intro", "")
        out.setdefault("gamechanger_blocks", "")

    # Final pass: remove any remaining LLM 'KPI overview' narratives and extraneous benchmark sections.
    try:
        # Remove duplicate KPI overview blocks in German and English
        esc = out.get("exec_summary_html") or ""
        # Define a pattern matching whitespace, non-breaking spaces and hyphen-like characters
        # between "KPI" and "Überblick".  Use single backslash escapes so that \s and
        # Unicode sequences are interpreted by the regex engine rather than matching
        # literal backslashes.  This ensures that phrases like "KPI‑Überblick" or
        # "KPI Überblick" are correctly detected and removed.
        hy = r"[\s\u00A0\u2010-\u2015-]+"
        # German version
        esc = re.sub(
            rf"(?is)(?:<h3[^>]*>)?\\s*KPI{hy}Überblick\\s*(?:</h3>)?\\s*.*?(?=(?:<h3[^>]*>)|Top{hy}Chancen|Zentrale{hy}Risiken|Nächste{hy}Schritte|$)",
            "",
            esc,
        )
        # English version
        esc = re.sub(
            rf"(?is)(?:<h3[^>]*>)?\\s*KPI{hy}overview\\s*(?:</h3>)?\\s*.*?(?=(?:<h3[^>]*>)|Top{hy}opportunities|Key{hy}risks|Next{hy}steps|$)",
            "",
            esc,
        )
        out["exec_summary_html"] = esc
        # Remove Reifegrad Benchmark section from gamechanger_html if present
        gc_sec = out.get("gamechanger_html") or ""
        gc_sec = re.sub(
            r"(?is)<h3[^>]*>\s*Reifegrad[\s\u00A0\u2010-\u2015-]*Benchmark\s*</h3>.*?(?=<h3|$)",
            "",
            gc_sec,
        )
        out["gamechanger_html"] = gc_sec
    except Exception:
        pass
    # ----------------------------------------------------------------------
    # Gold‑Standard sanitisation and clean‑up before returning.  The narrative
    # sections (quick wins, risks, recommendations and roadmap) should not
    # contain explicit lists or numeric values.  We define a local helper
    # function that removes <ul>/<ol>/<li> tags, replaces list items with
    # sentence separators and strips standalone numbers, percentage signs and
    # currency symbols.  This helper does not touch legal references (e.g.
    # DSGVO articles) because sanitisation is applied only to selected keys.
    def _strip_lists_and_numbers(html: str) -> str:
        import re as _re  # use local alias to avoid shadowing outer scope
        if not html or not isinstance(html, str):
            return html
        # Remove unordered/ordered list tags
        html = _re.sub(r"</?(ul|ol)[^>]*>", "", html)
        # Replace list items with periods and spaces
        html = html.replace("<li>", "").replace("</li>", ". ")
        # Remove numeric patterns together with leading hyphens and common units.  This
        # collapses phrases like "15 min", "30 days" or "3 Monate" into nothing,
        # preventing stray hyphens or units from lingering in the text.  Units are
        # handled in both English and German.  A preceding hyphen (e.g. "-15") is
        # removed along with the number and unit.  Currency symbols and percent
        # signs are also stripped.
        html = _re.sub(
            r"\s*[-]?\s*\d+[\.,]?\d*\s*(%|€|EUR|T€|T\\u20AC|Tage|Wochen|Monate|Days|Weeks|Months|Minute|Minutes|Minuten|Stunden|Hours|Hour)\b",
            "",
            html,
            flags=_re.IGNORECASE,
        )
        # Remove any remaining standalone numbers (e.g. "30" or "12") that are not
        # associated with a specific unit.  This prevents bare digits from
        # appearing after the previous substitution.  Excludes numbers that may
        # form part of an alphanumeric word (e.g. "ISO27001" remains untouched).
        html = _re.sub(r"(?<![\w])\d+[\.,]?\d*(?![\w])", "", html)
        # Remove leftover percentage signs or plus/minus markers that no longer have
        # numbers attached (e.g. "+%", "-%", " %").  These often appear after
        # numerical values have been stripped and can confuse the reader.
        html = _re.sub(r"[+\-]?\s*%", "", html)
        # Remove stray hyphens that might remain at the start of a sentence or
        # following whitespace after numbers have been removed.
        html = _re.sub(r"(\s|^)[\-–]\s+", r"\1", html)
        # Remove leftover units or descriptors that begin with a hyphen but are
        # no longer preceded by a number (e.g. "-min", "-Wochen", "-Pager").
        # Without this additional cleanup, hyphenated time or count terms may
        # remain after numeric stripping.  Handle both German and English
        # variants and ignore case.
        html = _re.sub(
            r"\s*[\-\u2010-\u2015]\s*(min|minute|minuten|stunden|hour|hours|wochen|weeks|monate|months|pager|projektbeschreibung|poc|pocs|wochen-pocs)\b",
            "",
            html,
            flags=_re.IGNORECASE,
        )
        # Collapse multiple spaces and punctuation into a single space.
        html = _re.sub(r"\s{2,}", " ", html)
        return html.strip()

    # Apply sanitisation to narrative HTML fields.  In addition to quick wins,
    # risks, recommendations and roadmap, we sanitise the vision, gamechanger
    # and executive summary sections to remove residual numbers, units and list
    # structures.  Including the executive summary ensures that stray
    # percentages or KPI references created by the LLM are removed.  The
    # "praxisbeispiel" key (which contains fallback case study HTML) is also
    # sanitised.
    for _key in [
        "exec_summary_html",
        "quick_wins_html",
        "risks_html",
        "recommendations_html",
        "roadmap_html",
        "vision_html",
        "gamechanger_html",
        "praxisbeispiel",
            "compliance_html",
    ]:
        if isinstance(out.get(_key), str):
            out[_key] = _strip_lists_and_numbers(out[_key])
    # If roadmap is a list of items (post‑processed), sanitise each item
    if isinstance(out.get("roadmap"), list):
        out["roadmap"] = [ _strip_lists_and_numbers(str(item)) for item in out["roadmap"] ]
    # If the timeline contains bullet points extracted from the roadmap, apply
    # sanitisation to each item in each phase (t30, t90, t365) so that
    # left‑over numbers, hyphens or units are removed.
    if isinstance(out.get("timeline"), dict):
        for _phase in ["t30", "t90", "t365"]:
            items = out["timeline"].get(_phase)
            if isinstance(items, list):
                out["timeline"][_phase] = [ _strip_lists_and_numbers(str(it)) for it in items ]
    # Remove KPI benchmarks and badges entirely
    out["benchmarks"] = {}
    out["kpi_badges_html"] = ""
    return out


def build_ueber_mich_section(lang: str = "de") -> str:
    """
    Build an "Über mich" section for the report.  Uses the user's profile to
    provide a personal introduction.  In a production system this information
    might come from user metadata; here it is hardcoded based on the project
    description.

    :param lang: language code
    :return: HTML string with the personal introduction
    """
    # In the Gold‑Standard version we avoid a biographical third‑person description.
    # Instead we provide a neutral, service‑oriented introduction based on the
    # "Leistung & Nachweis" concept.  The wording emphasises the role of a
    # TÜV‑certified AI manager and the specific areas of expertise.  The
    # contact information remains unchanged.  Note that the surrounding
    # template already includes a heading ("Über mich"/"About me"), so we
    # omit any additional headings here.
    if lang == "de":
        return (
            "<p>Als TÜV-zertifizierter KI-Manager begleite ich Unternehmen bei der sicheren "
            "Einführung, Nutzung und Audit-Vorbereitung von KI – mit klarer Strategie, "
            "dokumentierter Förderfähigkeit und DSGVO-Konformität.</p>"
            "<ul>"
            "<li><strong>KI-Strategie & Audit:</strong> TÜV-zertifizierte Entwicklung und Vorbereitung auf Prüfungen</li>"
            "<li><strong>EU AI Act & DSGVO:</strong> Beratung entlang aktueller Vorschriften und Standards</li>"
            "<li><strong>Dokumentation & Governance:</strong> Aufbau förderfähiger KI-Prozesse und Nachweise</li>"
            "<li><strong>Minimiertes Haftungsrisiko:</strong> Vertrauen bei Kunden, Partnern und Behörden</li>"
            "</ul>"
            "<p>Kontakt: <a href=\"mailto:kontakt@ki-sicherheit.jetzt\">kontakt@ki-sicherheit.jetzt</a> · "
            "<a href=\"https://ki-sicherheit.jetzt\">ki-sicherheit.jetzt</a></p>"
        )
    else:
        return (
            "<p>As a TÜV-certified AI manager I support organisations in safely implementing, using and preparing "
            "for audits of AI, focusing on clear strategy, documented eligibility for funding and GDPR compliance.</p>"
            "<ul>"
            "<li><strong>AI strategy & audit:</strong> Certified development and audit preparation</li>"
            "<li><strong>EU AI Act & GDPR:</strong> Guidance along current regulations and standards</li>"
            "<li><strong>Documentation & governance:</strong> Establishing fundable AI processes and evidence</li>"
            "<li><strong>Minimised liability risk:</strong> Building trust with clients, partners and authorities</li>"
            "</ul>"
            "<p>Contact: <a href=\"mailto:kontakt@ki-sicherheit.jetzt\">kontakt@ki-sicherheit.jetzt</a> · "
            "<a href=\"https://ki-sicherheit.jetzt\">ki-sicherheit.jetzt</a></p>"
        )


def build_glossary_section(lang: str = "de") -> str:
    """
    Build a simple glossary of key terms used in the report.  This helps readers
    unfamiliar with AI or compliance terminology.  Definitions are intentionally
    kept brief and non‑technical.

    :param lang: language code
    :return: HTML string with glossary entries
    """
    if lang == "de":
        entries = {
            "KI (Künstliche Intelligenz)": "Technologien, die aus Daten lernen und selbstständig Entscheidungen treffen oder Empfehlungen aussprechen.",
            "DSGVO": "Datenschutz-Grundverordnung der EU; regelt den Umgang mit personenbezogenen Daten.",
            "DSFA": "Datenschutz-Folgenabschätzung; Analyse der Risiken für Betroffene bei bestimmten Datenverarbeitungen.",
            "EU AI Act": "Zukünftige EU-Verordnung, die Anforderungen und Risikoklassen für KI-Systeme festlegt.",
            "Quick Win": "Maßnahme mit geringem Aufwand und schnellem Nutzen.",
            "MVP": "Minimum Viable Product; erste funktionsfähige Version eines Produkts mit minimalem Funktionsumfang.",
        }
        out = ["<p><strong>Glossar</strong></p>"]
        out.append("<ul>")
        for term, definition in entries.items():
            out.append(f"<li><strong>{term}</strong>: {definition}</li>")
        out.append("</ul>")
        return "\n".join(out)
    else:
        entries = {
            "AI (Artificial Intelligence)": "Technologies that learn from data and can make decisions or generate recommendations on their own.",
            "GDPR": "General Data Protection Regulation; EU regulation governing personal data processing.",
            "DPIA": "Data Protection Impact Assessment; analysis of risks to individuals for certain processing operations.",
            "EU AI Act": "Upcoming EU legislation specifying requirements and risk classes for AI systems.",
            "Quick Win": "Action with low effort and immediate benefit.",
            "MVP": "Minimum Viable Product; first working version of a product with core functionality only.",
        }
        out = ["<p><strong>Glossary</strong></p>"]
        out.append("<ul>")
        for term, definition in entries.items():
            out.append(f"<li><strong>{term}</strong>: {definition}</li>")
        out.append("</ul>")
        return "\n".join(out)


def generate_qr_code_uri(link: str) -> str:
    """
    Generate a QR code image URI for the given link.  This implementation
    delegates the generation to Google's Chart API, which returns a PNG QR code.
    Note: this relies on external network access when rendering the PDF; if
    offline use is required, consider bundling a pre‑generated QR code.

    :param link: URL to encode in the QR code
    :return: direct link to a QR code image
    """
    from urllib.parse import quote
    encoded = quote(link, safe='')
    # 200x200 pixel PNG QR code
    return f"https://chart.googleapis.com/chart?chs=200x200&cht=qr&chl={encoded}&choe=UTF-8"

def generate_preface(lang: str = "de", score_percent: Optional[float] = None) -> str:
    """
    Build a short introductory paragraph for the report.  In the Gold‑Standard
    version we avoid referring to a single aggregated readiness score and
    instead describe the report itself.  For German users the report is
    labelled as "KI‑Status‑Report", for English readers the term
    "AI readiness" remains, but no explicit score is included.
    """
    if lang == "de":
        preface = (
            "<p>Dieses Dokument fasst die Ergebnisse Ihres <b>KI‑Status‑Reports</b> zusammen "
            "und bietet individuelle Empfehlungen für die nächsten Schritte. Es basiert auf Ihren Angaben und "
            "berücksichtigt aktuelle gesetzliche Vorgaben, Fördermöglichkeiten und technologische Entwicklungen.</p>"
        )
        # In the Gold‑Standard version no aggregated score is displayed.  The individual
        # KPIs for Digitalisierung, Automatisierung, Papierlosigkeit und KI‑Know‑how
        # are visualised elsewhere in the report.
        return preface
    else:
        preface = (
            "<p>This document summarises your <b>AI readiness report</b> and provides tailored next steps. "
            "It is based on your input and considers legal requirements, funding options and current AI developments.</p>"
        )
        return preface

def analyze_briefing(payload: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    lang = _norm_lang(lang or payload.get("lang") or payload.get("language") or payload.get("sprache"))
    report = generate_full_report(payload, lang=lang)
    # Provide a structured roadmap list for templating when available.  When
    # postprocessing is enabled, the roadmap chapter may be a list rather than
    # HTML.  Expose it under the key "roadmap_items" for the template to
    # render a tabular roadmap.  If no structured roadmap exists, the
    # template will fall back to timeline/swimlane or HTML.
    try:
        if isinstance(report.get("roadmap"), list) and not report.get("roadmap_items"):
            report["roadmap_items"] = report["roadmap"]
    except Exception:
        pass
    env, template_name = _jinja_env(), _pick_template(lang)
    if template_name:
        tmpl = env.get_template(template_name)
        footer_de = ("TÜV-zertifiziertes KI-Management © {year}: Wolf Hohl · "
                     "E-Mail: kontakt@ki-sicherheit.jetzt · DSGVO- & EU-AI-Act-konform · "
                     "Alle Angaben ohne Gewähr; keine Rechtsberatung.")
        footer_en = ("TÜV-certified AI Management © {year}: Wolf Hohl · "
                     "Email: kontakt@ki-sicherheit.jetzt · GDPR & EU-AI-Act compliant · "
                     "No legal advice.")
        footer_text = (footer_de if lang == "de" else footer_en).format(year=datetime.now().year)
        # Compute company size classification for template variables.  We reuse
        # the logic from build_context to ensure consistent labels.  Because
        # build_context already normalises language, ensure lang is resolved.
        def _compute_size_info(d: dict) -> Dict[str, str]:
            # Determine employee count similar to build_context
            def get_count():
                for key in [
                    "mitarbeiter", "mitarbeiterzahl", "anzahl_mitarbeiter", "employees",
                    "employee_count", "team_size", "anzahl_mitarbeiterinnen"
                ]:
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
            emp_count = get_count()
            self_emp = is_self_employed(d)
            category = "solo" if self_emp else None
            if category is None:
                if emp_count is None:
                    category = "team"
                elif emp_count <= 1:
                    category = "solo"
                elif emp_count <= 10:
                    category = "team"
                else:
                    category = "kmu"
            if lang_resolved == "de":
                if category == "solo":
                    label = "Solo-Unternehmer:in"
                elif category == "team":
                    label = "Team (2–10 Mitarbeitende)"
                else:
                    label = "KMU (11+ Mitarbeitende)"
            else:
                if category == "solo":
                    label = "Solo entrepreneur"
                elif category == "team":
                    label = "Small team (2–10 people)"
                else:
                    label = "SME (11+ people)"
            return {
                "company_size_category": category,
                "company_size_label": label,
                "unternehmensgroesse": label,
                "selbststaendig": "Ja" if self_emp and lang_resolved == "de" else ("Nein" if lang_resolved == "de" else ("Yes" if self_emp else "No")),
                "self_employed": "Yes" if self_emp else "No",
            }

        lang_resolved = lang  # use the resolved language from outer scope
        size_info = _compute_size_info(payload)
        ctx = {
            "lang": lang,
            "today": datetime.now().strftime("%Y-%m-%d"),
            "datum": datetime.now().strftime("%Y-%m-%d"),
            "score_percent": report.get("score_percent", 0),
            "preface": report.get("preface",""),
            "exec_summary_html": report.get("exec_summary_html",""),
            "quick_wins_html": report.get("quick_wins_html",""),
            "risks_html": report.get("risks_html",""),
            "recommendations_html": report.get("recommendations_html",""),
            "roadmap_html": report.get("roadmap_html",""),
            # Structured roadmap items (list of dicts) for table rendering.  When this
            # list is empty the template falls back to timeline/swimlane or HTML.
            "roadmap_items": report.get("roadmap_items", []),
            "sections_html": report.get("sections_html",""),
            "compliance_html": report.get("compliance_html",""),
            "vision_html": report.get("vision_html",""),
            "one_pager_html": report.get("one_pager_html",""),
            "toc_html": report.get("toc_html",""),
            "chart_data_json": report.get("chart_data_json","{}"),
            "foerderprogramme_table": report.get("foerderprogramme_table",[]),
            "foerderprogramme_html": report.get("foerderprogramme_html",""),
            "tools_table": report.get("tools_table",[]),
            "tools_html": report.get("tools_html",""),
            "dynamic_funding_html": report.get("dynamic_funding_html",""),
            "footer_text": footer_text,
            "logo_main": _data_uri_for("ki-sicherheit-logo.webp") or _data_uri_for("ki-sicherheit-logo.png"),
            "logo_tuev": _data_uri_for("tuev-logo-transparent.webp") or _data_uri_for("tuev-logo.webp"),
            "logo_euai": _data_uri_for("eu-ai.svg"),
            "logo_dsgvo": _data_uri_for("dsgvo.svg"),
            "badge_ready": _data_uri_for("ki-ready-2025.webp"),
            # neue Kontexte für KPI-Kacheln, Benchmarks, Timeline, Risiko-Heatmap & Förder-Badges
            "kpis": report.get("kpis", []),
            "benchmarks": report.get("benchmarks", {}),
            "timeline": report.get("timeline", {}),
            "risk_heatmap": report.get("risk_heatmap", []),
            # personal & glossary sections
            "ueber_mich_html": report.get("ueber_mich_html", ""),
            "glossary_html": report.get("glossary_html", ""),
            # QR code linking to the KI‑Sicherheit website
            # QR‑Codes are omitted in the Gold‑Standard version.
            "qr_code_uri": "",
            "funding_badges": report.get("funding_badges", []),
            # Expose innovation & gamechanger content to the template.  Without
            # these keys the "Innovation & Gamechanger" card remains hidden,
            # even though the gamechanger_blocks and industry intros are
            # computed during report generation.  By passing them through
            # analyse_briefing we allow the Jinja template to conditionally
            # render the section when content is available.
            "branchen_innovations_intro": report.get("branchen_innovations_intro", ""),
            "gamechanger_blocks": report.get("gamechanger_blocks", ""),
            # The LLM-generated Innovation & Gamechanger chapter.  When present
            # this HTML is rendered in place of the fallback intro/blocks.
            "gamechanger_html": report.get("gamechanger_html", ""),
            # company size info for feedback links and prompt context
            **size_info,
        }
        html = tmpl.render(**ctx)
        # Fail‑fast if unresolved Jinja tokens remain in the rendered HTML.  Incomplete
        # rendering would otherwise propagate into the PDF and show raw template
        # markers.  Raising here ensures the caller can handle the error and
        # avoids generating a broken PDF.
        if "{{" in html or "{%" in html:
            raise RuntimeError("Template not fully rendered (unresolved Jinja tags)")
    else:
        # Fallback rendering (rarely used) without Jinja templates.  Use the new
        # report names.  For German we call it KI‑Status‑Report, in English
        # the classic AI Readiness name remains.  The aggregated score is not
        # referenced here.
        title = "KI-Status-Report" if lang == "de" else "AI Readiness Report"
        html = (
            f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>body{{font-family:Arial;padding:24px;}}</style></head>"
            f"<body><h1>{title} · {datetime.now().strftime('%Y-%m-%d')}</h1>"
            f"<div>{report.get('preface','')}</div>"
            f"<h2>{'Executive Summary' if lang!='de' else 'Executive Summary'}</h2>{report.get('exec_summary_html','')}"
            f"<div style='display:flex;gap:24px;'><div style='flex:1'>{report.get('quick_wins_html','')}</div>"
            f"<div style='flex:1'>{report.get('risks_html','')}</div></div>"
            f"<h2>{'Next steps' if lang!='de' else 'Nächste Schritte'}</h2>"
            f"{report.get('recommendations_html','') or report.get('roadmap_html','')}"
            f"{report.get('sections_html','')}"
            f"<hr><small>TÜV-zertifiziertes KI-Management © {datetime.now().year}: Wolf Hohl · "
            f"E-Mail: kontakt@ki-sicherheit.jetzt</small></body></html>"
        )

    html = _inline_local_images(strip_code_fences(html))
    # Final sanitisation: remove soft hyphens, zero-width spaces and invalid markers which can leak into the PDF
    try:
        if isinstance(html, str):
            html = html.replace("\u00AD", "").replace("\u200B", "").replace("\uFEFF", "").replace("\uFFFE", "")
    except Exception:
        pass
    return {"html": html, "lang": lang, "score_percent": report.get("score_percent", 0),
            "meta": {"chapters":[k for k in ("executive_summary","vision","tools","foerderprogramme","roadmap","compliance","praxisbeispiel") if report.get(k)],
                     "one_pager": True}}