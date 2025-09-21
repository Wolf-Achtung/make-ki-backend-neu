# gpt_analyze.py — Gold Standard 2025-09-21
# Killer-Fixes 1–6 implementiert.
# - Selektive Sanitisierung (NUM_OK)
# - Nur prompts/{de|en}/… (keine prompts_unzip)
# - Roadmap-Zeitanker ohne Ziffern
# - Mindest-HTML-Fallback
# - Region-Mapping für Förder-Fallbacks
# - Quick-Wins: liefert "Sichere Sofortschritte"/"Safe First Steps" (Box-ready)
from __future__ import annotations

import os, re, json, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

# -----------------------------------------------------------------------------
# Pfade & Konstanten
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
TEMPLATES_DIR = BASE_DIR / "templates"

LANGS = {"de", "en"}
DEFAULT_LANG = "de"
MIN_HTML_LEN = int(os.getenv("MIN_HTML_LEN", "1000"))

# Kapitel-Namen -> Keys im Output-Objekt (…_html)
CHAPTERS: List[str] = [
    "exec_summary",     # Management-Zusammenfassung (optional)
    "quick_wins",       # Sichere Sofortschritte (Box)
    "risks",            # Risiken
    "recommendations",  # Empfehlungen
    "roadmap",          # Roadmap (zeitlich)
    "vision",           # Vision
    "gamechanger",      # Gamechanger (optional, kann mit Vision verschmelzen)
    "compliance",       # DSGVO/ePrivacy/DSA/EU-AI-Act
    "funding",          # Förderprogramme
    "tools",            # Tools (EU-Optionen)
    "live",             # Live-Updates (News/Programme)
]

# Kapitel, in denen Zahlen/Listen EXPLIZIT erlaubt sind (Fix 1)
NUM_OK = {"roadmap_html", "funding_html", "tools_html", "live_html"}

# -----------------------------------------------------------------------------
# Utilities: Sanitisierung & Textaufbereitung
# -----------------------------------------------------------------------------
_CODEFENCE_RE = re.compile(r"```.*?```", flags=re.S)
_TAG_RE = re.compile(r"</?(script|style)[^>]*>", flags=re.I)

_LEADING_ENUM_RE = re.compile(r"(?m)^\s*(?:\d+[\.\)]|[-–•])\s+")
# Ersetzt <li>…</li> in Fließtext, ohne Zahlen zu entfernen
_LI_RE = re.compile(r"</?li[^>]*>", flags=re.I)
_OL_UL_RE = re.compile(r"</?(?:ol|ul)[^>]*>", flags=re.I)

def _strip_code_fences(text: str) -> str:
    if not text:
        return text
    text = _CODEFENCE_RE.sub("", text)
    return text.replace("```", "")

def _strip_scripts_styles(text: str) -> str:
    return _TAG_RE.sub("", text or "")

def _normalize_lists_to_paragraphs(html: str) -> str:
    if not html:
        return html
    # LI zu Absätzen
    html = _LI_RE.sub("\n", html)
    html = _OL_UL_RE.sub("\n", html)
    # führende Aufzählungen am Zeilenanfang entfernen
    html = _LEADING_ENUM_RE.sub("", html)
    # mehrfaches Newline straffen
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html

def _strip_lists_and_numbers(html: str) -> str:
    """
    Historisch: entfernen von Listen & 'nackten' Aufzählungsnummern.
    Überarbeitet: keine globale Ziffern-Löschung mehr (Fix 1) – nur Listenstruktur raus.
    """
    if not html:
        return html
    html = _strip_code_fences(_strip_scripts_styles(html))
    html = _normalize_lists_to_paragraphs(html)
    return html

def _sanitize_text(html: str) -> str:
    if not html:
        return html
    html = _strip_scripts_styles(html)
    html = _strip_code_fences(html)
    # einfache HTML-Sauberkeit
    html = html.replace("&nbsp;", " ")
    return html

# -----------------------------------------------------------------------------
# Region-Normalisierung für Förder-Fallbacks (Fix 6)
# -----------------------------------------------------------------------------
REGION_MAP = {
    "be": "berlin",
    "bb": "brandenburg",
    "bw": "baden-württemberg",
    "by": "bayern",
    "hb": "bremen",
    "hh": "hamburg",
    "he": "hessen",
    "mv": "mecklenburg-vorpommern",
    "ni": "niedersachsen",
    "nw": "nordrhein-westfalen",
    "nrw": "nordrhein-westfalen",
    "rp": "rheinland-pfalz",
    "sl": "saarland",
    "sn": "sachsen",
    "st": "sachsen-anhalt",
    "sh": "schleswig-holstein",
    "th": "thüringen",
}
def normalize_region(value: Optional[str]) -> str:
    if not value:
        return ""
    v = str(value).strip().lower()
    return REGION_MAP.get(v, v)

# -----------------------------------------------------------------------------
# Prompts laden – nur aus prompts/{de|en}/… (Fix 2)
# -----------------------------------------------------------------------------
def _path_must_exist(p: Path) -> Path:
    if not p.exists():
        raise FileNotFoundError(f"Prompt/Template nicht gefunden: {p}")
    return p

def _load_text(p: Path) -> str:
    return _path_must_exist(p).read_text(encoding="utf-8")

def _read_prompt(chapter: str, lang: str) -> str:
    """Erzwingt Ein-Quellen-Politik: NUR prompts/{lang}/{chapter}.md"""
    if lang not in LANGS:
        lang = DEFAULT_LANG
    pp = PROMPTS_DIR / lang / f"{chapter}.md"
    return _load_text(pp)

def _read_optional_context(lang: str) -> str:
    """Persona, Praxisbeispiel, Förder-/Tools-Kontext optional anreichern (Ein-Quelle)."""
    parts: List[str] = []
    for name in ("persona.md", "praxisbeispiel.md", "foerderprogramme.md", "tools.md"):
        p = PROMPTS_DIR / lang / name
        if p.exists():
            parts.append(_load_text(p))
    return "\n\n".join(parts)

# -----------------------------------------------------------------------------
# LLM-Aufruf (neutral, damit bestehende Provider weiterhin funktionieren)
# -----------------------------------------------------------------------------
def _llm_complete(prompt: str, model: Optional[str] = None, temperature: float = 0.3) -> str:
    """
    Minimaler Provider: OpenAI ChatCompletions falls verfügbar, sonst RuntimeError.
    Bestehende Deployments können diese Funktion überschreiben/monkeypatchen.
    """
    # Externer Provider via ENV?
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "none":
        raise RuntimeError("LLM disabled via LLM_PROVIDER=none")

    try:
        from openai import OpenAI
        client = OpenAI()
        mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=mdl,
            temperature=temperature,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that writes clean HTML paragraphs."},
                {"role": "user", "content": prompt},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

# -----------------------------------------------------------------------------
# Prompt-Bau – inkl. Roadmap-Regel ohne Ziffern (Fix 3)
# -----------------------------------------------------------------------------
def build_masterprompt(chapter: str, ctx: Dict[str, Any], lang: str) -> str:
    """
    Kombiniert Kapitel-Prompt + Basisregeln + optionale Kontexte.
    Erzwingt "per Sie", narrativ, ohne Buzzwords; Roadmap: Zeitanker ohne Ziffern.
    """
    base = _read_prompt(chapter, lang)
    extra_ctx = _read_optional_context(lang)

    base_rules_de = (
        "Schreiben Sie narrativ in Absätzen (keine Listen/Tabellen), freundlich, per Sie, "
        "optimistisch und professionell. Vermeiden Sie Buzzwords. "
        "Bevorzugen Sie EU‑Hosting‑Optionen. Adressieren Sie DSGVO, ePrivacy, DSA und den EU‑AI‑Act pragmatisch."
    )
    base_rules_en = (
        "Write in warm narrative paragraphs (no lists/tables), politely addressing the reader, "
        "optimistic and professional. Avoid buzzwords. Prefer EU‑hosted options. "
        "Address GDPR, ePrivacy, DSA and the EU AI Act pragmatically."
    )
    base_rules = base_rules_de if lang == "de" else base_rules_en

    roadmap_rule_de = (" Verwenden Sie Zeitanker **ohne Ziffern**: "
                       "„sofort“, „in den nächsten Wochen“, „innerhalb eines Jahres“.")
    roadmap_rule_en = (" Use time anchors **without digits**: "
                       "“immediately”, “in the coming weeks”, “within a year”.")
    roadmap_rule = roadmap_rule_de if lang == "de" else roadmap_rule_en

    # Kapitel-spezifische Zusätze
    extras = []
    if chapter == "roadmap":
        extras.append(roadmap_rule)

    if chapter == "quick_wins":
        # Einheitlicher Titel inhaltlich; das Template setzt die Überschrift, aber der Fließtext darf darauf Bezug nehmen.
        extras.append(" Fassen Sie drei sehr kleine, reversible Schritte zusammen, die Datenschutz respektieren.")

    # Kontextvariablen als JSON
    ctx_json = json.dumps(ctx, ensure_ascii=False)
    parts = [
        base,
        "\n\n---\nKontext:\n",
        ctx_json,
        "\n\n---\nRegeln:\n",
        base_rules,
        *extras,
        "\n\n---\nZusätzliche Hinweise:\n",
        extra_ctx,
    ]
    return "\n".join(p for p in parts if p)

# -----------------------------------------------------------------------------
# Kapitel-Generierung
# -----------------------------------------------------------------------------
def _chapter_to_key(chapter: str) -> str:
    return f"{chapter}_html"

def _generate_chapter_html(chapter: str, ctx: Dict[str, Any], lang: str,
                           temperature: float = 0.35) -> str:
    prompt = build_masterprompt(chapter, ctx, lang)
    html = _llm_complete(prompt, model=os.getenv("ANALYZE_MODEL"), temperature=temperature)
    return html

def _postprocess_outputs(raw: Dict[str, str]) -> Dict[str, str]:
    """
    Selektive Sanitisierung (Fix 1): Roadmap/Funding/Tools/Live behalten Zahlen/Listen.
    Andere Kapitel werden 'entlistet', Codefences entfernt, aber keine harte Ziffern-Löschung.
    """
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if not k.endswith("_html"):
            out[k] = v
            continue
        if k in NUM_OK:
            out[k] = _sanitize_text(v)
        else:
            out[k] = _strip_lists_and_numbers(v)
    return out

# -----------------------------------------------------------------------------
# Templating & Fallback (Fix 4 & 5)
# -----------------------------------------------------------------------------
def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html",))
    )

def _template_name(lang: str) -> str:
    return "pdf_template_en.html" if lang == "en" else "pdf_template.html"

def _ensure_min_html(html: str, lang: str, ctx: Dict[str, Any]) -> str:
    """
    Mindestinhalt vor PDF: Wenn zu kurz oder keine Kapitel-Anker vorhanden,
    rendere Fallback-HTML aus Template mit Platzhaltern (Fix 5).
    """
    needs_fallback = False
    if not html or len(html) < MIN_HTML_LEN:
        needs_fallback = True
    # crude: mindestens eine <h2>-Überschrift (Kapitel)
    if "<h2" not in html:
        needs_fallback = True

    if not needs_fallback:
        return html

    # Fallback: Template mit vorhandenen Kapiteln füllen (kann minimal sein)
    env = _jinja_env()
    tpl = env.get_template(_template_name(lang))
    safe_ctx = {
        "meta": {
            "title": ctx.get("meta", {}).get("title") or ("KI‑Statusbericht" if lang == "de" else "AI Status Report"),
            "date": datetime.date.today().strftime("%d.%m.%Y") if lang == "de" else datetime.date.today().isoformat(),
            "lang": lang,
            "branche": ctx.get("branche") or "—",
            "groesse": ctx.get("unternehmensgroesse") or ctx.get("size") or "—",
            "standort": ctx.get("standort") or ctx.get("region") or "—",
        },
        # falls raw leer war, leere Strings einsetzen:
        "exec_summary_html": "",
        "quick_wins_html": ctx.get("quick_wins_html", ""),
        "risks_html": ctx.get("risks_html", ""),
        "recommendations_html": ctx.get("recommendations_html", ""),
        "roadmap_html": ctx.get("roadmap_html", ""),
        "vision_html": ctx.get("vision_html", ""),
        "gamechanger_html": ctx.get("gamechanger_html", ""),
        "compliance_html": ctx.get("compliance_html", ""),
        "funding_html": ctx.get("funding_html", ""),
        "tools_html": ctx.get("tools_html", ""),
        "live_html": ctx.get("live_html", ""),
    }
    return tpl.render(**safe_ctx)

# -----------------------------------------------------------------------------
# Öffentliche API
# -----------------------------------------------------------------------------
def analyze(data: Dict[str, Any], lang: str = DEFAULT_LANG, temperature: float = 0.35) -> Dict[str, str]:
    """
    Führt die Kapitel-Generierung durch und liefert ein Dict {<chapter>_html: "..."}.
    """
    lang = (lang or DEFAULT_LANG).lower()
    if lang not in LANGS:
        lang = DEFAULT_LANG

    # Region normalisieren (Fix 6)
    data = dict(data or {})
    if "bundesland" in data:
        data["bundesland"] = normalize_region(data.get("bundesland"))
    elif "state" in data:
        data["state"] = normalize_region(data.get("state"))

    raw: Dict[str, str] = {}
    for ch in CHAPTERS:
        try:
            raw[_chapter_to_key(ch)] = _generate_chapter_html(ch, data, lang, temperature=temperature)
        except Exception as e:
            # robustes Degrade: Kapitel leerlassen, wird im Template aufgefangen
            raw[_chapter_to_key(ch)] = f""

    return _postprocess_outputs(raw)

def analyze_to_html(data: Dict[str, Any], lang: str = DEFAULT_LANG, temperature: float = 0.35) -> str:
    """
    Liefert vollständig gerendertes HTML (Template + Kapitel).
    Enthält Mindestinhalt-Fallback (Fix 5).
    """
    sections = analyze(data, lang=lang, temperature=temperature)

    env = _jinja_env()
    template = env.get_template(_template_name(lang))

    # Meta
    meta = {
        "title": data.get("meta", {}).get("title")
                 or ("KI‑Statusbericht" if lang == "de" else "AI Status Report"),
        "date": datetime.date.today().strftime("%d.%m.%Y") if lang == "de" else datetime.date.today().isoformat(),
        "lang": lang,
        "branche": data.get("branche") or "—",
        "groesse": data.get("unternehmensgroesse") or data.get("size") or "—",
        "standort": data.get("standort") or data.get("region") or "—",
    }

    # Quick‑Wins-Label/Box (Fix 4): Text bleibt Fließtext; das Template rendert Überschrift + Box-Styling
    html = template.render(
        meta=meta,
        **sections
    )

    # Mindestinhalt vorm PDF
    html = _ensure_min_html(html, lang, {"meta": meta, **sections, **data})
    return html
