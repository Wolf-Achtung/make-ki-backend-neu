
# gpt_analyze.py — Gold-Standard (2025-09-20)
# Maintainer: Wolf Hohl · KI-Sicherheit.jetzt
# Purpose: Generate warm, narrative, DSGVO- & EU-AI-Act-ready HTML for the PDF service.
#
# Key guarantees in this version:
# - No empty reports: always fill meta + all sections (with robust fallbacks)
# - Strict HTML narrative (no lists/tables/numbers) enforced post-generation
# - Prompt lookup supports prompts/{lang}/* and prompts_unzip/{lang}/*
# - Live updates + Funding + Tools narratives are size/region aware
# - Works with existing templates/pdf_template.html expecting `meta` and *_html keys

import os
import re
import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

# External deps
from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI

client = OpenAI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

# --- Optional hook ------------------------------------------------------------
try:
    from postprocess_report import postprocess_report_dict  # type: ignore[attr-defined]
except Exception:
    postprocess_report_dict = None

# --- Utilities ----------------------------------------------------------------

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").strip().lower()
    return "de" if l.startswith("de") else "en"

def _as_int(x) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None

def ensure_unzipped(zip_name: str, dest_dir: str):
    try:
        z = Path(zip_name)
        d = Path(dest_dir)
        if z.exists() and not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(d)
    except Exception:
        pass

# Unpack known archives if present
ensure_unzipped(str(BASE_DIR / "prompts.zip"), str(BASE_DIR / "prompts_unzip"))
ensure_unzipped(str(BASE_DIR / "data.zip"), str(BASE_DIR / "data"))
ensure_unzipped(str(BASE_DIR / "branchenkontext.zip"), str(BASE_DIR / "branchenkontext"))

def fix_encoding(text: str) -> str:
    return (text or "").replace("�","-").replace("–","-").replace("“",'"').replace("”",'"').replace("’","'")

def strip_code_fences(text: str) -> str:
    if not text:
        return text
    t = text.replace("\r","")
    t = t.replace("```html","```").replace("```HTML","```")
    while "```" in t:
        t = t.replace("```","")
    return t.replace("`","")

def _strip_lists_and_numbers(text: str) -> str:
    """Remove list markers and digits/percent tokens to honour 'no numbers' rule."""
    if not text:
        return text
    t = str(text)

    # Remove list markers at line starts
    t = re.sub(r'(?m)^\s*[-*•]\s+', '', t)

    # Remove table like pipes
    t = re.sub(r'\|+', ' ', t)

    # Remove explicit enumerations like "1)", "2." at starts
    t = re.sub(r'(?m)^\s*\d+[\)\.\:]\s*', '', t)

    # Remove inline percentages and digit clusters
    t = re.sub(r'\d+\s*%','', t)
    t = re.sub(r'\b\d+([.,]\d+)?\b', '', t)

    # Collapse duplicate spaces
    t = re.sub(r'\s{2,}',' ', t).strip()
    return t

def ensure_html(text: str) -> str:
    """If no HTML tags are present, wrap paragraphs in <p> and headings in <h3> heuristically."""
    if not text:
        return ""
    t = text.strip()
    if "<" in t and ">" in t:
        return t
    # Convert simple markdown-ish input to <p> blocks
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    html = []
    for ln in lines:
        if ln.startswith("#"):
            level = min(3, len(ln) - len(ln.lstrip("#")))
            html.append(f"<h{level}>{ln[level:].strip()}</h{level}>")
        else:
            html.append(f"<p>{ln}</p>")
    return "\n".join(html)

def _sanitize_text(value: str) -> str:
    if not value:
        return value
    bad = ["\uFFFE", "\uFEFF", "\u200B", "\u00AD"]
    t = str(value)
    for ch in bad:
        t = t.replace(ch, "")
    # Neutral vendor wording
    replacements = {
        "GPT-Analyse": "LLM-gestützte Analyse",
        "GPT‑Analyse": "LLM-gestützte Analyse",
        "GPT-gestützt": "LLM-gestützte",
        "GPT‑gestützt": "LLM-gestützte",
        "GPT-Technologie": "LLM-gestützte Technologie",
        "GPT‑Technologie": "LLM-gestützte Technologie",
    }
    for old, new in replacements.items():
        t = t.replace(old, new)
    return t

def _extract_branche(d: Dict[str, Any]) -> str:
    raw = (str(d.get("branche") or d.get("industry") or d.get("sector") or "")).strip().lower()
    m = {
        "beratung":"beratung","consulting":"beratung","dienstleistung":"beratung","services":"beratung",
        "it":"it","software":"it","saas":"it","information technology":"it",
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

def _norm_size_label(data: Dict[str, Any], lang: str) -> Tuple[str, str]:
    """Return (category, label). Categories: solo|team|kmu"""
    # Try explicit employee count first
    for k in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
        n = _as_int(data.get(k))
        if n is not None:
            if n <= 1: cat = "solo"
            elif n <= 10: cat = "team"
            else: cat = "kmu"
            break
    else:
        sz = str(data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
        if any(s in sz for s in ["solo","einzel","self"]): cat = "solo"
        elif any(s in sz for s in ["team","2-","2 –","2–","10"]): cat = "team"
        elif "kmu" in sz or "11" in sz: cat = "kmu"
        else: cat = "team"
    if lang == "de":
        label = {"solo":"Solo-Unternehmer:in","team":"Team (2–10 Mitarbeitende)","kmu":"KMU (11+ Mitarbeitende)"}[cat]
    else:
        label = {"solo":"Solo entrepreneur","team":"Small team (2–10 people)","kmu":"SME (11+ people)"}[cat]
    return cat, label

# --- Prompt handling -----------------------------------------------------------

def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None

def _render_prompt_vars(template_text: str, context: dict) -> str:
    def repl_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)
    s = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", repl_join, template_text)
    def repl_simple(m):
        key = m.group(1); val = context.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", repl_simple, s)

def _load_prompt(lang: str, chapter: str) -> str:
    # Search order: prompts/{lang}/{chapter}.md -> prompts_unzip/{lang}/{chapter}.md
    for root in [BASE_DIR/"prompts", BASE_DIR/"prompts_unzip"]:
        if not root.exists():
            continue
        for ext in (".md",".txt"):
            p = root/lang/(chapter+ext)
            if p.exists():
                s = _read_text(p)
                if s:
                    return s
    return f"[NO PROMPT FOUND for {chapter}/{lang}]"

def _load_persona(lang: str) -> str:
    for root in [BASE_DIR/"prompts", BASE_DIR/"prompts_unzip"]:
        if not root.exists(): continue
        for name in ("_persona.md","persona.md","_style.md"):
            p = root/lang/name
            if p.exists():
                s = _read_text(p)
                if s:
                    return s
    return ""

def build_masterprompt(chapter: str, context: dict, lang: str) -> str:
    persona = _load_persona(lang)
    prompt_body = _load_prompt(lang, chapter)
    # Global style constraints (German/English)
    is_de = (lang == "de")
    base_rules = (
        "Gib die Antwort ausschließlich als gültiges HTML ohne <html>-Wrapper zurück. "
        "Verwende nur <h3> und <p>. Keine Listen, keine Tabellen, keine Aufzählungen. "
        "Formuliere 2–3 zusammenhängende Absätze in warmer, motivierender Sprache. "
        "Integriere Best‑Practice‑Beispiele als kurze Geschichten. Keine Zahlen/Prozentwerte."
        if is_de else
        "Return VALID HTML only (no <html> wrapper). Use only <h3> and <p>. "
        "Avoid lists and tables. Write 2–3 connected paragraphs in a warm, motivating tone. "
        "Integrate best‑practice examples as short stories. Do not include numbers or percentages."
    )
    merged = "\n\n".join([persona.strip(), prompt_body.strip(), "---\n"+base_rules]).strip()
    return _render_prompt_vars(merged, context)

def _chat_complete(messages: List[Dict[str, str]], model_name: Optional[str]) -> str:
    # Resolve model; avoid invalid choices
    wanted = model_name or os.getenv("GPT_MODEL_NAME", "gpt-5")
    if wanted.lower().startswith("gpt-5"):
        # This environment may not have GPT-5; fallback to safe defaults
        model = os.getenv("EXEC_MODEL_FALLBACK", "gpt-4o-mini")
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
        resp = client.chat.completions.create(model=model, temperature=temperature, messages=messages)
    else:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
        resp = client.chat.completions.create(model=wanted, temperature=temperature, messages=messages)
    return (resp.choices[0].message.content or "").strip()

def _ensure_narrative_html(text: str) -> str:
    t = strip_code_fences(fix_encoding(text or ""))
    t = _strip_lists_and_numbers(t)
    t = ensure_html(t)
    # Allow only <h3> and <p> tags; strip others
    t = re.sub(r'</?(?!h3|p)[a-zA-Z][^>]*>', '', t)
    return t

# --- Domain blocks -------------------------------------------------------------

def build_context(data: dict, branche: str, lang: str) -> dict:
    # Merge optional branch yaml
    ctx = dict(data or {})
    ctx["lang"] = lang
    cat, label = _norm_size_label(ctx, lang)
    ctx["company_size_category"] = cat
    ctx["company_size_label"] = label
    # Backwards-compatible aliases used in templates
    ctx["unternehmensgroesse"] = label
    ctx.setdefault("hauptleistung", ctx.get("main_service") or ctx.get("hauptprodukt") or "")
    ctx.setdefault("projektziel", ctx.get("ziel") or "")
    # Branch translation for English
    if lang != "de":
        tr = {
            "beratung":"consulting","bau":"construction","bildung":"education","finanzen":"finance","gesundheit":"healthcare",
            "handel":"trade","industrie":"industry","it":"IT","logistik":"logistics","marketing":"marketing","medien":"media","verwaltung":"public administration"
        }
        ctx["branche"] = tr.get(branche, branche)
    else:
        ctx["branche"] = branche
    return ctx

def gpt_generate_section_html(data: dict, branche: str, chapter: str, lang: str) -> str:
    system_de = "Sie sind TÜV-zertifizierte:r KI-Manager:in, KI-Strategieberater:in sowie Datenschutz- und Fördermittel-Expert:in. Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
    system_en = "You are a TÜV-certified AI manager and strategy consultant. Deliver precise, actionable, up-to-date, sector-relevant content as HTML."
    context = build_context(data, branche, lang)
    prompt = build_masterprompt(chapter, context, lang)
    text = _chat_complete(
        messages=[
            {"role":"system","content": system_de if lang=="de" else system_en},
            {"role":"user","content": prompt},
        ],
        model_name=os.getenv("EXEC_SUMMARY_MODEL" if chapter=="executive_summary" else "GPT_MODEL_NAME", os.getenv("GPT_MODEL_NAME","gpt-4o-mini"))
    )
    return _ensure_narrative_html(text)

def fallback_vision(data: dict, lang: str) -> str:
    if lang == "de":
        return _ensure_narrative_html("""
<h3>Vision</h3>
<p><b>Kühne Idee:</b> Ein KI‑Serviceportal für KMU bündelt Fragebögen, kompakte Auswertungen und praxiserprobte Arbeitsabläufe. So wird der Einstieg in KI greifbar und Vertrauen wächst Schritt für Schritt.</p>
<p>Als Startpunkt dient ein schlanker Prototyp mit persönlichem Feedback und unkomplizierter Terminvereinbarung. Daraus entsteht ein lebendiges Wissensnetz, das Erfahrungen sammelt und neue Dienstleistungen inspiriert – ohne Zahlenwüsten, mit klarem Blick auf Menschen und Wirkung.</p>
""")
    else:
        return _ensure_narrative_html("""
<h3>Vision</h3>
<p><b>Bold idea:</b> An AI service portal for SMEs brings together questionnaires, concise insights and proven workflows. It makes the first steps tangible and builds trust one conversation at a time.</p>
<p>Begin with a lean prototype that offers personal feedback and easy appointment booking. Over time it grows into a living knowledge network that captures experience and fuels new services – focused on people and outcomes rather than numbers.</p>
""")

def build_compliance_block(lang: str) -> str:
    if lang == "de":
        return _ensure_narrative_html("""
<h3>Compliance</h3>
<p>Die vorgeschlagenen Maßnahmen sind DSGVO‑konform gedacht: Datenminimierung, klare Zwecke und transparente Einwilligungen bleiben Leitplanken. Für KI‑Anwendungen gelten zusätzlich die Grundsätze der ePrivacy‑Richtlinie und die Sorgfaltspflichten des Digital Services Act.</p>
<p>Beim EU‑AI‑Act orientieren wir uns an Risikoklassen: Prozesse mit niedrigerem Risiko werden bevorzugt, hochriskante Vorhaben erfordern striktere Dokumentation, Mensch‑in‑der‑Schleife und belastbare Tests. So bleibt Innovation möglich – und Rechtssicherheit gewahrt.</p>
""")
    else:
        return _ensure_narrative_html("""
<h3>Compliance</h3>
<p>All measures are conceived to comply with GDPR: data minimisation, clear purposes and transparent consent. For AI use we also consider ePrivacy principles and the duties set out by the Digital Services Act.</p>
<p>Under the EU AI Act we align with risk classes: low‑risk processes first, while higher‑risk ideas require stronger documentation, human‑in‑the‑loop and robust testing. This keeps innovation moving while preserving legal certainty.</p>
""")

# --- Funding & Tools (narratives) ---------------------------------------------

def _csv_path(*names: str) -> Optional[Path]:
    # Try data/ first, then project root
    for n in names:
        p = BASE_DIR / "data" / n
        if p.exists():
            return p
    for n in names:
        p = BASE_DIR / n
        if p.exists():
            return p
    return None

def _load_csv(path: Path) -> List[Dict[str,str]]:
    import csv
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def _size_category(data: dict) -> str:
    cat, _ = _norm_size_label(data, "de")
    return cat

def build_funding_narrative(data: dict, lang: str) -> Tuple[str, str]:
    rows = []
    path = _csv_path("foerdermittel.csv","foerderprogramme.csv")
    if path:
        rows = _load_csv(path)
    # Basic filter by region and size (very permissive)
    region = (str(data.get("bundesland") or data.get("state") or "")).lower()
    alias = {"be":"berlin","by":"bayern","bw":"baden-württemberg","nrw":"nordrhein-westfalen"}
    region = alias.get(region, region)
    size = _size_category(data)
    picked: List[Dict[str,str]] = []
    for r in rows:
        name = r.get("Name") or r.get("name") or ""
        if not name: 
            continue
        rg = (r.get("Region") or r.get("region") or "").lower()
        zg = (r.get("Zielgruppe") or r.get("target") or "").lower()
        if region and (rg not in (region, "bund")):
            continue
        if size and zg and (size not in zg) and not (size in ("team","kmu") and "kmu" in zg):
            continue
        picked.append({
            "name": name,
            "use": r.get("Beschreibung") or r.get("einsatz") or r.get("zweck") or "",
            "grant": r.get("Fördersumme (€)") or r.get("foerderart") or r.get("quote") or "",
            "link": r.get("Link") or r.get("url") or ""
        })
        if len(picked) >= 6:
            break
    # Build narrative
    if not picked:
        return ("", "")
    if lang == "de":
        paras = []
        for p in picked:
            s = f"<p><b>{p['name']}</b> – passt zu Vorhaben wie {p['use']}. "
            if p['grant']:
                s += f"<i>Förderart/Volumen: {p['grant']}. </i>"
            if p['link']:
                s += f'<a href="{p["link"]}">Zum Programm</a>'
            s += "</p>"
            paras.append(s)
        stand = ""
        try:
            if path:
                ts = path.stat().st_mtime
                stand = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            pass
        return ("\n".join(paras), stand)
    else:
        paras = []
        for p in picked:
            s = f"<p><b>{p['name']}</b> – suited for initiatives such as {p['use']}. "
            if p['grant']:
                s += f"<i>Grant/volume: {p['grant']}. </i>"
            if p['link']:
                s += f'<a href="{p["link"]}">Open</a>'
            s += "</p>"
            paras.append(s)
        stand = ""
        try:
            if path:
                ts = path.stat().st_mtime
                stand = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            pass
        return ("\n".join(paras), stand)

def build_tools_narrative(data: dict, branche: str, lang: str) -> str:
    rows = []
    path = _csv_path("tools.csv","ki_tools.csv")
    if path:
        rows = _load_csv(path)
    size = _size_category(data)
    out = []
    for r in rows or []:
        name = r.get("Tool-Name") or r.get("Name") or r.get("Tool")
        if not name: 
            continue
        tags = (r.get("Branche-Slugs") or r.get("Tags") or r.get("Branche") or "").lower()
        if branche and tags and branche not in tags:
            continue
        row_size = (r.get("Unternehmensgröße") or r.get("Unternehmensgroesse") or "").lower()
        if row_size and row_size not in ("alle", size) and not (row_size=="kmu" and size in ("team","kmu")):
            continue
        usecase = r.get("Funktion/Zweck") or r.get("Einsatz") or r.get("Usecase") or ""
        price = r.get("Kosten") or r.get("Cost") or "n/a"
        link = r.get("Link/Website") or r.get("Link") or r.get("Website") or ""
        data_loc = r.get("Datenschutz") or r.get("Datensitz") or "n/a"
        if lang=="de":
            s = f"<p><b>{name}</b> – geeignet für {usecase}. Hosting/Datenschutz: {data_loc}; Preis: {price}. "
            if link: s += f'<a href="{link}">Zur Website</a>'
            s += "</p>"
        else:
            s = f"<p><b>{name}</b> – suitable for {usecase}. Hosting/data: {data_loc}; price: {price}. "
            if link: s += f'<a href="{link}">Website</a>'
            s += "</p>"
        out.append(s)
        if len(out) >= 8:
            break
    return "\n".join(out)

def build_live_updates_html(data: Dict[str, Any], lang: str = "de", max_results: int = 5) -> Tuple[str, str]:
    # Lightweight search via Tavily if API key exists, else return empty
    try:
        import httpx
    except Exception:
        return ("", "")
    key = os.getenv("TAVILY_API_KEY","").strip()
    if not key:
        return ("", "")
    query = ""
    branche = _extract_branche(data)
    region = str(data.get("bundesland") or data.get("state") or data.get("ort") or "").strip()
    if lang=="de":
        query = f"Förderprogramm KI {region} {branche}"
        title = f"Neu seit {datetime.now():%B %Y}"
    else:
        query = f"AI funding {region} {branche}"
        title = f"New since {datetime.now():%B %Y}"
    try:
        payload = {"api_key": key, "query": query, "max_results": max_results, "include_answer": False}
        with httpx.Client(timeout=10.0) as c:
            r = c.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
        items = []
        for it in data.get("results", [])[:max_results]:
            url = (it.get("url") or "").strip()
            if not url: 
                continue
            title_i = (it.get("title") or url)[:120]
            date = it.get("published_date") or ""
            snippet = (it.get("content") or "")[:220]
            li = f'<li><a href="{url}">{title_i}</a>'
            if date: li += f' <span style="color:#5B6B7C">({date})</span>'
            if snippet:
                li += f"<br><span style='color:#5B6B7C;font-size:12px'>{snippet}</span>"
            li += "</li>"
            items.append(li)
        html = "<ul>"+ "".join(items) + "</ul>" if items else ""
        return (title, html)
    except Exception:
        return ("", "")

# --- Main entrypoint -----------------------------------------------------------

def analyze_briefing(body: Any, lang: Optional[str] = None):
    """
    Main function called by main.py. Returns a fully rendered HTML string.
    - `body` may be a dict or a JSON string.
    - `lang` overrides or falls back to 'de'.
    """
    # Parse input
    if isinstance(body, str):
        try:
            data = json.loads(body)
        except Exception:
            data = {"raw": body}
    elif isinstance(body, dict):
        data = dict(body)
    else:
        data = {}

    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    branche = _extract_branche(data)

    # Build context for prompts
    context = build_context(data, branche, lang)

    # Generate sections (robust: try LLM, fallback to safe narrative)
    def _gen(chapter: str, fallback: Optional[str] = None) -> str:
        try:
            html = gpt_generate_section_html(data, branche, chapter, lang)
        except Exception:
            html = ""
        html = _ensure_narrative_html(html or "")
        if not html and fallback:
            html = _ensure_narrative_html(fallback)
        return html

    # Chapter content
    executive_summary_html = _gen("executive_summary", "<h3>Executive Summary</h3><p>Ihre Antworten skizzieren klare Prioritäten. Dieser Bericht fasst Chancen, Risiken und erste Schritte zusammen – ohne Zahlen, dafür mit konkreten, alltagstauglichen Empfehlungen.</p>")
    quick_wins_html        = _gen("quick_wins", "<h3>Schnelle Hebel</h3><p>Beginnen Sie mit kleinen, sichtbaren Verbesserungen im Tagesgeschäft: wiederkehrende Texte, Meeting-Notizen, einfache Automatisierungen. Das baut Vertrauen auf und schafft Zeit für die nächsten Schritte.</p>")
    risks_html             = _gen("risks", "<h3>Risiken</h3><p>Die größten Risiken entstehen selten durch Technik, sondern durch unklare Rollen, Datenquellen und Erwartungen. Wir empfehlen einen schlanken Freigabeprozess und klare Kriterien für Qualität und Sicherheit.</p>")
    recommendations_html   = _gen("recommendations", "<h3>Empfehlungen</h3><p>Fokussieren Sie sich auf einen Pilotprozess mit hoher Sichtbarkeit und geringer Komplexität. Binden Sie Datenschutz früh ein und dokumentieren Sie Annahmen, Tests und Lernerfolge in einem knappen Logbuch.</p>")
    roadmap_html           = _gen("roadmap", "<h3>Roadmap</h3><p>Starten Sie mit einem vierwöchigen Sprint: Auswahl Pilotprozess, Mini‑Prototyp, Feedback, Nachschärfen. Danach schrittweise verbreitern – erst Prozesse, dann Teams.</p>")

    vision_html = _gen("vision") or fallback_vision(data, lang)

    # Gamechanger: optional prompt, else transform vision into 'innovation' narrative
    gamechanger_html = _gen("gamechanger", "<h3>Innovation &amp; Gamechanger</h3><p>Die Idee gewinnt durch konsequentes Zusammenspiel von Beratung, Prototyping und sauberem Betrieb. Entscheidend ist die Nähe zum Alltag: echte Fragen, echte Daten, echte Wirkung.</p>")

    compliance_html = build_compliance_block(lang)

    funding_html, funding_stand = build_funding_narrative(data, lang)
    tools_html = build_tools_narrative(data, branche, lang)

    # Live updates (optional)
    news_title, news_html = build_live_updates_html(data, lang)

    # Build meta
    loc = str(data.get("ort") or data.get("city") or data.get("standort") or "").strip()
    size_label = context.get("company_size_label") or ""
    meta = {
        "title": "KI-Statusbericht" if lang=="de" else "AI Status Report",
        "subtitle": "Narrativer KI‑Report – DSGVO & EU‑AI‑Act‑ready" if lang=="de" else "Narrative AI report – GDPR & EU AI Act ready",
        "date": datetime.now().strftime("%d.%m.%Y") if lang=="de" else datetime.now().strftime("%Y-%m-%d"),
        "branche": context.get("branche","—"),
        "size": size_label or "—",
        "location": loc or "—",
    }

    # Assemble context for template (both sections{} and top-level *_html for compatibility)
    out: Dict[str, Any] = {
        "meta": meta,
        "executive_summary_html": executive_summary_html,
        "quick_wins_html": quick_wins_html,
        "risks_html": risks_html,
        "recommendations_html": recommendations_html,
        "roadmap_html": roadmap_html,
        "vision_html": vision_html,
        "gamechanger_html": gamechanger_html,
        "compliance_html": compliance_html,
        "funding_html": funding_html,
        "tools_html": tools_html,
        "news_title": news_title,
        "news_html": news_html,
        "funding_last_update": funding_stand or "",
        "lang": lang,
    }
    out["sections"] = {
        "executive_summary": executive_summary_html,
        "quick_wins": quick_wins_html,
        "risks": risks_html,
        "recommendations": recommendations_html,
        "roadmap": roadmap_html,
        "vision": vision_html,
        "gamechanger": gamechanger_html,
        "compliance": compliance_html,
        "funding": funding_html,
        "tools": tools_html,
        "news_title": news_title,
        "news": news_html,
    }

    # Optional post-processing hook
    try:
        if postprocess_report_dict:
            out = postprocess_report_dict(out) or out
    except Exception:
        pass

    # Render HTML via the template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html","xml"]),
        enable_async=False,
    )
    # Provide `now` in template for convenience
    env.globals.update(now=datetime.now)

    tpl_name = "pdf_template.html"
    tpl = env.get_template(tpl_name)
    html = tpl.render(**out)

    # Final sanitation: remove stray code fences and invisible chars
    html = strip_code_fences(_sanitize_text(html))
    return html
