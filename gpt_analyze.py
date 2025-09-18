# gpt_analyze.py — Gold-Standard (2025-09-18 HF3)
# - Prompts-first (./prompts/de|en/*.md)
# - OpenAI mit Modell-Fallback (alias: gpt-5 -> gpt-4o)
# - Live-Kasten: Tavily first (SerpAPI Fallback) via websearch_utils.search_links
# - Liefert Kontext-Dict für Jinja-Templates (pdf_template*.html)

from __future__ import annotations
import os, re, json, time, logging, datetime as dt
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import httpx

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [analyze] %(message)s")
log = logging.getLogger("analyze")

# ====== ENV / Pfade ===========================================================
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts")).resolve()
DATA_DIR    = Path(os.getenv("DATA_DIR", "data")).resolve()

OPENAI_API_KEY  = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
OPENAI_ENDPOINT = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

# bevorzugte Modelle (werden alias-bereinigt)
MODEL_NAME         = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini").strip()
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", MODEL_NAME).strip()
SUMMARY_MODEL_NAME = os.getenv("SUMMARY_MODEL_NAME", MODEL_NAME).strip()
TEMPERATURE        = float(os.getenv("GPT_TEMPERATURE", "0.3"))
MAX_TOKENS         = int(os.getenv("GPT_MAX_TOKENS", "1400"))
DEFAULT_LANG       = (os.getenv("DEFAULT_LANG","de") or "de").lower()

# Web-Suche (Tavily-first Wrapper)
from websearch_utils import search_links, render_live_box_html

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
# ====== Prompt-Loader =========================================================
_PROMPT_CACHE: Dict[Tuple[str,str], str] = {}

def _pfile(lang: str, name: str) -> Path:
    # bevorzugt: prompts/<lang>/<name>.md
    return PROMPTS_DIR.joinpath(lang, f"{name}.md")

def _pfile_fallbacks(lang: str, name: str) -> List[Path]:
    # Fallbacks (selten benötigt): <name>_<lang>.md, <name>.md
    return [
        PROMPTS_DIR.joinpath(f"{name}_{lang}.md"),
        PROMPTS_DIR.joinpath(f"{name}.md"),
    ]

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

# ====== Modell-Aliase & OpenAI Call ==========================================
_MODEL_ALIASES = {
    "gpt-5": "gpt-4o",
    "gpt5": "gpt-4o",
    "gpt-4.1": "gpt-4o",
    "gpt-o": "gpt-4o",
}

def _alias(model: str) -> str:
    m = (model or "").strip().lower()
    return _MODEL_ALIASES.get(m, model)

def _call_openai(messages: List[Dict[str,Any]], model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY fehlt")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": _alias(model),
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    with httpx.Client(timeout=httpx.Timeout(60.0, read=120.0, write=30.0)) as c:
        r = c.post(OPENAI_ENDPOINT, headers=headers, json=payload)
        if r.status_code >= 400:
            # einmaliger Fallback auf gpt-4o-mini wenn Model nicht akzeptiert
            fb = "gpt-4o-mini"
            if _alias(model) != fb:
                log.info("LLM %s failed %s – retry with %s", model, r.status_code, fb)
                payload["model"] = fb
                r = c.post(OPENAI_ENDPOINT, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()

def _compose_and_call_llm(system: str, user: str, model: Optional[str] = None) -> str:
    messages = [{"role":"system","content":system},{"role":"user","content":user}]
    raw = _call_openai(messages, model or MODEL_NAME, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
    txt = (raw.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
    return txt

# ====== Sanitize (keine Jinja-Platzhalter/Codezäune) =========================
_RE_JINJA = re.compile(r"(\{\{.*?\}\}|\{\%.*?\%\})", re.DOTALL)

def sanitize_text(t: str) -> str:
    if not t: return t
    t = t.replace("```html","```").replace("```HTML","```")
    while "```" in t:
        t = t.replace("```","")
    # Curly Braces aus generierten Fließtexten entfernen
    t = _RE_JINJA.sub("", t)
    return t.strip()
# ====== Form-Daten lesen ======================================================
def _get_field(body: Dict[str,Any], *keys: str) -> Optional[str]:
    for k in keys:
        if k in body and isinstance(body[k], str):
            v = body[k].strip()
            if v: return v
    return None

def _extract_context(body: Dict[str,Any], lang: str) -> Dict[str,str]:
    company = _first(_get_field(body,"company","firma","unternehmen"), "")
    industry = _first(_get_field(body,"industry","branche"), "Beratung" if lang=="de" else "Consulting")
    product  = _first(_get_field(body,"hauptleistung","main_product","main_service"), "")
    company_size = _first(_get_field(body,"company_size","größe","size"), "solo")
    location = _first(_get_field(body,"location","standort","country"), "Deutschland" if lang=="de" else "Germany")
    return {
        "company": company,
        "industry": industry,
        "product": product,
        "company_size": company_size,
        "location": location,
    }

def _industry_hook(ctx: Dict[str,str], lang: str) -> str:
    ind = ctx.get("industry","").lower()
    prod = ctx.get("product","")
    if lang=="de":
        if "beratung" in ind:
            return "Beratung mit klarer KI‑Kante: schneller Nutzen, saubere Compliance, spürbare Entlastung."
        if "handel" in ind:
            return "Vom Warenkorb zur Wirkung: KI entlastet Teams und hebt Conversion – DSGVO‑sicher."
        return f"KI als Vorteil in {ctx.get('industry','Ihrer Branche')}: pragmatisch, menschenzentriert, gesetzeskonform."
    else:
        if "consult" in ind:
            return "Consulting with a clear AI edge: rapid wins, clean compliance, real team relief."
        if "retail" in ind:
            return "From basket to benefit: AI lifts conversion and cuts busywork – GDPR‑ready."
        return f"AI as an edge in {ctx.get('industry','your industry')}: pragmatic, human‑centric, compliant."

# ====== Prompt-Bausteine ======================================================
def _build_system(lang: str) -> str:
    if lang=="de":
        return ("Du bist ein warmherziger, professioneller Berater. Schreibe flüssige, empathische, "
                "journalistische Absätze ohne Bullet-Listen und ohne Zahlen/KPIs. "
                "Nenne DSGVO, ePrivacy, DSA und EU‑AI‑Act kontextsensitiv. "
                "Schreibe niemals Code, keine Platzhalter mit {{...}} oder {%...%}, keine Tabellen.")
    return ("You are a warm, professional advisor. Write flowing, empathetic, journalistic paragraphs, "
            "no bullet lists and no numeric KPIs. Mention GDPR, ePrivacy, DSA and the EU‑AI‑Act where relevant. "
            "Never output code, or placeholders like {{...}} or {%...%}, no tables.")

def _load_prompts(lang: str) -> Dict[str,str]:
    names = ["prompt_prefix","executive_summary","quick_wins","risks","recommendations",
             "roadmap","vision","gamechanger","compliance","tools","foerderprogramme","prompt_suffix",
             f"prompt_additions_{'de' if lang=='de' else 'en'}"]
    out = {}
    for n in names:
        out[n] = load_prompt(n, lang, "")
    return out

def _join_user_prompt(parts: List[str]) -> str:
    return "\n\n".join([p for p in parts if p and p.strip()!=""])
# ====== Live-Box Query ========================================================
def _live_query(ctx: Dict[str,str], lang: str) -> str:
    # Branchen × Größe × Hauptleistung → knapper Query
    base = f"{ctx.get('industry','')} {ctx.get('product','')}".strip()
    size = ctx.get("company_size","")
    if lang=="de":
        return f"{base} {size} (Förderung KI OR Zuschuss KI OR Programm KI OR Tool KI OR Software KI) site:de"
    else:
        return f"{base} {size} (AI funding OR AI grant OR AI program OR AI tool OR AI software)"

def _build_live_box(ctx: Dict[str,str], lang: str) -> str:
    q = _live_query(ctx, lang)
    try:
        links = search_links(q, lang=lang)
    except Exception as e:
        log.warning("live box search failed: %s", e)
        links = []
    month = _month_year(lang)
    title = "Neu seit " + month if lang=="de" else "New since " + month
    return render_live_box_html(title, links, lang=lang)

# ====== Abschnitt-Composer ====================================================
def _compose_section(name: str, prompts: Dict[str,str], ctx: Dict[str,str], lang: str, model: Optional[str]=None) -> str:
    sys = _build_system(lang)
    user = _join_user_prompt([
        prompts.get("prompt_prefix",""),
        prompts.get(name,""),
        prompts.get("prompt_additions_de" if lang=="de" else "prompt_additions_en",""),
        prompts.get("prompt_suffix",""),
        f"\n\nKontext:\nBranche: {ctx.get('industry')}\nLeistung/Produkt: {ctx.get('product')}\n"
        f"Größe: {ctx.get('company_size')}\nStandort: {ctx.get('location')}\n"
    ])
    txt = _compose_and_call_llm(sys, user, model=model or MODEL_NAME)
    return sanitize_text(txt)

def _compose_exec_summary(prompts, ctx, lang):
    return _compose_section("executive_summary", prompts, ctx, lang, model=EXEC_SUMMARY_MODEL or MODEL_NAME)

def _compose_quick_wins(prompts, ctx, lang):      return _compose_section("quick_wins",       prompts, ctx, lang)
def _compose_risks(prompts, ctx, lang):            return _compose_section("risks",            prompts, ctx, lang)
def _compose_recommendations(prompts, ctx, lang):  return _compose_section("recommendations",  prompts, ctx, lang)
def _compose_roadmap(prompts, ctx, lang):          return _compose_section("roadmap",          prompts, ctx, lang)
def _compose_vision(prompts, ctx, lang):           return _compose_section("vision",           prompts, ctx, lang)
def _compose_gamechanger(prompts, ctx, lang):      return _compose_section("gamechanger",      prompts, ctx, lang)
def _compose_compliance(prompts, ctx, lang):       return _compose_section("compliance",       prompts, ctx, lang)
def _compose_tools(prompts, ctx, lang):            return _compose_section("tools",            prompts, ctx, lang)
def _compose_funding(prompts, ctx, lang):          return _compose_section("foerderprogramme", prompts, ctx, lang)
# ====== Public API ============================================================
def analyze_briefing(body: Dict[str,Any], lang: Optional[str] = None) -> Dict[str,Any]:
    """
    Erzeugt den Kontext für das Jinja-Template (pdf_template*.html).
    """
    lng = _lang(body, lang)
    ctx = _extract_context(body, lng)
    prompts = _load_prompts(lng)

    title = "KI‑Statusbericht" if lng=="de" else "AI Readiness Report"
    vision_title = "Vision & Leitstern" if lng=="de" else "Vision & North Star"
    game_title = "Innovation & Gamechanger" if lng=="de" else "Innovation & Gamechanger"

    # Abschnitte
    executive_summary = _compose_exec_summary(prompts, ctx, lng)
    quick_wins        = _compose_quick_wins(prompts, ctx, lng)
    risks             = _compose_risks(prompts, ctx, lng)
    recommendations   = _compose_recommendations(prompts, ctx, lng)
    roadmap           = _compose_roadmap(prompts, ctx, lng)
    vision            = _compose_vision(prompts, ctx, lng)
    gamechanger       = _compose_gamechanger(prompts, ctx, lng)
    compliance_html   = _compose_compliance(prompts, ctx, lng)
    tools_html        = _compose_tools(prompts, ctx, lng)
    funding_html      = _compose_funding(prompts, ctx, lng)

    # Live-Kasten (Tavily-first)
    live_html = _build_live_box(ctx, lng)

    # Hook/CTA
    industry_hook = _industry_hook(ctx, lng)
    footer_cta = ("Ihre Meinung zählt: Feedback geben (kurz)" 
                  if lng=="de" else "Your opinion matters: Give feedback (short)")

    # Rückgabe: Kontext-Dict für Template
    return {
        "title": title,
        "company": ctx.get("company") or "",
        "industry": ctx.get("industry"),
        "product": ctx.get("product"),
        "company_size": ctx.get("company_size"),
        "location": ctx.get("location"),

        "industry_hook": industry_hook,

        "executive_summary": executive_summary,
        "quick_wins": quick_wins,
        "risks": risks,
        "recommendations": recommendations,
        "roadmap": roadmap,
        "vision_title": vision_title,
        "vision": vision,
        "game_title": game_title,
        "gamechanger": gamechanger,

        "compliance_html": compliance_html,
        "funding_html": funding_html,
        "tools_html": tools_html,

        "live_box_html": live_html,            # optional, falls Template es anzeigen soll
        "stand_datum": _month_year(lng),
        "footer_cta": footer_cta,
    }
# ====== CLI-Quicktest =========================================================
if __name__ == "__main__":
    sample = {
        "lang": "de",
        "industry": "Beratung",
        "hauptleistung": "Beratung zu KI‑Fähigkeiten und KI‑Automatisierung für Unternehmen",
        "company_size": "KMU",
        "location": "Deutschland",
        "company": "Beispiel GmbH"
    }
    out = analyze_briefing(sample, lang="de")
    print(json.dumps({k: (v[:200]+"..." if isinstance(v,str) and len(v)>220 else v) for k,v in out.items()}, ensure_ascii=False, indent=2))
