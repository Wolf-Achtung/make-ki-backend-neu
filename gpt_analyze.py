# gpt_analyze.py — Gold-Standard (2025-09-18 HF3)
# - Prompts-first (./prompts/de|en/*.md)
# - OpenAI mit Modell-Fallback (env GPT_MODEL_NAME -> EXEC_SUMMARY_MODEL)
# - Live-Kasten: Tavily first (SerpAPI Fallback) via websearch_utils.search_links
# - Liefert Kontext-Dict für Jinja-Templates (pdf_template*.html)

from __future__ import annotations
import os, json, time, logging, datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import httpx

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [analyze] %(message)s")
log = logging.getLogger("analyze")

PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts")).resolve()
DATA_DIR    = Path(os.getenv("DATA_DIR", "data")).resolve()

OPENAI_API_KEY  = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
OPENAI_ENDPOINT = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

MODEL_NAME         = (os.getenv("GPT_MODEL_NAME") or "gpt-4o-mini").strip()
EXEC_SUMMARY_MODEL = (os.getenv("EXEC_SUMMARY_MODEL") or MODEL_NAME).strip()
SUMMARY_MODEL_NAME = (os.getenv("SUMMARY_MODEL_NAME") or MODEL_NAME).strip()
TEMPERATURE        = float(os.getenv("GPT_TEMPERATURE", "0.3"))
MAX_TOKENS         = int(os.getenv("GPT_MAX_TOKENS", "1400"))
DEFAULT_LANG       = (os.getenv("DEFAULT_LANG","de") or "de").lower()

SEARCH_DAYS        = int(os.getenv("SEARCH_DAYS","14"))
SEARCH_MAX         = int(os.getenv("SEARCH_MAX_RESULTS","5"))
INC_DOMAINS        = [s.strip() for s in (os.getenv("SEARCH_INCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_INCLUDE_DOMAINS") else []) if s.strip()]
EXC_DOMAINS        = [s.strip() for s in (os.getenv("SEARCH_EXCLUDE_DOMAINS","").split(",") if os.getenv("SEARCH_EXCLUDE_DOMAINS") else []) if s.strip()]

from websearch_utils import search_links, live_query_for, render_live_box_html

MONTHS_DE = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"]

def _month_year(lang: str="de") -> str:
    now = dt.date.today()
    if (lang or "de").lower().startswith("de"):
        return f"{MONTHS_DE[now.month-1]} {now.year}"
    return f"{MONTHS_EN[now.month-1]} {now.year}"

def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

def _first(*vals) -> str:
    for v in vals:
        v = _norm(v)
        if v:
            return v
    return ""

def _lang(body: Dict[str, Any], explicit: Optional[str]) -> str:
    if explicit:
        return "de" if explicit.lower().startswith("de") else "en"
    v = (body.get("lang") or body.get("language") or DEFAULT_LANG or "de").lower()
    return "de" if v.startswith("de") else "en"
# --- sanitize + helpers (ADD THIS BLOCK) ------------------------------
BAD_PREFIXES = ("I'm sorry", "I can't assist", "I cannot help", "As an AI")
def _sanitize_html(s: str) -> str:
    s = (s or "").strip()
    for bad in BAD_PREFIXES:
        if bad in s:
            s = s.replace(bad, "")
    # entschärft versehentliche Jinja-Tokens aus LLM
    s = s.replace("{{", "&#123;&#123;").replace("}}", "&#125;&#125;")
    return s.strip()

def _build_live_box(ctx: dict, lang: str) -> str:
    try:
        # Query aus Kontext generieren (Branche × Größe × Leistung)
        q = live_query_for(ctx, lang=lang)
        # Tavily first, dann SerpAPI
        links = search_links(q, num=5, lang=lang, country=("de" if lang.startswith("de") else "uk"))
        # HTML sauber rendern (Signatur tolerant; kein multiple-values Fehler mehr)
        title = "New since" if lang.startswith("en") else "Neu seit"
        return render_live_box_html(title, links, lang=lang)
    except Exception as e:
        log.warning("live box search failed: %s", e)
        return ""


def _finalize_ctx(body: Dict[str, Any], out: Dict[str, Any], lang: str) -> Dict[str, Any]:
    # Metadaten (Branche/Größe/Standort) aus Ergebnis ODER Eingabe
    meta = {
        "lang": lang,
        "branche": _first(out.get("branche"), body.get("branche"), body.get("industry")),
        "company_size": _first(out.get("groesse"), out.get("company_size"), body.get("groesse"), body.get("company_size")),
        "location": _first(out.get("standort"), body.get("standort"), body.get("location")),
        "month_label": _month_year(lang)
    }
    sections = {
        "executive_summary": _sanitize_html(out.get("executive_summary", "")),
        "quick_wins":        _sanitize_html(out.get("quick_wins", "")),
        "risks":             _sanitize_html(out.get("risks", "")),
        "recommendations":   _sanitize_html(out.get("recommendations", "")),
        "roadmap":           _sanitize_html(out.get("roadmap", "")),
        "vision":            _sanitize_html(out.get("vision", "")),
        "gamechanger":       _sanitize_html(out.get("gamechanger", "")),
        "compliance":        _sanitize_html(out.get("compliance", "")),
        "tools":             _sanitize_html(out.get("tools", "")),
        "foerderprogramme":  _sanitize_html(out.get("foerderprogramme", "")),
    }
    ctx = {"meta": meta, "sections": sections}
    # Live-Kasten anhängen (optional im Template einbinden)
    ctx["live_box_html"] = _build_live_box({**body, **meta}, lang)
    return ctx
# ----------------------------------------------------------------------

# ====== Prompt-Loader ======================================================
_PROMPT_CACHE: Dict[Tuple[str,str], str] = {}

def _pfile(lang: str, name: str) -> Path:
    return PROMPTS_DIR.joinpath(lang, f"{name}.md")

def _pfile_fallbacks(lang: str, name: str):
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

# ====== OpenAI =============================================================
def _call_openai(messages: List[Dict[str,Any]], model: str, temperature: float, max_tokens: int) -> Dict[str,Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    with httpx.Client(timeout=40.0) as client:
        r = client.post(OPENAI_ENDPOINT, headers=headers, json=payload)
        try:
            r.raise_for_status()
        except Exception as e:
            log.info("LLM %s failed: %s", model, r.status_code)
            raise
        return r.json()

def _compose_and_call_llm(messages: List[Dict[str,Any]], *, model: str) -> str:
    order = [model, EXEC_SUMMARY_MODEL, SUMMARY_MODEL_NAME, "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
    seen = set()
    for m in order:
        m = (m or "").strip()
        if not m or m in seen:
            continue
        seen.add(m)
        try:
            raw = _call_openai(messages, model=m, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
            content = (raw.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if content:
                return content
        except Exception:
            continue
    return ""

# ====== Section builders ===================================================
def _ctx_from_body(body: Dict[str,Any], lang: str) -> Dict[str,Any]:
    # normalize key variants from the form
    industry = _first(body.get("branche"), body.get("industry"))
    size     = _first(body.get("groesse"), body.get("größe"), body.get("size"))
    location = _first(body.get("standort"), body.get("location"))
    product  = _first(body.get("hauptleistung"), body.get("primary_product"), body.get("hauptprodukt"))
    persona  = _first(body.get("zielgruppe"), body.get("persona"))
    return {
        "lang": lang,
        "industry": industry or ("Beratung" if lang=="de" else "consulting"),
        "size": size or ("KMU" if lang=="de" else "SME"),
        "location": location,
        "primary_product": product,
        "persona": persona,
    }

def _section_from_prompt(name: str, lang: str, ctx: Dict[str,Any], body: Dict[str,Any]) -> str:
    prefix = load_prompt("prompt_prefix", lang, "")
    suffix = load_prompt("prompt_suffix", lang, "")
    extra  = load_prompt(f"prompt_additions_{'de' if lang=='de' else 'en'}", lang, "")
    section_prompt = load_prompt(name, lang, "")

    instruction = f"""{prefix}

    {section_prompt}

    {extra}
    {suffix}
    """
    user_ctx = {
        "industry": ctx.get("industry"),
        "size": ctx.get("size"),
        "location": ctx.get("location"),
        "primary_product": ctx.get("primary_product"),
        "answers": body,
    }
    messages = [
        {"role":"system", "content": "You are a senior AI consultant. Write warm, narrative paragraphs, no bullets, no numbers. Mention EU compliance (GDPR, ePrivacy, DSA, EU AI Act) when relevant. German if lang=de, else English."},
        {"role":"user", "content": json.dumps({"lang": lang, "context": user_ctx, "instruction": instruction}, ensure_ascii=False)},
    ]
    txt = _compose_and_call_llm(messages, model=MODEL_NAME).strip()
    return txt or ""

def _build_live_box(ctx: Dict[str,Any], lang: str) -> str:
    q = live_query_for(ctx, lang=lang)
    try:
        links = search_links(q, topic=os.getenv("SEARCH_TOPIC","news"), days=SEARCH_DAYS,
                             max_results=SEARCH_MAX, include_domains=INC_DOMAINS, exclude_domains=EXC_DOMAINS, lang=lang)
    except TypeError as e:
        # Compatibility with older search_links implementations
        log.warning("live box search failed: %s", e)
        links = search_links(q, topic=os.getenv("SEARCH_TOPIC","news"), days=SEARCH_DAYS,
                             max_results=SEARCH_MAX, include_domains=INC_DOMAINS, exclude_domains=EXC_DOMAINS)
    title = ("Neu seit " + _month_year(lang)) if lang=="de" else ("New since " + _month_year(lang))
    try:
        return render_live_box_html(title, links, lang=lang)
    except TypeError:
        return render_live_box_html(title, links)

# ====== Public entrypoint ==================================================
def analyze_briefing(body: Dict[str,Any], lang: Optional[str] = None) -> Dict[str,Any]:
    lng = _lang(body, lang)
    ctx = _ctx_from_body(body, lng)

    sections = {}
    for name in ["executive_summary","quick_wins","risks","recommendations","roadmap","vision","gamechanger","compliance","tools","foerderprogramme"]:
        try:
            sections[name] = _section_from_prompt(name, lng, ctx, body)
        except Exception as e:
            log.warning("section %s failed: %s", name, e)
            sections[name] = ""

    live_html = _build_live_box(ctx, lng)

    out = {
        "lang": lng,
        "month_label": _month_year(lng),
        "industry": ctx.get("industry"),
        "size": ctx.get("size"),
        "location": ctx.get("location"),
        "primary_product": ctx.get("primary_product"),
        "sections": sections,
        "live_box_html": live_html,
        "tools_html": sections.get("tools",""),
        "foerderprogramme_html": sections.get("foerderprogramme",""),
    }
    # statt: return out
    return _finalize_ctx(body, out, lng)
