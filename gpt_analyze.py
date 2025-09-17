# gpt_analyze.py — Gold-Standard — VERSION_MARKER: v-gold-2025-09-17
# Kompatibel zum main.py-Loader: stellt analyze_briefing(payload, lang) bereit.

from __future__ import annotations

import os, re, json, base64, zipfile, mimetypes, math
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Jinja2 Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

# YAML (optional – robustes Fallback ohne Exception)
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

# HTTP-Client (für Live-Layer: Tavily/SerpAPI)
try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None

# OpenAI (optional – robustes Fallback)
try:
    from openai import OpenAI  # type: ignore
    _OPENAI = OpenAI()
except Exception:  # pragma: no cover
    _OPENAI = None

# —————————————————— Pfade/Verzeichnisse
BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"

def ensure_unzipped(zip_name: str, dest_dir: str) -> None:
    """Entpackt zip einmalig robust (silent)."""
    try:
        zf = BASE_DIR / zip_name
        dst = BASE_DIR / dest_dir
        if zf.exists() and not dst.exists():
            dst.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zf), "r") as arc:
                arc.extractall(str(dst))
    except Exception:
        pass

# Automatisch entpacken (Prompts/Kontexte)
ensure_unzipped("prompts.zip", "prompts_unzip")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")

# —————————————————— Umgebungsvariablen
PRIMARY_MODEL = os.getenv("GPT_MODEL_NAME") or os.getenv("SUMMARY_MODEL_NAME") or "gpt-4o-mini"
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL") or PRIMARY_MODEL
TEMPERATURE = float(os.getenv("GPT_TEMPERATURE") or "0.6")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
SERPAPI_KEY   = os.getenv("SERPAPI_KEY", "").strip()

DEFAULT_LANG = (os.getenv("DEFAULT_LANG") or "de").lower().strip()
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE") or "Europe/Berlin"

# —————————————————— kleine Helfer
def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or DEFAULT_LANG or "de").lower().strip()
    return "de" if l.startswith("de") else "en"

def _as_int(x) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None

def fix_encoding(text: str) -> str:
    return (text or "").replace("�", "-").replace("“", '"').replace("”", '"').replace("’", "'")

def strip_code_fences(text: str) -> str:
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")

def _sanitize_text(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = fix_encoding(s)
    # kein doppeltes Leerzeichen, weiche Normalisierung
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def ensure_html(text: str, lang: str = "de") -> str:
    """Wandelt reinen Fließtext in <p>…</p> Absätze; einfache Listen -> <ul>."""
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    html, in_ul = [], False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>"); in_ul = True
            html.append("<li>" + re.sub(r"^[-•*]\s+", "", ln).strip() + "</li>")
        else:
            if in_ul:
                html.append("</ul>"); in_ul = False
            html.append("<p>" + ln + "</p>")
    if in_ul: html.append("</ul>")
    return "\n".join(html)

def _strip_lists_and_numbers(html: str) -> str:
    """Gold‑Standard: zentrale Kapitel ohne harte Aufzählungen/Zahlen wirken lassen."""
    if not html:
        return html
    t = re.sub(r"<(ul|ol)[^>]*>.*?</\1>", "", html, flags=re.S|re.I)
    t = re.sub(r"\b\d{1,3}\s?(?:%|\/10|/10)\b", "deutlich", t)
    return t

def load_text(path: Path) -> Optional[str]:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return None

def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        if yaml:
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        # Minimaler Fallback (kein echtes YAML)
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

# —————————————————— Branchen-Erkennung & Normalisierung
_BRANCHE_MAP = {
    # deutsch
    "beratung":"beratung","dienstleistung":"beratung","dienstleistungen":"beratung","consulting":"beratung",
    "marketing":"marketing","werbung":"marketing","advertising":"marketing",
    "it":"it","software":"it","ict":"it","informationstechnologie":"it","technology":"it",
    "finanzen":"finanzen","insurance":"finanzen","bank":"finanzen","banking":"finanzen","versicherung":"finanzen",
    "handel":"handel","e-commerce":"handel","retail":"handel","einzelhandel":"handel",
    "bildung":"bildung","education":"bildung","schule":"bildung",
    "verwaltung":"verwaltung","public":"verwaltung","öffentliche hand":"verwaltung","public sector":"verwaltung",
    "gesundheit":"gesundheit","health":"gesundheit","care":"gesundheit","healthcare":"gesundheit",
    "bau":"bau","construction":"bau","architecture":"bau","architektur":"bau",
    "medien":"medien","kreativwirtschaft":"medien","creative":"medien","media":"medien",
    "industrie":"industrie","produktion":"industrie","manufacturing":"industrie",
    "logistik":"logistik","transport":"logistik","shipping":"logistik",
}

def _norm_industry_slug(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-zäöüß0-9\- ]+", " ", s)
    s = s.replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
    s = s.strip()
    if s in _BRANCHE_MAP:
        return _BRANCHE_MAP[s]
    # häufige Phrasen abfangen
    for k,v in _BRANCHE_MAP.items():
        if k in s:
            return v
    return "default"

def _extract_branche(d: Dict[str, Any]) -> str:
    raw = (str(d.get("branche") or d.get("industry") or d.get("sector") or "")).strip().lower()
    m = {
        "consulting":"beratung","dienstleistung":"beratung","beratung":"beratung",
        "it":"it","software":"it","information technology":"it",
        "marketing":"marketing","advertising":"marketing","werbung":"marketing",
        "construction":"bau","bau":"bau","architecture":"bau",
        "industry":"industrie","produktion":"industrie","manufacturing":"industrie",
        "retail":"handel","e-commerce":"handel","handel":"handel",
        "finance":"finanzen","insurance":"finanzen","finanzen":"finanzen",
        "health":"gesundheit","healthcare":"gesundheit","gesundheit":"gesundheit",
        "media":"medien","kreativwirtschaft":"medien","medien":"medien",
        "logistics":"logistik","transport":"logistik","logistik":"logistik",
        "public administration":"verwaltung","verwaltung":"verwaltung",
        "education":"bildung","bildung":"bildung",
    }
    # Default nicht mehr "beratung"
    return m.get(raw, "default")

# —————————————————— Branchenkontext + Firmenkontext
def build_context(data: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Lädt branchen- & unternehmensspezifischen Kontext (YAML), mit Default-Fallback."""
    branche = _extract_branche(data)
    ctx_dir = BASE_DIR / "branchenkontext"
    lang = _norm_lang(lang)

    # Pfad wie: branchenkontext/beratung.de.yaml  bzw. default.de.yaml
    cand = [ctx_dir / f"{branche}.{lang}.yaml", ctx_dir / f"default.{lang}.yaml"]
    out: Dict[str, Any] = {}
    for p in cand:
        out.update(load_yaml(p))

    # Unternehmenskontext (leicht normalisiert)
    out["company"] = {
        "name": data.get("company_name") or data.get("unternehmen") or data.get("firma") or data.get("name") or "",
        "hauptleistung": data.get("hauptleistung") or data.get("hauptprodukt") or data.get("main_product") or "",
        "bundesland": data.get("bundesland") or data.get("state") or "",
        "unternehmensgroesse": data.get("unternehmensgroesse") or data.get("company_size") or "",
        "zielgruppen": data.get("zielgruppen") or data.get("target_groups") or [],
    }
    out["branche_slug"] = branche
    return out

# —————————————————— Live-Layer: Tavily (bevorzugt) → SerpAPI → deaktiviert
def _search_live(query: str, lang: str = "de", max_results: int = 5) -> List[Dict[str, str]]:
    """Sucht kurze News/Links. Rückgabe: [{title,url,date,snippet}] | []."""
    results: List[Dict[str,str]] = []
    try:
        if TAVILY_API_KEY and httpx:
            # Tavily (offizielle API – einfache Suche)
            payload = {"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results}
            if lang == "de":
                payload["search_depth"] = "advanced"
                payload["include_domains"] = []  # frei
            to = httpx.Timeout(10.0, read=12.0)
            with httpx.Client(timeout=to) as c:
                r = c.post("https://api.tavily.com/search", json=payload)
                if r.status_code == 200:
                    j = r.json()
                    for item in j.get("results", []):
                        results.append({
                            "title": item.get("title") or "",
                            "url": item.get("url") or "",
                            "date": item.get("published_date") or "",
                            "snippet": item.get("content") or item.get("snippet") or ""
                        })
        elif SERPAPI_KEY and httpx:
            # SerpAPI (Google)
            params = {
                "engine": "google",
                "q": query,
                "hl": "de" if lang == "de" else "en",
                "num": max_results,
                "api_key": SERPAPI_KEY
            }
            to = httpx.Timeout(10.0, read=12.0)
            with httpx.Client(timeout=to) as c:
                r = c.get("https://serpapi.com/search.json", params=params)
                if r.status_code == 200:
                    j = r.json()
                    for item in (j.get("organic_results") or [])[:max_results]:
                        results.append({
                            "title": item.get("title") or "",
                            "url": item.get("link") or "",
                            "date": item.get("date") or "",
                            "snippet": item.get("snippet") or ""
                        })
    except Exception:
        pass
    return results[:max_results]

def build_live_box(data: Dict[str,Any], lang: str, topic: str) -> str:
    """Kleiner Live-Kasten „Neu seit {Monat}“ abgestimmt auf Branche/Hauptleistung."""
    branche = _extract_branche(data)
    haupt = (data.get("hauptleistung") or "").strip()
    month = datetime.now().strftime("%B %Y") if lang != "de" else datetime.now().strftime("%B %Y")
    if lang == "de":
        title = f"Neu seit {month}"
        q = f"{topic} {branche} {haupt} Deutschland aktuelle Förderprogramme KI Tools"
    else:
        title = f"New since {month}"
        q = f"{topic} {branche} {haupt} Germany funding AI tools latest"
    hits = _search_live(q, lang=lang, max_results=5)
    if not hits:
        return ""
    lis = []
    for h in hits:
        date = f"<span class='date'>{h.get('date','')}</span>" if h.get("date") else ""
        lis.append(f"<li><b>{_sanitize_text(h.get('title',''))}</b> – {date}<br><a href='{h.get('url','')}'>{h.get('url','')}</a><br>{_sanitize_text(h.get('snippet',''))}</li>")
    return f"<aside class='live-box'><h3>{title}</h3><ul>" + "\n".join(lis) + "</ul></aside>"

# —————————————————— Prompts (eingebaute Defaults)
def _sys_prompt(lang: str) -> str:
    if lang == "de":
        return ("Du bist ein einfühlsamer, präziser KI‑Analyst. "
                "Du schreibst in warmem, professionellem Ton, ohne Aufzählungen und ohne Prozentzahlen. "
                "Beziehe DSGVO, ePrivacy, DSA und EU‑AI‑Act ein.")
    return ("You are a precise, empathetic AI analyst. "
            "Write in a warm, professional tone. Avoid bullet lists and percentages. "
            "Include GDPR, ePrivacy, DSA and the EU AI Act where relevant.")

def _build_user_facts(data: Dict[str,Any], ctx: Dict[str,Any], lang: str) -> str:
    branche = ctx.get("branche_slug") or _extract_branche(data)
    comp = ctx.get("company", {})
    size = (comp.get("unternehmensgroesse") or "").strip() or (data.get("unternehmensgroesse") or "")
    haupt = comp.get("hauptleistung") or ""
    if lang == "de":
        return (f"Branche: {branche}; Hauptleistung: {haupt}; Größe: {size}; "
                f"Bundesland: {comp.get('bundesland','')}.")
    return (f"Industry: {branche}; Core service: {haupt}; Size: {size}; "
            f"State: {comp.get('bundesland','')}.")

# --- Model resolver (robust against invalid model names) ---
def _resolve_model(wanted: Optional[str]) -> str:
    # Order of preference
    fallbacks = [
        "gpt-4o-mini",  # fast & günstig
        "gpt-4o",       # hochwertig
        "gpt-3.5-turbo"
    ]
    w = (wanted or "").strip()
    # Sanitise common placeholders
    if not w or w.lower().startswith("gpt-5"):
        for m in fallbacks:
            return m
    # If user provided a known-good string, use it
    known = { "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo" }
    if w in known:
        return w
    # Fallback chain
    return fallbacks[0]

# —————————————————— OpenAI Wrapper
def _chat_complete(messages: List[Dict[str,str]], lang: str, model: Optional[str] = None,
                   temperature: float = TEMPERATURE, max_tokens: int = 1300) -> str:
    mdl = _resolve_model(model or os.getenv("GPT_MODEL_NAME"))
    try:
        if not _OPENAI:
            return ""
        resp = _OPENAI.chat.completions.create(
            model=mdl,
            temperature=temperature,
            messages=messages,
            max_tokens=max_tokens,
        )
        return strip_code_fences((resp.choices[0].message.content or "").strip())
    except Exception as e:
        # One retry with a safer fallback if we hit 400 or invalid_request
        try:
            safe = _resolve_model("gpt-4o")
            if safe != mdl:
                resp = _OPENAI.chat.completions.create(
                    model=safe, temperature=temperature, messages=messages, max_tokens=max_tokens
                )
                return strip_code_fences((resp.choices[0].message.content or "").strip())
        except Exception:
            pass
        return ""


def gpt_generate_section(topic: str, data: Dict[str,Any], ctx: Dict[str,Any], lang: str,
                         model: Optional[str] = None, temperature: float = TEMPERATURE,
                         add_facts: bool = True) -> str:
    sys_msg = _sys_prompt(lang)
    facts = _build_user_facts(data, ctx, lang) if add_facts else ""
    if lang == "de":
        ask = {
            "exec": "Schreibe eine herzliche, klare Executive Summary (1–2 Absätze).",
            "quickwins": "Formuliere drei sofort umsetzbare Quick Wins (als Fließtext).",
            "risks": "Beschreibe die wichtigsten Risiken und wie sie mitigiert werden (Fließtext).",
            "recs": "Gib priorisierte Empfehlungen (Fließtext, ohne Bulletpoints).",
            "roadmap": "Skizziere eine 3‑Phasen‑Roadmap mit Meilensteinen (Fließtext).",
            "vision": "Formuliere eine professionelle Vision für die Branche & Hauptleistung.",
            "compliance": "Gib Compliance‑Hinweise zu DSGVO, ePrivacy, DSA, EU‑AI‑Act (Fließtext).",
            "tools": "Nenne geeignete KI‑Tools (branchen-/größenspezifisch) in erzählender Form.",
            "funding": "Beschreibe passende Förderprogramme (branchen-/bundeslandspezifisch)."
        }.get(topic, topic)
    else:
        ask = {
            "exec": "Write a warm, clear executive summary (1–2 paragraphs).",
            "quickwins": "Describe three quick wins as narrative paragraphs.",
            "risks": "Explain key risks and how to mitigate them (paragraphs).",
            "recs": "Provide prioritized recommendations (narrative, no bullet points).",
            "roadmap": "Sketch a 3‑phase roadmap with milestones (narrative).",
            "vision": "Draft a professional vision for this industry and core service.",
            "compliance": "Provide compliance guidance re GDPR, ePrivacy, DSA, EU AI Act (narrative).",
            "tools": "Recommend suitable AI tools (industry/size‑specific) as prose.",
            "funding": "Describe relevant funding schemes (industry/state‑specific)."
        }.get(topic, topic)

    messages = [{"role":"system","content":sys_msg},
                {"role":"user","content":facts + "\n\n" + ask}]
    out = _chat_complete(messages, lang=lang, model=model)
    return ensure_html(out or "", lang)
# —————————————————— Fallbacks für wichtige Kapitel
def _fallback_exec(lang: str) -> str:
    return ensure_html("Ihr Unternehmen steht an einem guten Ausgangspunkt. "
                       "Der Report fasst Chancen, Risiken und konkrete nächste Schritte zusammen."
                       if lang == "de"
                       else "You are at a promising starting point. This report outlines opportunities, risks and next steps.",
                       lang)

def _fallback_compliance(lang: str) -> str:
    if lang == "de":
        return ensure_html(
            "Beachten Sie Grundsätze wie Privacy‑by‑Design, Datensparsamkeit, Auswahl geeigneter Auftragsverarbeiter, "
            "Datenfluss‑Dokumentation, Löschkonzepte, Betroffenenrechte sowie menschliche Letztentscheidung bei kritischen Vorgängen. "
            "Der EU‑AI‑Act erfordert je nach Risikoklasse u. a. Transparenz, Daten‑Governance, Protokollierung und Monitoring.",
            lang)
    return ensure_html(
        "Apply privacy‑by‑design/minimisation, document data flows, choose processors carefully, "
        "provide deletion concepts and data subject rights. Under the EU AI Act, depending on risk level, "
        "ensure transparency, data governance, logging and monitoring with human oversight.", lang)

# —————————————————— Inhaltsverzeichnis (leicht dynamisch)
def _toc_from_report(parts: Dict[str, Any], lang: str) -> str:
    labels = {
        "de": {
            "exec_summary_html":"Zusammenfassung",
            "quick_wins_html":"Quick Wins",
            "risks_html":"Risiken",
            "recommendations_html":"Empfehlungen",
            "roadmap_html":"Roadmap",
            "foerderprogramme_html":"Förderprogramme",
            "tools_html":"KI‑Tools",
            "sections_html":"Praxis",
            "compliance_html":"Compliance"
        },
        "en": {
            "exec_summary_html":"Executive summary",
            "quick_wins_html":"Quick wins",
            "risks_html":"Risks",
            "recommendations_html":"Recommendations",
            "roadmap_html":"Roadmap",
            "foerderprogramme_html":"Funding",
            "tools_html":"AI tools",
            "sections_html":"Case",
            "compliance_html":"Compliance"
        }
    }["de" if lang=="de" else "en"]
    order = ["exec_summary_html","quick_wins_html","risks_html","recommendations_html",
             "roadmap_html","foerderprogramme_html","tools_html","sections_html","compliance_html"]
    items = []
    for k in order:
        if parts.get(k):
            items.append(f"<li>{labels[k]}</li>")
    return "<ul class='toc'>" + "\n".join(items) + "</ul>" if items else ""

# —————————————————— Jinja Umgebung & Templateauswahl
def _jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"])
    )
    env.globals.update({"now": datetime.now})
    return env

def _pick_template(lang: str) -> str:
    return "pdf_template.html" if lang == "de" else "pdf_template_en.html"

# —————————————————— Hauptzusammenbau
def generate_full_report(data: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    lang = _norm_lang(lang)
    ctx = build_context(data, lang)

    # — Kernkapitel (mit LLM, robustem Fallback)
    exec_html = gpt_generate_section("exec", data, ctx, lang, model=EXEC_SUMMARY_MODEL) or _fallback_exec(lang)
    quick_html = gpt_generate_section("quickwins", data, ctx, lang)  # darf später ggf. zu <ul> werden
    risks_html = gpt_generate_section("risks", data, ctx, lang)
    recs_html  = gpt_generate_section("recs", data, ctx, lang)
    road_html  = gpt_generate_section("roadmap", data, ctx, lang)
    visn_html  = gpt_generate_section("vision", data, ctx, lang)
    comp_html  = gpt_generate_section("compliance", data, ctx, lang) or _fallback_compliance(lang)

    # Tools & Förderprogramme (narrativ) + Live-Box
    tools_html = gpt_generate_section("tools", data, ctx, lang)
    fund_html  = gpt_generate_section("funding", data, ctx, lang)
    live_box_tools  = build_live_box(data, lang, topic="KI‑Tools" if lang=="de" else "AI tools")
    live_box_funds  = build_live_box(data, lang, topic="Förderprogramme" if lang=="de" else "funding programs")

    # Kapitel feinsäubern (Gold-Standard)
    for key, value in {
        "exec_html": exec_html, "quick_html": quick_html, "risks_html": risks_html,
        "recs_html": recs_html, "road_html": road_html, "visn_html": visn_html
    }.items():
        if value:
            locals()[key] = _strip_lists_and_numbers(value)

    # Report-Objekt
    out: Dict[str, Any] = {
        "version": "v-gold-2025-09-17",
        "lang": lang,
        "branche": ctx.get("branche_slug") or _extract_branche(data),
        "company_name": ctx.get("company", {}).get("name",""),
        "hauptleistung": ctx.get("company", {}).get("hauptleistung",""),

        "exec_summary_html": exec_html,
        "quick_wins_html": quick_html,
        "risks_html": risks_html,
        "recommendations_html": recs_html,
        "roadmap_html": road_html,
        "vision_html": visn_html,
        "compliance_html": comp_html,

        "tools_html": tools_html + (live_box_tools or ""),
        "foerderprogramme_html": fund_html + (live_box_funds or ""),

        "sections_html": "",
        "toc_html": _toc_from_report({
            "exec_summary_html": exec_html,
            "quick_wins_html": quick_html,
            "risks_html": risks_html,
            "recommendations_html": recs_html,
            "roadmap_html": road_html,
            "foerderprogramme_html": fund_html,
            "tools_html": tools_html,
            "sections_html": "",
            "compliance_html": comp_html
        }, lang)
    }

    # Sanft normalisieren
    for k,v in list(out.items()):
        if isinstance(v, str):
            out[k] = _sanitize_text(v)

    return out
def generate_preface(lang: str = "de") -> str:
    if lang == "de":
        return ("<p>Dieses Dokument fasst die Ergebnisse Ihres <b>KI‑Status‑Reports</b> zusammen "
                "und bietet individuelle Empfehlungen für die nächsten Schritte. Es basiert auf Ihren Angaben und "
                "berücksichtigt aktuelle gesetzliche Vorgaben, Fördermöglichkeiten und technologische Entwicklungen.</p>")
    return ("<p>This document summarises your <b>AI readiness report</b> and provides tailored next steps. "
            "It is based on your input and considers legal requirements, funding options and current AI developments.</p>")

def _footer_text(lang: str) -> str:
    year = datetime.now().year
    if lang == "de":
        return (f"TÜV‑zertifiziertes KI‑Management © {year}: Wolf Hohl · "
                f"E‑Mail: kontakt@ki-sicherheit.jetzt · DSGVO‑ & EU‑AI‑Act‑konform · "
                f"Alle Angaben ohne Gewähr; keine Rechtsberatung.")
    return (f"TÜV‑certified AI Management © {year}: Wolf Hohl · "
            f"Email: kontakt@ki-sicherheit.jetzt · GDPR & EU‑AI‑Act compliant · "
            f"No legal advice.")

def _company_size_badge(data: Dict[str,Any]) -> str:
    """Kleines Label für die Templates (solo/team/kmu)."""
    sz = (data.get("unternehmensgroesse") or "").strip().lower()
    if any(x in sz for x in ["solo","1"]):
        return "solo"
    if any(x in sz for x in ["2–10","2-10","team"]):
        return "team"
    if any(x in sz for x in ["11–100","kmu","sme","11-100"]):
        return "kmu"
    return "n/a"

def render_with_template(report: Dict[str,Any], lang: str) -> str:
    env = _jinja_env()
    tmpl = env.get_template(_pick_template(lang))

    # Metadaten für Template
    meta = {
        "title": "KI‑Status‑Report" if lang=="de" else "AI Readiness Report",
        "preface_html": generate_preface(lang),
        "footer_text": _footer_text(lang),
        "company_size_badge": _company_size_badge(report),
        "branche": report.get("branche",""),
        "company_name": report.get("company_name",""),
        "hauptleistung": report.get("hauptleistung",""),
        "toc_html": report.get("toc_html","")
    }

    html = tmpl.render(**meta, **report)
    html = strip_code_fences(html or "")
    return html

# —————————————————— Öffentlicher Entry-Point (für main.py)
def analyze_briefing(payload: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Baut den Report (inkl. Live‑Kästen) und rendert HTML via Jinja.
    Rückgabe ist ein Dict mit Schlüssel 'html' (für main.py) plus Rohdaten.
    """
    lang = _norm_lang(lang or payload.get("lang") or payload.get("language") or payload.get("sprache"))
    report = generate_full_report(payload, lang=lang)

    # HTML rendern
    try:
        html = render_with_template(report, lang)
        # Sicherstellen, dass keine unerledigten Jinja‑Marker enthalten sind (Härtung wie in main.py)
        if ("{{" in html) or ("{%" in html):
            # Sollte beim offiziellen Template nicht passieren; dennoch abfangen.
            html = html.replace("{{", "").replace("}}", "").replace("{%", "").replace("%}", "")
    except Exception:
        # Minimal‑Fallback – entspricht main.py‑Fallback
        head = f"<h1>{'KI‑Status‑Report' if lang=='de' else 'AI Readiness Report'}</h1>"
        html = head + report.get("exec_summary_html","")

    # Rückgabe: fertiges HTML + Daten (damit pdf‑service optionale Metadaten hätte)
    out = dict(report)
    out["html"] = html
    return out
# Optional: lokaler Schnelltest
if __name__ == "__main__":  # pragma: no cover
    demo = {
        "lang": "de",
        "branche": "Beratung",
        "unternehmensgroesse": "kmu",
        "bundesland": "he",
        "hauptleistung": "Strategie- und Markenberatung für KMU",
        "zielgruppen": ["kmu","b2b"]
    }
    r = analyze_briefing(demo, lang="de")
    Path("out_demo.html").write_text(r.get("html",""), encoding="utf-8")
    print("Demo-HTML → out_demo.html")
