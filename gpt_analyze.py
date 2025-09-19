
# -*- coding: utf-8 -*-
"""
gpt_analyze.py — Gold-Standard
Version: 2025-09-19

Purpose
-------
Generate a warm, narrative KI-Readiness report (DE/EN) with
DSGVO & EU-AI-Act-ready phrasing. This module renders the
Jinja template itself and returns HTML to the caller.

Key fixes vs. broken versions seen in logs:
- Always defines `meta` so templates never fail with "meta is undefined".
- Implements `_strip_lists_and_numbers` used by fallbacks.
- Removes stray top-level `return`/indent errors.
- Provides robust fallbacks when prompts or data are missing.
- Keeps tables out of primary sections; narrative HTML only.
- Still exposes `funding_table`/`tools_table` for template fallbacks.

External deps expected in the app image:
- jinja2, httpx, openai

Environment variables (optional):
- GPT_MODEL_NAME, EXEC_SUMMARY_MODEL, GPT_TEMPERATURE
- SUMMARY_MODEL_NAME
- TAVILY_API_KEY (for live updates); SERPAPI_KEY (fallback)
"""

from __future__ import annotations

import os
import re
import csv
import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI

# -----------------------------------------------------------------------------
# Globals
# -----------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data"

client = OpenAI()


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def _as_int(x) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").lower().strip()
    return "de" if l.startswith("de") else "en"

def fix_encoding(text: str) -> str:
    return (text or "").replace("�", "-").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'")

def strip_code_fences(text: str) -> str:
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")

def ensure_html(text: str, lang: str = "de") -> str:
    """Render simple paragraphs if no HTML is present."""
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

def _strip_lists_and_numbers(text: str) -> str:
    """
    Remove list markers and most numeric clutter while keeping links intact.
    We avoid touching URLs or HTML attributes.
    """
    if not text:
        return text
    t = str(text)

    # Remove markdown list markers at line starts
    t = re.sub(r"(?m)^\s*[-*•]\s+", "", t)

    # Flatten simple <li>…</li> lists into sentences.
    def _flatten_li(m):
        inner = m.group(1).strip()
        # Replace trailing punctuation duplication later
        return " " + inner
    t = re.sub(r"(?is)<li[^>]*>(.*?)</li>", _flatten_li, t)
    t = re.sub(r"(?is)</?(ul|ol)[^>]*>", "", t)

    # Remove percentages and plain numbers not inside links.
    # Very conservative: only numbers surrounded by word boundaries.
    def repl_num(m):
        whole = m.group(0)
        # keep if looks like part of an URL query or path (contains http or href around is handled by regex)
        return ""

    # Skip inside anchor tags
    def _remove_numbers_outside_links(html: str) -> str:
        parts = re.split(r"(?is)(<a[^>]*>.*?</a>)", html)
        out = []
        for p in parts:
            if p.lower().startswith("<a"):
                out.append(p)  # unchanged
            else:
                out.append(re.sub(r"\b\d[\d\.,%]*\b", repl_num, p))
        return "".join(out)

    t = _remove_numbers_outside_links(t)

    # Collapse multiple spaces
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    return t

def _resolve_model(wanted: Optional[str]) -> str:
    fallbacks = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    w = (wanted or "").strip().lower()
    if not w or w.startswith("gpt-5"):
        return fallbacks[0]
    known = set(fallbacks) | {"gpt-4o-audio-preview", "gpt-4.1", "gpt-4.1-mini"}
    return w if w in known else fallbacks[0]

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
    for k, v in m.items():
        if k in raw:
            return v
    return "default"

def _norm_size(x: str) -> str:
    x = (x or "").lower()
    if x in {"solo","einzel","einzelunternehmer","freelancer","soloselbstständig","soloselbststaendig"}: return "solo"
    if x in {"team","small"}: return "team"
    if x in {"kmu","sme","mittelstand"}: return "kmu"
    return ""


# -----------------------------------------------------------------------------
# Live search (optional)
# -----------------------------------------------------------------------------

def _tavily_search(query: str, max_results: int = 5, days: Optional[int] = None) -> List[Dict[str, Any]]:
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
    base_de = f"Förderprogramm KI {region} {branche} {size}".strip()
    base_en = f"AI funding {region} {branche} {size}".strip()
    t_de = f"KI Tool {branche} {product} DSGVO".strip()
    t_en = f"GDPR-friendly AI tool {branche} {product}".strip()
    if lang.startswith("de"):
        queries = [q for q in [base_de, t_de, topic] if q]
        title = f"Neu seit {datetime.now():%B %Y}"
    else:
        queries = [q for q in [base_en, t_en, topic] if q]
        title = f"New since {datetime.now():%B %Y}"
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


# -----------------------------------------------------------------------------
# Content helpers (funding/tools & narratives)
# -----------------------------------------------------------------------------

def _load_csv_candidates(names: List[str]) -> str:
    for n in names:
        p = DATA_DIR / n
        if p.exists(): return str(p)
    for n in names:
        if Path(n).exists(): return n
    nested = BASE_DIR / "ki_backend" / "make-ki-backend-neu-main" / "data"
    for n in names:
        p = nested / n
        if p.exists(): return str(p)
    return ""

def _read_rows(path: str) -> List[Dict[str, str]]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k,v in r.items()} for r in rd]
    except Exception:
        return []

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
        if size and target:
            if size not in target and not (target=="kmu" and size in {"team","kmu"}):
                continue
        score = 0
        if region and reg == region: score -= 5
        if reg in {"bund","deutschland","de"}: score -= 1
        out.append({"name":name, "target":r.get("zielgruppe") or r.get("target") or "",
                    "region":r.get("region") or r.get("bundesland") or r.get("land") or "",
                    "grant":grant, "use_case":use_case, "link":link, "_score": score})
    out = sorted(out, key=lambda x: x.get("_score",0))[:max_items]
    for o in out:
        o.pop("_score", None)
    stand = ""
    try:
        ts = os.path.getmtime(path)
        stand = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        pass
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


# -----------------------------------------------------------------------------
# Jinja env
# -----------------------------------------------------------------------------

def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        enable_async=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


# -----------------------------------------------------------------------------
# Prompting helpers
# -----------------------------------------------------------------------------

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

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
    primary_path = f"prompts/{lang}/{chapter}.md"
    prompt_text = load_text(primary_path) if os.path.exists(primary_path) else f"[NO PROMPT FOUND for {chapter}/{lang}]"
    prompt = render_prompt(prompt_text, context)
    is_de = (lang == "de")
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
    return prompt + "\n\n---\n" + base_rules

def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float] = None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

def gpt_generate_section(data: dict, branche: str, chapter: str, lang="de") -> str:
    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    # minimal context for prompt rendering
    ctx = dict(data)
    ctx["branche"] = _extract_branche(data) if not data.get("branche") else data.get("branche")
    ctx["lang"] = lang
    prompt = build_masterprompt(chapter, ctx, lang)
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model
    section_text = _chat_complete(
        messages=[
            {
                "role": "system",
                "content": (
                    "Sie sind TÜV-zertifizierte:r KI-Manager:in, KI-Strategieberater:in sowie Datenschutz- und Fördermittel-Expert:in. "
                    "Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
                ) if lang == "de" else (
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

def gpt_generate_section_html(data: dict, branche: str, chapter: str, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    html = ensure_html(strip_code_fences(fix_encoding(html)), lang)
    return _strip_lists_and_numbers(html)


# -----------------------------------------------------------------------------
# Fallbacks
# -----------------------------------------------------------------------------

def fallback_vision(data: dict, lang: str = "de") -> str:
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

def compliance_fallback(lang: str = "de") -> str:
    if lang == "de":
        return (
            "<p>Dieser Bericht folgt den Grundsätzen von DSGVO, ePrivacy, Digital Services Act "
            "und EU‑AI‑Act. Personenbezogene Daten bleiben minimal, transparent und zweckgebunden. "
            "Für KI‑Anwendungen empfehlen wir klare Rollen und Verantwortlichkeiten, ein "
            "Risiko‑Register, Datenklassifizierung sowie ein schlankes Verfahren zur "
            "Folgenabschätzung bei höherem Risiko. Trainingsdaten, Modelle und Outputs werden "
            "dokumentiert, sensible Merkmale vermieden und menschliche Aufsicht gesichert.</p>"
        )
    else:
        return (
            "<p>This report adheres to GDPR, ePrivacy, the Digital Services Act and the EU AI Act. "
            "Personal data is kept minimal, transparent and purpose‑bound. For AI applications we "
            "recommend clear roles and accountability, a risk register, data classification and a "
            "lightweight impact assessment for higher‑risk use cases. Training data, models and "
            "outputs are documented, sensitive attributes avoided and human oversight ensured.</p>"
        )


# -----------------------------------------------------------------------------
# Section assemblers
# -----------------------------------------------------------------------------

def build_context(data: dict, branche: str, lang: str) -> dict:
    # Company size classification (narrative labels)
    def _get_employee_count(d: dict) -> Optional[int]:
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
                try: return int(m.group(1))
                except Exception: pass
        return None

    emp = _get_employee_count(data)
    if emp is None:
        cat = "team"
    elif emp <= 1:
        cat = "solo"
    elif emp <= 10:
        cat = "team"
    else:
        cat = "kmu"

    if lang == "de":
        size_label = "Solo-Unternehmer:in" if cat=="solo" else ("Team (2–10 Mitarbeitende)" if cat=="team" else "KMU (11+ Mitarbeitende)")
    else:
        size_label = "Solo entrepreneur" if cat=="solo" else ("Small team (2–10 people)" if cat=="team" else "SME (11+ people)")

    ctx = dict(data)
    ctx["lang"] = lang
    ctx["branche"] = branche
    ctx["company_size_category"] = cat
    ctx["company_size_label"] = size_label
    ctx["unternehmensgroesse"] = size_label
    return ctx

def generate_full_report(data: dict, lang: str = "de") -> Dict[str, str]:
    branche = _extract_branche(data)
    # Sections via LLM (narrative)
    sections = {}
    for chapter in ["executive_summary", "quick_wins", "risks", "recommendations", "roadmap", "vision", "compliance"]:
        try:
            sections[f"{chapter}_html"] = gpt_generate_section_html(data, branche, chapter, lang=lang)
        except Exception:
            # Fallbacks per chapter
            if chapter == "vision":
                sections[f"{chapter}_html"] = ensure_html(fallback_vision(data, lang), lang)
            elif chapter == "compliance":
                sections[f"{chapter}_html"] = ensure_html(compliance_fallback(lang), lang)
            else:
                # minimal neutral fallback
                sections[f"{chapter}_html"] = ensure_html("<p>Analysemodul nicht geladen – Fallback.</p>", lang)

    # Narrative funding/tools
    funding_html = build_funding_narrative(data, lang, max_items=5)
    tools_html = build_tools_narrative(data, branche, lang, max_items=6)
    sections["funding_html"] = _strip_lists_and_numbers(funding_html) if funding_html else ""
    sections["tools_html"] = _strip_lists_and_numbers(tools_html) if tools_html else ""

    # Also expose tables for template fallback paths (won't be used in Gold-Standard)
    try:
        sections["funding_table"] = build_funding_table(data, lang=lang, max_items=8)  # type: ignore[name-defined]
    except Exception:
        sections["funding_table"] = []
    try:
        sections["tools_table"] = build_tools_table(data, branche=branche, lang=lang, max_items=8)  # type: ignore[name-defined]
    except Exception:
        sections["tools_table"] = []

    # Live updates (optional)
    try:
        title, live_html = build_live_updates_html(data, lang=lang, max_results=5)
    except Exception:
        title, live_html = ("", "")
    sections["live_updates_title"] = title
    sections["live_updates_html"] = live_html

    # Final sanitisation
    for k, v in list(sections.items()):
        if isinstance(v, str):
            sections[k] = _strip_lists_and_numbers(ensure_html(strip_code_fences(fix_encoding(v)), lang))

    return sections


# -----------------------------------------------------------------------------
# Public entry point used by main.py
# -----------------------------------------------------------------------------

def analyze_briefing(body: Dict[str, Any], lang: str = "de") -> str:
    """
    Build all sections, construct ctx with meta, render Jinja template and
    return final HTML. This function never returns a dict; it always returns
    HTML so main.py can forward it to the PDF service.
    """
    lang = _norm_lang(body.get("lang") or body.get("language") or body.get("sprache") or lang)

    # The questionnaire may be nested under various keys; accept several.
    data = {}
    for key in ["data", "payload", "answers", "antworten", "questionnaire", "briefing", "body"]:
        if isinstance(body.get(key), dict):
            data = dict(body[key])
            break
    if not data and isinstance(body, dict):
        data = dict(body)

    branche = _extract_branche(data)
    ctx_base = build_context(data, branche, lang)
    sections = generate_full_report(data, lang=lang)

    # Build META for template (prevents 'meta is undefined').
    org = (data.get("unternehmen") or data.get("company") or data.get("firma") or "").strip()
    if not org:
        org = (data.get("name") or data.get("kontakt") or data.get("email") or "KI-Statusbericht").split("@")[0]
    subtitle = "Narrativer KI‑Report – DSGVO & EU‑AI‑Act‑ready" if lang=="de" else "Narrative AI Report – GDPR & EU AI Act ready"
    meta = {
        "title": f"KI-Statusbericht – {org}" if lang=="de" else f"AI Readiness Report – {org}",
        "subtitle": subtitle,
        "date": datetime.now().strftime("%d.%m.%Y") if lang=="de" else datetime.now().strftime("%Y-%m-%d"),
        "branche": branche,
        "size": ctx_base.get("company_size_label") or "—",
        "location": data.get("ort") or data.get("city") or data.get("bundesland") or data.get("state") or "—",
        "copyright": f"© {datetime.now().year} KI‑Sicherheit.jetzt – Wolf Hohl"
    }

    # Compose full Jinja context
    ctx = dict(ctx_base)
    ctx.update(sections)
    ctx["meta"] = meta

    # Ensure template exists
    env = _jinja_env()
    try:
        tmpl = env.get_template("pdf_template.html")
    except Exception as e:
        # As a hard fallback, wrap sections into a barebones HTML skeleton
        parts = [
            f"<h2>{meta['title']}</h2><p>{meta['subtitle']}</p>",
            sections.get("executive_summary_html",""),
            sections.get("quick_wins_html",""),
            sections.get("risks_html",""),
            sections.get("recommendations_html",""),
            sections.get("roadmap_html",""),
            sections.get("vision_html",""),
            sections.get("compliance_html",""),
            sections.get("funding_html",""),
            sections.get("tools_html",""),
        ]
        return "\n".join(parts)

    html = tmpl.render(**ctx, now=datetime.now)
    return html


# -----------------------------------------------------------------------------
# Zip auto-unpack (optional)
# -----------------------------------------------------------------------------

def ensure_unzipped(zip_name: str, dest_dir: str):
    try:
        z = BASE_DIR / zip_name
        d = BASE_DIR / dest_dir
        if z.exists() and not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(z), "r") as zf:
                zf.extractall(str(d))
    except Exception:
        pass

ensure_unzipped("prompts.zip", "prompts_unzip")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")
ensure_unzipped("aus-Data.zip", "data")

# End of file
