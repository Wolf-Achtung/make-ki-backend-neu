
# gpt_analyze.py — Gold Standard bundle (2025-09-21)
from __future__ import annotations

import os, re, json, datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
TEMPLATES_DIR = BASE_DIR / "templates"
LANGS = {"de","en"}
DEFAULT_LANG = "de"
MIN_HTML_LEN = int(os.getenv("MIN_HTML_LEN","1000"))

CHAPTERS: List[str] = [
    "exec_summary",
    "quick_wins",
    "risks",
    "recommendations",
    "roadmap",
    "vision",
    "gamechanger",
    "compliance",
    "tools",
    "funding",
    "live",
    "trusted_check",
]

NUM_OK = {"roadmap_html","funding_html","tools_html","live_html"}

_CODEFENCE_RE = re.compile(r"```.*?```", flags=re.S)
_TAG_RE = re.compile(r"</?(script|style)[^>]*>", flags=re.I)
_LEADING_ENUM_RE = re.compile(r"(?m)^\s*(?:\d+[\.\)]|[-–•])\s+")
_LI_RE = re.compile(r"</?li[^>]*>", flags=re.I)
_OL_UL_RE = re.compile(r"</?(?:ol|ul)[^>]*>", flags=re.I)

def _strip_code_fences(text: str) -> str:
    if not text: return text
    text = _CODEFENCE_RE.sub("", text)
    return text.replace("```","")

def _strip_scripts_styles(text: str) -> str:
    return _TAG_RE.sub("", text or "")

def _normalize_lists_to_paragraphs(html: str) -> str:
    if not html: return html
    html = _LI_RE.sub("\n", html)
    html = _OL_UL_RE.sub("\n", html)
    html = _LEADING_ENUM_RE.sub("", html)
    html = re.sub(r"\n{3,}","\n\n", html)
    return html

def _strip_lists_and_numbers(html: str) -> str:
    if not html: return html
    html = _strip_code_fences(_strip_scripts_styles(html))
    html = _normalize_lists_to_paragraphs(html)
    return html

def _sanitize_text(html: str) -> str:
    if not html: return html
    html = _strip_scripts_styles(html)
    html = _strip_code_fences(html)
    return html.replace("&nbsp;"," ")

REGION_MAP = {
    "be":"berlin","bb":"brandenburg","bw":"baden-württemberg","by":"bayern",
    "hb":"bremen","hh":"hamburg","he":"hessen","mv":"mecklenburg-vorpommern",
    "ni":"niedersachsen","nw":"nordrhein-westfalen","nrw":"nordrhein-westfalen",
    "rp":"rheinland-pfalz","sl":"saarland","sn":"sachsen","st":"sachsen-anhalt",
    "sh":"schleswig-holstein","th":"thüringen",
}
def normalize_region(value: Optional[str]) -> str:
    if not value: return ""
    v = str(value).strip().lower()
    return REGION_MAP.get(v, v)

def _must_exist(p: Path) -> Path:
    if not p.exists():
        raise FileNotFoundError(f"Prompt fehlt: {p}")
    return p

def _load_text(p: Path) -> str:
    return _must_exist(p).read_text(encoding="utf-8")

def _read_prompt(chapter: str, lang: str) -> str:
    lang = lang if lang in LANGS else DEFAULT_LANG
    return _load_text(PROMPTS_DIR/lang/f"{chapter}.md")

def _read_optional_context(lang: str) -> str:
    parts: List[str] = []
    for name in ("persona.md","praxisbeispiel.md"):
        p = PROMPTS_DIR/lang/name
        if p.exists():
            parts.append(_load_text(p))
    return "\n\n".join(parts)

def _llm_complete(prompt: str, model: Optional[str]=None, temperature: float=0.35) -> str:
    provider = os.getenv("LLM_PROVIDER","openai").lower()
    if provider == "none":
        raise RuntimeError("LLM disabled")
    try:
        from openai import OpenAI
        client = OpenAI()
        mdl = model or os.getenv("OPENAI_MODEL","gpt-4o-mini")
        r = client.chat.completions.create(
            model=mdl,
            temperature=temperature,
            messages=[
                {"role":"system","content":"You write warm, compliant HTML paragraphs. Use <h3 class='sub'> for subheads. For tools/funding you may include a compact <table class='mini'>."},
                {"role":"user","content":prompt},
            ],
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

def build_masterprompt(chapter: str, ctx: Dict[str,Any], lang: str) -> str:
    base = _read_prompt(chapter, lang)
    extra_ctx = _read_optional_context(lang)
    rules_de = ("Narrative Absätze, per Sie, freundlich, optimistisch, keine Listen/Tabellen (außer Tools/Förderung). "
                "EU‑Hosting bevorzugen, konkrete Alltagstauglichkeit. Keine Prozentangaben.")
    rules_en = ("Narrative paragraphs, polite, optimistic, no lists/tables (except Tools/Funding). "
                "Prefer EU hosting, concrete everyday usefulness. No percentages.")
    rules = rules_de if lang=="de" else rules_en
    roadmap_rule = (" Verwenden Sie Zeitanker ohne Ziffern: „sofort“, „in den nächsten Wochen“, „innerhalb eines Jahres“.")
    roadmap_rule_en = (" Use time anchors without digits: “immediately”, “in the coming weeks”, “within a year”.")
    extras = roadmap_rule if (lang=="de" and chapter=="roadmap") else (roadmap_rule_en if (lang=="en" and chapter=="roadmap") else "")
    ctx_json = json.dumps(ctx, ensure_ascii=False)
    return "\n".join([base, "\n---\nKontext:\n", ctx_json, "\n---\nRegeln:\n", rules, extras, "\n---\nZusätzliche Hinweise:\n", extra_ctx])

def _chapter_key(ch: str) -> str: return f"{ch}_html"

def _generate(ch: str, ctx: Dict[str,Any], lang: str, temperature: float=0.35) -> str:
    prompt = build_masterprompt(ch, ctx, lang)
    return _llm_complete(prompt, model=os.getenv("ANALYZE_MODEL"), temperature=temperature)

def _postprocess(outputs: Dict[str,str]) -> Dict[str,str]:
    out: Dict[str,str] = {}
    for k, v in outputs.items():
        if not k.endswith("_html"):
            out[k]=v; continue
        out[k] = _sanitize_text(v) if k in NUM_OK else _strip_lists_and_numbers(v)
    return out

def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(enabled_extensions=("html",)))

def _tpl_name(lang: str) -> str:
    return "pdf_template_en.html" if lang=="en" else "pdf_template.html"

# ---- Fallback builders (chapter enforcement) ----
def _fallback_exec(lang: str, meta: Dict[str,Any]) -> str:
    if lang=="en":
        return ("<p>You can start with three safe, reversible steps, then move to a staged roadmap. "
                "Compliance is a way of working: roles, approvals, documentation and deletion with logs. "
                "Prefer EU‑hosted tools and keep human approval before sending.</p>")
    return ("<p>Sie starten mit drei sicheren, reversiblen Schritten und entwickeln daraus eine gestufte Roadmap. "
            "Compliance ist Arbeitsweise: Rollen, Freigaben, Dokumentation und Löschung mit Logs. "
            "Bevorzugen Sie EU‑gehostete Werkzeuge und behalten Sie die menschliche Freigabe vor dem Versand bei.</p>")

def _fallback_tools(lang: str) -> str:
    if lang=="en":
        return ("""<table class="mini"><thead><tr><th>Building block</th><th>Purpose</th><th>EU notes</th></tr></thead>
<tbody>
<tr><td>CRM / Contact hub</td><td>Unify customer threads, quotes & notes</td><td>EU region, export, roles & logs (e.g., weclapp, CentralStationCRM, Pipedrive EU)</td></tr>
<tr><td>Writing / research assistant</td><td>Drafts, summaries, ideation</td><td>EU options, data‑sparse mode, human approval (e.g., DeepL Write, Mistral, Aleph Alpha)</td></tr>
<tr><td>Small automation layer</td><td>Confirmations, file routing, templates</td><td>Rollback, pilot, logging (e.g., n8n self‑host EU, Make EU)</td></tr>
</tbody></table>
<p>Choose by principles rather than brand: EU region, exportability, roles/logs and reversibility.</p>""")
    return ("""<table class="mini"><thead><tr><th>Baustein</th><th>Wozu</th><th>EU‑Hinweise</th></tr></thead>
<tbody>
<tr><td>CRM / Kontakt‑Hub</td><td>Kundenfäden bündeln, Angebote & Notizen</td><td>EU‑Datenregion, Export, Rollen & Logs (z. B. weclapp, CentralStationCRM, Pipedrive EU)</td></tr>
<tr><td>Schreib‑/Recherche‑Assistent</td><td>Entwürfe, Zusammenfassungen, Ideation</td><td>EU‑Optionen, Datensparmodus, menschliche Freigabe (z. B. DeepL Write, Mistral, Aleph Alpha)</td></tr>
<tr><td>Kleine Automationsschicht</td><td>Bestätigungen, Datei‑Routing, Vorlagen</td><td>Rollback, Probelauf, Logging (z. B. n8n self‑host EU, Make EU)</td></tr>
</tbody></table>
<p>Entscheiden Sie nach Prinzipien statt Marke: EU‑Datenregion, Exportfähigkeit, Rollen/Logs, Rückbau.</p>""")

def _fallback_funding(lang: str) -> str:
    if lang=="en":
        return ("""<table class="mini"><thead><tr><th>Path</th><th>Suitable when</th><th>Notes</th></tr></thead>
<tbody>
<tr><td>Data groundwork</td><td>Put order into data/processes</td><td>EU hosting, light documentation, small pilot</td></tr>
<tr><td>Small pilots</td><td>Test 1–2 use cases</td><td>Pilot, logs, human approval</td></tr>
<tr><td>Upskilling</td><td>Make the team fit</td><td>Short modules, practice share, export of results</td></tr>
</tbody></table>
<p>Start with a funding‑ready mini‑path: goal → small steps → observable effect (no percentages).</p>""")
    return ("""<table class="mini"><thead><tr><th>Pfad</th><th>Geeignet wenn</th><th>Hinweise</th></tr></thead>
<tbody>
<tr><td>Daten‑Grundlagen</td><td>Stammdaten/Prozesse ordnen</td><td>EU‑Hosting, schlanke Doku, kleiner Pilot</td></tr>
<tr><td>Kleine Piloten</td><td>1–2 Use‑Cases testen</td><td>Probelauf, Logs, menschliche Freigabe</td></tr>
<tr><td>Qualifizierung</td><td>Team fit machen</td><td>Kurzmodule, Praxisanteil, Export der Ergebnisse</td></tr>
</tbody></table>
<p>Starten Sie mit einem förder‑tauglichen Mini‑Pfad: Ziel → kleine Schritte → sichtbare Wirkung (ohne Prozente).</p>""")

def _fallback_trusted(lang: str) -> str:
    if lang=="en":
        return ("""<p>The Trusted AI Check ensures privacy, traceability and reversibility.</p>
<table class="mini"><thead><tr><th>Criterion</th><th>How to recognise</th><th>Next step</th></tr></thead>
<tbody>
<tr><td>Purpose & benefit</td><td>Clear, limited goal</td><td>Write 2–3 sentences</td></tr>
<tr><td>Data & roles</td><td>Inputs known, roles assigned</td><td>Name owner & reviewer</td></tr>
<tr><td>Human approval</td><td>Four‑eyes before sending</td><td>Checklist + sign‑off</td></tr>
<tr><td>Logging & export</td><td>Events recorded, export possible</td><td>Enable logs, test export</td></tr>
<tr><td>Deletion</td><td>Retention set & enforced</td><td>Define & test deletion</td></tr>
<tr><td>Risk & mitigation</td><td>False outputs, data spill</td><td>Pilot, rollback, data minimisation</td></tr>
</tbody></table>
<p>This one‑page check builds trust and reduces adoption friction.</p>""")
    return ("""<p>Der Trusted KI‑Check stellt Datenschutz, Nachvollziehbarkeit und Rückbaubarkeit sicher.</p>
<table class="mini"><thead><tr><th>Kriterium</th><th>Woran erkennbar</th><th>Nächster Schritt</th></tr></thead>
<tbody>
<tr><td>Zweck & Nutzen</td><td>Klares, begrenztes Ziel</td><td>2–3 Sätze formulieren</td></tr>
<tr><td>Daten & Rollen</td><td>Eingaben bekannt, Rollen vergeben</td><td>Owner & Reviewer benennen</td></tr>
<tr><td>Menschliche Freigabe</td><td>Vier‑Augen vor Versand</td><td>Checkliste + Sign‑off</td></tr>
<tr><td>Logging & Export</td><td>Ereignisse protokolliert, Export möglich</td><td>Logs aktivieren, Export testen</td></tr>
<tr><td>Löschung</td><td>Aufbewahrung festgelegt & durchgesetzt</td><td>Löschkonzept definieren & testen</td></tr>
<tr><td>Risiko & Mitigation</td><td>Fehlausgaben, Datenabfluss</td><td>Probelauf, Rückbau, Datensparsamkeit</td></tr>
</tbody></table>
<p>Die Kurzprüfung schafft Vertrauen und senkt Einführungsbarrieren.</p>""")

def analyze(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> Dict[str,str]:
    lang = lang if lang in LANGS else DEFAULT_LANG
    d = dict(data or {})
    # Region wird im Formular verlangt; Normalisierung nur falls vorhanden
    if "bundesland" in d: d["bundesland"] = normalize_region(d.get("bundesland"))
    outputs: Dict[str,str] = {}
    for ch in CHAPTERS:
        try:
            outputs[_chapter_key(ch)] = _generate(ch, d, lang, temperature=temperature)
        except Exception:
            outputs[_chapter_key(ch)] = ""
    out = _postprocess(outputs)
    # Kapitel-Erzwingung / Fallbacks
    meta = {
        "title": (d.get("meta",{}) or {}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": d.get("branche") or "",
        "groesse": d.get("unternehmensgroesse") or d.get("size") or "",
        "standort": d.get("standort") or d.get("region") or d.get("bundesland") or "",
    }
    if not out.get("exec_summary_html"): out["exec_summary_html"] = _fallback_exec(lang, meta)
    if not out.get("tools_html"): out["tools_html"] = _fallback_tools(lang)
    if not out.get("funding_html"): out["funding_html"] = _fallback_funding(lang)
    if not out.get("trusted_check_html"): out["trusted_check_html"] = _fallback_trusted(lang)
    return out

def analyze_briefing(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> Dict[str,Any]:
    sections = analyze(data, lang=lang, temperature=temperature)
    meta = {
        "title": (data.get("meta",{}) or {}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": data.get("branche") or "",
        "groesse": data.get("unternehmensgroesse") or data.get("size") or "",
        "standort": data.get("standort") or data.get("region") or data.get("bundesland") or "",
    }
    ctx = {"meta": meta}
    ctx.update(sections)
    return ctx

def analyze_to_html(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> str:
    sections = analyze(data, lang=lang, temperature=temperature)
    env = _env()
    tpl = env.get_template(_tpl_name(lang))
    meta = {
        "title": (data.get("meta",{}) or {}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": data.get("branche") or "",
        "groesse": data.get("unternehmensgroesse") or data.get("size") or "",
        "standort": data.get("standort") or data.get("region") or data.get("bundesland") or "",
    }
    html = tpl.render(meta=meta, **sections)
    if not html or len(html) < MIN_HTML_LEN or "<h2" not in html:
        # Minimaler Fallback: render erneut nur mit vorhandenen Sektionen
        html = tpl.render(meta=meta, **sections)
    return html
