# gpt_analyze.py — Gold Standard 2025-09-21
# Killer-Fixes 1–6 + Kompatibilität zu main.py (analyze_briefing vorhanden)
from __future__ import annotations

import os, re, json, datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

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

CHAPTERS: List[str] = [
    "exec_summary",
    "quick_wins",
    "risks",
    "recommendations",
    "roadmap",
    "vision",
    "gamechanger",
    "compliance",
    "funding",
    "tools",
    "live",
]

# Kapitel, in denen Zahlen/Listen erhalten bleiben (Fix 1)
NUM_OK = {"roadmap_html", "funding_html", "tools_html", "live_html"}

# -----------------------------------------------------------------------------
# Sanitisierung
# -----------------------------------------------------------------------------
_CODEFENCE_RE = re.compile(r"```.*?```", flags=re.S)
_TAG_RE = re.compile(r"</?(script|style)[^>]*>", flags=re.I)
_LEADING_ENUM_RE = re.compile(r"(?m)^\s*(?:\d+[\.\)]|[-–•])\s+")
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
    html = _LI_RE.sub("\n", html)
    html = _OL_UL_RE.sub("\n", html)
    html = _LEADING_ENUM_RE.sub("", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html

def _strip_lists_and_numbers(html: str) -> str:
    """Listen in Fließtext überführen; KEIN globales Ziffernlöschen mehr."""
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
    html = html.replace("&nbsp;", " ")
    return html

# -----------------------------------------------------------------------------
# Region-Normalisierung (Fix 6)
# -----------------------------------------------------------------------------
REGION_MAP = {
    "be":"berlin","bb":"brandenburg","bw":"baden-württemberg","by":"bayern",
    "hb":"bremen","hh":"hamburg","he":"hessen","mv":"mecklenburg-vorpommern",
    "ni":"niedersachsen","nw":"nordrhein-westfalen","nrw":"nordrhein-westfalen",
    "rp":"rheinland-pfalz","sl":"saarland","sn":"sachsen","st":"sachsen-anhalt",
    "sh":"schleswig-holstein","th":"thüringen",
}
def normalize_region(value: Optional[str]) -> str:
    if not value:
        return ""
    v = str(value).strip().lower()
    return REGION_MAP.get(v, v)

# -----------------------------------------------------------------------------
# Prompts laden – nur prompts/{de|en}/… (Fix 2)
# -----------------------------------------------------------------------------
def _must_exist(p: Path) -> Path:
    if not p.exists():
        raise FileNotFoundError(f"Nicht gefunden: {p}")
    return p

def _load_text(p: Path) -> str:
    return _must_exist(p).read_text(encoding="utf-8")

def _read_prompt(chapter: str, lang: str) -> str:
    lang = lang if lang in LANGS else DEFAULT_LANG
    return _load_text(PROMPTS_DIR / lang / f"{chapter}.md")

def _read_optional_context(lang: str) -> str:
    parts: List[str] = []
    for name in ("persona.md","praxisbeispiel.md","foerderprogramme.md","tools.md"):
        p = PROMPTS_DIR / lang / name
        if p.exists():
            parts.append(_load_text(p))
    return "\n\n".join(parts)

# -----------------------------------------------------------------------------
# LLM-Aufruf (platzhalter-kompatibel)
# -----------------------------------------------------------------------------
def _llm_complete(prompt: str, model: Optional[str]=None, temperature: float=0.35) -> str:
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
                {"role":"system","content":"You write warm, compliant HTML paragraphs (no lists)."},
                {"role":"user","content":prompt},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

# -----------------------------------------------------------------------------
# Prompt-Bau (Fix 3: Roadmap-Zeitanker ohne Ziffern)
# -----------------------------------------------------------------------------
def build_masterprompt(chapter: str, ctx: Dict[str,Any], lang: str) -> str:
    base = _read_prompt(chapter, lang)
    extra_ctx = _read_optional_context(lang)
    rules_de = ("Schreiben Sie narrativ in Absätzen (keine Listen/Tabellen), per Sie, "
                "freundlich, optimistisch, ohne Buzzwords. EU‑Hosting bevorzugen. "
                "DSGVO, ePrivacy, DSA, EU‑AI‑Act pragmatisch einordnen.")
    rules_en = ("Write in warm narrative paragraphs (no lists/tables), polite, optimistic, no buzzwords. "
                "Prefer EU‑hosted options. Address GDPR, ePrivacy, DSA, EU AI Act pragmatically.")
    rules = rules_de if lang == "de" else rules_en
    roadmap_rule_de = " Verwenden Sie Zeitanker ohne Ziffern: „sofort“, „in den nächsten Wochen“, „innerhalb eines Jahres“."
    roadmap_rule_en = " Use time anchors without digits: “immediately”, “in the coming weeks”, “within a year”."
    extras = [roadmap_rule_de if lang=="de" and chapter=="roadmap" else "",
              roadmap_rule_en if lang=="en" and chapter=="roadmap" else ""]
    ctx_json = json.dumps(ctx, ensure_ascii=False)
    return "\n".join([base,
                      "\n---\nKontext:\n", ctx_json,
                      "\n---\nRegeln:\n", rules,
                      *(e for e in extras if e),
                      "\n---\nZusätzliche Hinweise:\n", extra_ctx])

# -----------------------------------------------------------------------------
# Kapitel-Generierung & Nachbearbeitung
# -----------------------------------------------------------------------------
def _chapter_key(ch: str) -> str: return f"{ch}_html"

def _generate_chapter_html(chapter: str, ctx: Dict[str,Any], lang: str, temperature: float=0.35) -> str:
    prompt = build_masterprompt(chapter, ctx, lang)
    return _llm_complete(prompt, model=os.getenv("ANALYZE_MODEL"), temperature=temperature)

def _postprocess(outputs: Dict[str,str]) -> Dict[str,str]:
    out: Dict[str,str] = {}
    for k, v in outputs.items():
        if not k.endswith("_html"):
            out[k] = v; continue
        if k in NUM_OK:
            out[k] = _sanitize_text(v)
        else:
            out[k] = _strip_lists_and_numbers(v)
    return out

# -----------------------------------------------------------------------------
# Templating (für direkten HTML-Output; main.py darf auch nur Kontext nehmen)
# -----------------------------------------------------------------------------
def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)),
                       autoescape=select_autoescape(enabled_extensions=("html",)))

def _tpl_name(lang: str) -> str:
    return "pdf_template_en.html" if lang=="en" else "pdf_template.html"

def _ensure_min_html(html: str, lang: str, ctx: Dict[str,Any]) -> str:
    need = (not html) or (len(html) < MIN_HTML_LEN) or ("<h2" not in html)
    if not need:
        return html
    env = _env()
    tpl = env.get_template(_tpl_name(lang))
    safe_meta = {
        "title": ctx.get("meta",{}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": ctx.get("branche") or "—",
        "groesse": ctx.get("unternehmensgroesse") or ctx.get("size") or "—",
        "standort": ctx.get("standort") or ctx.get("region") or "—",
    }
    base_ctx = {
        "exec_summary_html": "",
        "quick_wins_html": ctx.get("quick_wins_html",""),
        "risks_html": ctx.get("risks_html",""),
        "recommendations_html": ctx.get("recommendations_html",""),
        "roadmap_html": ctx.get("roadmap_html",""),
        "vision_html": ctx.get("vision_html",""),
        "gamechanger_html": ctx.get("gamechanger_html",""),
        "compliance_html": ctx.get("compliance_html",""),
        "funding_html": ctx.get("funding_html",""),
        "tools_html": ctx.get("tools_html",""),
        "live_html": ctx.get("live_html",""),
    }
    return tpl.render(meta=safe_meta, **base_ctx)

# -----------------------------------------------------------------------------
# Öffentliche API
# -----------------------------------------------------------------------------
def analyze(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> Dict[str,str]:
    """Kapitel generieren und als Dict {<chapter>_html: "..."} zurückgeben."""
    lang = lang if lang in LANGS else DEFAULT_LANG
    d = dict(data or {})
    if "bundesland" in d:
        d["bundesland"] = normalize_region(d.get("bundesland"))
    elif "state" in d:
        d["state"] = normalize_region(d.get("state"))

    raw: Dict[str,str] = {}
    for ch in CHAPTERS:
        try:
            raw[_chapter_key(ch)] = _generate_chapter_html(ch, d, lang, temperature=temperature)
        except Exception:
            raw[_chapter_key(ch)] = ""  # robustes Degrade
    return _postprocess(raw)

def analyze_briefing(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> Dict[str,Any]:
    """
    **Kompatibilität für main.py**:
    Liefert einen vollständigen Jinja-Kontext inkl. meta{title,date,lang,branche,groesse,standort}
    und allen *_html-Feldern.
    """
    sections = analyze(data, lang=lang, temperature=temperature)
    meta = {
        "title": (data.get("meta", {}) or {}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": data.get("branche") or "—",
        "groesse": data.get("unternehmensgroesse") or data.get("size") or "—",
        "standort": data.get("standort") or data.get("region") or "—",
    }
    ctx = {"meta": meta}
    ctx.update(sections)
    return ctx

def analyze_to_html(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> str:
    """
    Optionaler Convenience-Wrapper, falls direkt HTML benötigt wird.
    """
    sections = analyze(data, lang=lang, temperature=temperature)
    env = _env()
    tpl = env.get_template(_tpl_name(lang))
    meta = {
        "title": (data.get("meta", {}) or {}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": data.get("branche") or "—",
        "groesse": data.get("unternehmensgroesse") or data.get("size") or "—",
        "standort": data.get("standort") or data.get("region") or "—",
    }
    html = tpl.render(meta=meta, **sections)
    return _ensure_min_html(html, lang, {"meta": meta, **sections, **data})
