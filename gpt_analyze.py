# gpt_analyze.py — Gold-Standard (2025-09-18 HF3)
# - Prompts-first (./prompts/de|en/*.md)
# - OpenAI mit Fallback-Kaskade (gpt-5 → gpt-4o → gpt-4o-mini → gpt-3.5-turbo)
# - Live-Kasten: Tavily first (SerpAPI Fallback) via websearch_utils.search_links
# - Liefert Kontext-Dict für Jinja-Templates (pdf_template*.html)

from __future__ import annotations
import os, json, time, re, logging, datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [analyze] %(message)s")
log = logging.getLogger("analyze")

# ====== ENV / Pfade ===========================================================
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts")).resolve()
DATA_DIR    = Path(os.getenv("DATA_DIR", "data")).resolve()

OPENAI_API_KEY  = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
OPENAI_ENDPOINT = (os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
                   + "/chat/completions")

MODEL_PREFS = [
    (os.getenv("GPT_MODEL_NAME") or "gpt-5").strip(),
    "gpt-4o",
    os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini").strip(),
    "gpt-3.5-turbo",
]
TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.3"))
MAX_TOKENS  = int(os.getenv("GPT_MAX_TOKENS", "1400"))
DEFAULT_LANG= (os.getenv("DEFAULT_LANG","de") or "de").lower()

# ====== Websuche (Tavily-first) ==============================================
try:
    # Du hast websearch_utils.py bereits im Projekt liegen
    from websearch_utils import search_links, render_live_box_html
except Exception as e:
    log.warning("[websearch] utils missing: %s", repr(e))
    def search_links(*args, **kwargs): return []
    def render_live_box_html(*args, **kwargs): return ""

# ====== Monate für Datumsanzeige =============================================
MONTHS_DE = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"]

def _month_year(lang: str="de") -> str:
    now = dt.date.today()
    return f"{(MONTHS_DE if lang.startswith('de') else MONTHS_EN)[now.month-1]} {now.year}"

def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

# ====== Prompt-Loader =========================================================
_PROMPT_CACHE: Dict[Tuple[str,str], str] = {}

def _pfile(lang: str, name: str) -> Path:
    # prompts/<lang>/<name>.md
    return PROMPTS_DIR.joinpath(lang, f"{name}.md")

def _pfile_fallbacks(lang: str, name: str) -> List[Path]:
    # Fallbacks (selten): <name>_<lang>.md, <name>.md
    return [PROMPTS_DIR.joinpath(f"{name}_{lang}.md"),
            PROMPTS_DIR.joinpath(f"{name}.md")]

def load_prompt(name: str, lang: str, default: str = "") -> str:
    key = (lang, name)
    if key in _PROMPT_CACHE:
        return _PROMPT_CACHE[key]
    fp = _pfile(lang, name)
    try:
        if fp.exists():
            txt = fp.read_text(encoding="utf-8").strip()
            log.info("[PROMPT] %s <- %s", name, fp)
            _PROMPT_CACHE[key] = txt
            return txt
    except Exception as e:
        log.warning("[PROMPT] read failed %s: %s", fp, e)
    for fb in _pfile_fallbacks(lang, name):
        try:
            if fb.exists():
                txt = fb.read_text(encoding="utf-8").strip()
                log.info("[PROMPT] %s <- %s", name, fb)
                _PROMPT_CACHE[key] = txt
                return txt
        except Exception:
            pass
    if default:
        log.warning("[PROMPT] %s not found – using default", name)
    _PROMPT_CACHE[key] = default
    return default
# ====== Formular-Extraktion ===================================================
def _first_nonempty(*vals: Optional[str]) -> str:
    for v in vals:
        if v and str(v).strip():
            return str(v).strip()
    return ""

def _as_lang(body: Dict[str, Any], explicit: Optional[str]) -> str:
    if explicit:
        return "de" if explicit.lower().startswith("de") else "en"
    v = (body.get("lang") or body.get("language") or DEFAULT_LANG or "de").lower()
    return "de" if v.startswith("de") else "en"

def _extract_meta(body: Dict[str, Any]) -> Dict[str,str]:
    # robuste Feldzuordnung (mehrere mögliche Keys)
    industry = _first_nonempty(
        body.get("branche"), body.get("industry"), body.get("Branche"),
        body.get("sector"), body.get("industry_name")
    ) or "Beratung"
    company = _first_nonempty(body.get("firma"), body.get("company"), body.get("unternehmen"))
    size    = _first_nonempty(body.get("groesse"), body.get("company_size"), body.get("größe"))
    location= _first_nonempty(body.get("standort"), body.get("location"), body.get("ort"), body.get("land"))
    product = _first_nonempty(
        body.get("hauptleistung"), body.get("hauptprodukt"),
        body.get("main_product"), body.get("main_service")
    )
    return {
        "company": company,
        "industry": industry,
        "company_size": size or "n/a",
        "location": location or "n/a",
        "main_product": product or "",
    }

# ====== Sanitizer & Platzhalter-Füllung ======================================
_BAD_LINES = re.compile(r"^\s*(i'?m sorry|as an ai|i cannot assist|can['’]t assist)", re.I)

def _sanitize_text(t: str) -> str:
    if not t: return t
    # Entfernt häufige LLM-Disclaimer & Codefences
    t = t.replace("\r", "")
    t = t.replace("```html","```").replace("```HTML","```")
    t = t.replace("```","")
    # Problematische Einleitungsphrasen entfernen
    lines = [ln for ln in t.split("\n") if not _BAD_LINES.match(ln.strip())]
    t = "\n".join(lines)
    # „Fehler:“ Artefakte aus alten Prompts raus
    t = re.sub(r"^\s*(Fehler|Error)\s*:\s*.*$", "", t, flags=re.I|re.M)
    return t.strip()

# Ersetzt {{ feldname }} in einem generierten Absatz mit Werten aus body
_CURLY = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

def _fill_curly_placeholders(text: str, source: Dict[str, Any]) -> str:
    if not text: return text
    def repl(m):
        key = m.group(1)
        v = source.get(key)
        return str(v) if v is not None else ""
    return _CURLY.sub(repl, text)

def _mk_hook(lang: str, meta: Dict[str,str]) -> str:
    if lang.startswith("de"):
        return f"In der Branche {meta['industry']} zeigen Unternehmen Ihrer Größe ({meta['company_size']}) gerade, wie KI aus {meta['main_product'] or 'Kernprozessen'} messbaren Nutzen macht."
    return f"In {meta['industry']}, peers of your size ({meta['company_size']}) are turning AI into measurable wins across {meta['main_product'] or 'core processes'}."
# ====== OpenAI Call mit Fallback-Kaskade =====================================
def _call_openai(messages: List[Dict[str, str]], model: Optional[str]=None,
                 temperature: float = TEMPERATURE, max_tokens: int = MAX_TOKENS) -> str:
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    last_err = None
    for m in ([model] if model else []) + [m for m,_ in enumerate(MODEL_PREFS) or []]:
        pass  # no-op to satisfy linter

    # Iteriere Präferenzliste
    for mdl in ([model] if model else []) + [m for m in MODEL_PREFS if m != (model or "")]:
        payload = {"model": mdl, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        try:
            with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0, read=30.0)) as c:
                r = c.post(OPENAI_ENDPOINT, headers=headers, json=payload)
            if 200 <= r.status_code < 300:
                data = r.json()
                out = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
                if out.strip():
                    log.info("LLM %s ok", mdl)
                    return out
                last_err = RuntimeError("empty response")
            else:
                last_err = RuntimeError(f"HTTP {r.status_code}")
                log.info("LLM %s failed: %s", mdl, r.status_code)
        except Exception as e:
            last_err = e
            log.info("LLM %s exception: %s", mdl, repr(e))
    raise RuntimeError(f"LLM failed: {repr(last_err)}")

def _compose_section(prompt_name: str, lang: str, meta: Dict[str,str], body: Dict[str,Any],
                     additions: Optional[str] = None, temp: float = TEMPERATURE) -> str:
    system = "You are a senior AI strategy writer. Write warm, narrative paragraphs. No bullet points. No numbers."
    if lang.startswith("de"):
        system = ("Du bist Senior-Berater für KI-Strategie. Schreibe warm, empathisch, narrativ. "
                  "Keine Listen, keine Prozentzahlen, keine KPI. DSGVO, ePrivacy, DSA und EU-AI-Act berücksichtigen.")
    prefix = load_prompt("prompt_prefix", lang, "")
    suffix = load_prompt("prompt_suffix", lang, "")
    base   = load_prompt(prompt_name, lang, "")
    add    = additions or load_prompt(("prompt_additions_de" if lang.startswith("de") else "prompt_additions_en"), lang, "")

    user = "\n\n".join([p for p in [prefix, base, add, suffix] if p.strip()])
    messages = [{"role":"system","content":system},
                {"role":"user","content": user}]

    try:
        raw = _call_openai(messages, model=None, temperature=temp, max_tokens=MAX_TOKENS)
    except Exception as e:
        log.error("LLM call failed: %s", e)
        return ""

    # Nachbearbeitung
    raw = _sanitize_text(raw)
    # Platzhalter mit bekannten Feldern/Antworten ersetzen
    merged = {**body, **meta}
    return _fill_curly_placeholders(raw, merged)
# ====== Live-Suche & Box ======================================================
def _live_query(lang: str, meta: Dict[str,str]) -> str:
    # Query: Branche × Größe × Hauptleistung
    if lang.startswith("de"):
        topic = os.getenv("SEARCH_TOPIC", "news")
        return (f"{meta['industry']} {meta['main_product']} {meta['company_size']} "
                f"(Förderung KI OR Zuschuss KI OR Programm KI OR Tool KI OR Software KI) site:de")
    else:
        return (f"{meta['industry']} {meta['main_product']} {meta['company_size']} "
                f"(grant OR funding OR program OR AI tool)")

def _build_live_box(lang: str, meta: Dict[str,str], max_results: int = 5) -> str:
    try:
        q = _live_query(lang, meta)
        links = search_links(q, lang=lang, max_results=max_results)
        if not links:
            return ""
        title = "Neu seit " + _month_year(lang)
        return render_live_box_html(title, links, lang=lang)
    except Exception as e:
        log.warning("[live] box failed: %s", repr(e))
        return ""

# ====== HTML-Bausteine: Compliance / Funding / Tools =========================
def _compose_html_block(block_name: str, lang: str, meta: Dict[str,str], body: Dict[str,Any]) -> str:
    # block_name: "compliance" | "foerderprogramme" | "tools"
    txt = _compose_section(block_name, lang, meta, body, temp=max(0.2, TEMPERATURE-0.1))
    # Erlaubt, dass Prompts mit <p>, <h3> etc. arbeiten; kein weiterer Wrap hier
    return txt

def _vision_title(lang: str) -> str:
    return "Vision & Leitstern" if lang.startswith("de") else "Vision & North Star"

def _game_title(lang: str) -> str:
    return "Innovation & Gamechanger" if lang.startswith("de") else "Innovation & Game Changer"

def _footer_cta(lang: str) -> str:
    return ("Ihre Meinung zählt: Feedback geben (kurz)") if lang.startswith("de") else ("Your opinion matters: Give feedback (short)")
# ====== Haupteinstieg =========================================================
def analyze_briefing(body: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Nimmt den Fragebogen-Body, erzeugt die Fließtexte je Kapitel (prompts/*),
    fügt Live-Kasten ein und liefert das Kontext-Dict für die Templates.
    """
    lang = _as_lang(body, lang)
    meta = _extract_meta(body)

    title = "KI-Statusbericht" if lang.startswith("de") else "AI Readiness Report"
    stand = _month_year(lang)
    hook  = _mk_hook(lang, meta)

    # Hauptabschnitte
    executive = _compose_section("executive_summary", lang, meta, body)
    quick     = _compose_section("quick_wins", lang, meta, body)
    risks     = _compose_section("risks", lang, meta, body)
    recs      = _compose_section("recommendations", lang, meta, body)
    roadmap   = _compose_section("roadmap", lang, meta, body)
    vision    = _compose_section("vision", lang, meta, body)
    game      = _compose_section("gamechanger", lang, meta, body)

    # HTML-Blöcke
    compliance_html = _compose_html_block("compliance", lang, meta, body)
    funding_html    = _compose_html_block("foerderprogramme", lang, meta, body)
    tools_html      = _compose_html_block("tools", lang, meta, body)

    # Live seit {Monat}
    live_box_html = _build_live_box(lang, meta, max_results=int(os.getenv("SEARCH_MAX_RESULTS","5")))

    # Zusammensetzen
    ctx: Dict[str, Any] = {
        "title": title,
        "company": meta["company"],
        "industry": meta["industry"],
        "company_size": meta["company_size"],
        "location": meta["location"],
        "industry_hook": hook,

        "executive_summary": executive,
        "quick_wins": quick,
        "risks": risks,
        "recommendations": recs,
        "roadmap": roadmap,
        "vision_title": _vision_title(lang),
        "vision": vision,
        "game_title": _game_title(lang),
        "gamechanger": game,

        "compliance_html": compliance_html,
        "funding_html": (live_box_html + funding_html) if live_box_html else funding_html,
        "tools_html": tools_html,

        "stand_datum": stand,
        "footer_cta": _footer_cta(lang),
    }
    return ctx
