# gpt_analyze.py  —  Gold-Standard (2025-09-18)
# Lädt Prompts aus ./prompts/<lang>/..., generiert narrative Abschnitte,
# baut Live-Kasten via Tavily (Fallback: SerpAPI), liefert Kontext für Jinja.
from __future__ import annotations
import os, json, time, logging, hashlib, httpx, datetime as dt
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

# --- Logging ------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s %(asctime)s [analyze] %(message)s")
log = logging.getLogger("analyze")

# --- ENV ----------------------------------------------------------------------
OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY", "").strip()
MODEL_NAME           = os.getenv("GPT_MODEL_NAME", "gpt-4.1").strip()
EXEC_SUMMARY_MODEL   = os.getenv("EXEC_SUMMARY_MODEL", MODEL_NAME).strip()
SUMMARY_MODEL_NAME   = os.getenv("SUMMARY_MODEL_NAME", MODEL_NAME).strip()
TEMPERATURE          = float(os.getenv("GPT_TEMPERATURE", "0"))
MAX_TOKENS           = int(os.getenv("GPT_MAX_TOKENS", "1100"))

PROMPTS_DIR          = Path(os.getenv("PROMPTS_DIR", "prompts"))
DEFAULT_LANG         = os.getenv("DEFAULT_LANG", "de").lower()
COMBINE_MODE         = os.getenv("GPT_COMBINE_MODE", "single").strip()  # "single" | "multi"
TAVILY_FIRST         = True  # explizit Tavily-first

# Suche (für Live-Kasten)
from websearch_utils import search_links, live_query_for, render_live_box_html

# --- OpenAI: schlanke Wrapper + Fallbackkette --------------------------------
_OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
_FALLBACK_MODELS = [m for m in [
    MODEL_NAME,
    EXEC_SUMMARY_MODEL,
    SUMMARY_MODEL_NAME,
    "gpt-4.1",
    "gpt-4o-mini",
] if m]

def _headers():
    return {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

def _call_openai(messages: List[Dict[str, Any]], model: str = MODEL_NAME,
                 temperature: float = TEMPERATURE, max_tokens: int = MAX_TOKENS) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    to = httpx.Timeout(connect=20.0, read=60.0, write=30.0, pool=60.0)
    with httpx.Client(http2=True, timeout=to) as c:
        r = c.post(_OPENAI_ENDPOINT, headers=_headers(), json=payload)
        if r.status_code == 400:
            # häufig: Modellname ungültig → Fallback
            raise httpx.HTTPStatusError("400", request=r.request, response=r)
        r.raise_for_status()
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""

def _compose_and_call_llm(system_prompt: str, user_prompt: str,
                          prefer_model: Optional[str] = None,
                          temperature: float = TEMPERATURE,
                          max_tokens: int = MAX_TOKENS) -> str:
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]
    models = [prefer_model] + _FALLBACK_MODELS if prefer_model else list(_FALLBACK_MODELS)
    seen = set()
    for m in models:
        if not m or m in seen:
            continue
        seen.add(m)
        try:
            return _call_openai(messages, model=m, temperature=temperature, max_tokens=max_tokens)
        except httpx.HTTPStatusError as e:
            log.info("LLM %s failed: %s", m, e)
            continue
        except Exception as e:
            log.warning("LLM %s unexpected: %s", m, e)
            continue
    # letzter Fallback: kurzer Platzhalter
    return ""

# --- Prompt-Loader ------------------------------------------------------------
def _pfile(lang: str, name: str) -> Path:
    return PROMPTS_DIR / lang / f"{name}.md"

def _read_prompt(lang: str, name: str) -> str:
    fp = _pfile(lang, name)
    try:
        text = fp.read_text("utf-8")
        log.info("[PROMPT] %s <- %s", name, fp)
        return text
    except Exception:
        log.warning("[PROMPT] missing: %s", fp)
        return ""

def _lang(body: Dict[str, Any], lang: Optional[str]) -> str:
    if lang:
        return "de" if lang.lower().startswith("de") else "en"
    v = (body.get("lang") or DEFAULT_LANG or "de").lower()
    return "de" if v.startswith("de") else "en"

# --- Briefing-Parsing ---------------------------------------------------------
def _first_nonempty(*vals) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _extract_briefing(body: Dict[str, Any]) -> Dict[str, str]:
    # tolerante Feldnamen, wie in deinen Fragebögen
    industry = _first_nonempty(body.get("branche"), body.get("industry"), body.get("sector"))
    size     = _first_nonempty(body.get("groesse"), body.get("company_size"), body.get("size"))
    product  = _first_nonempty(body.get("hauptleistung"), body.get("hauptprodukt"),
                               body.get("main_product"), body.get("main_service"))
    country  = _first_nonempty(body.get("land"), body.get("country"))
    region   = _first_nonempty(body.get("bundesland"), body.get("region"), body.get("state"))

    return {
        "industry": industry or "Beratung",
        "size": size or "KMU",
        "product": product or "Dienstleistung",
        "country": country or "Deutschland",
        "region": region or "",
    }

# --- kleine Utils -------------------------------------------------------------
def _month_year_label() -> str:
    return dt.datetime.now().strftime("%B %Y")

def _mk_hook(industry: str, lang: str) -> str:
    if lang == "de":
        return f"{industry}: Wo KI heute pragmatisch Nutzen stiftet – und wo Vorsicht geboten ist."
    return f"{industry}: Where AI creates practical value today—and where caution pays off."

def _mk_system_prompt(lang: str) -> str:
    if lang == "de":
        return (
            "Du bist Redakteur:in für warmherzige, verständliche KI-Statusberichte. "
            "Schreibe stets in Absätzen, ohne Listenpunkte oder Prozentzahlen. "
            "Nenne qualitative Formulierungen (z. B. ‚deutlich über Branchenniveau‘). "
            "Beziehe DSGVO, ePrivacy, DSA und EU‑AI‑Act ein. Ton: freundlich, professionell, optimistisch."
        )
    else:
        return (
            "You are an editor for warm, human AI status reports. "
            "Write in paragraphs (no bullets, no numeric KPIs). "
            "Use qualitative wording. Always reference GDPR, ePrivacy, DSA and the EU AI Act. "
            "Tone: friendly, professional, optimistic."
        )
# === PART 2/5 ===

# --- Abschnitt-Generatoren ----------------------------------------------------
def _section_from_prompt(section: str, briefing: Dict[str, str], lang: str,
                         extra_inputs: Optional[Dict[str, Any]] = None,
                         prefer_model: Optional[str] = None,
                         temperature: float = TEMPERATURE,
                         max_tokens: int = MAX_TOKENS) -> str:
    """
    Liest z. B. 'executive_summary.md' und erzeugt narrativen Abschnitt.
    """
    sys = _mk_system_prompt(lang)
    prefix = _read_prompt(lang, "prompt_prefix")
    suffix = _read_prompt(lang, "prompt_suffix")
    additions = _read_prompt(lang, f"prompt_additions_{'de' if lang=='de' else 'en'}")

    core = _read_prompt(lang, section)
    bi = briefing
    extras = extra_inputs or {}
    user = (
        f"{prefix}\n\n"
        f"{core}\n\n"
        f"Briefing:\n"
        f"- Branche/Industry: {bi['industry']}\n"
        f"- Unternehmensgröße/Size: {bi['size']}\n"
        f"- Hauptleistung/Produkt: {bi['product']}\n"
        f"- Standort/Country-Region: {bi['country']} {bi['region']}\n"
    )
    if extras:
        user += "\nKontext:\n" + json.dumps(extras, ensure_ascii=False)
    user += f"\n\n{additions}\n\n{suffix}"

    out = _compose_and_call_llm(sys, user, prefer_model=prefer_model, temperature=temperature, max_tokens=max_tokens)
    return out or ""

def _make_live_items(briefing: Dict[str, str], lang: str, n: int = 5) -> List[Dict[str, Any]]:
    q = live_query_for(briefing["industry"], briefing["size"], briefing["product"], lang=lang)
    items = search_links(q, days=int(os.getenv("SEARCH_DAYS", "14")),
                         max_results=n, prefer="tavily")
    return items

def _render_tools_or_programs_narrative(kind: str, briefing: Dict[str, str], lang: str,
                                        live_items: List[Dict[str, Any]]) -> str:
    """
    Übergibt Live-Snippets in die Tools-/Förderprogramme-Prompts, damit
    der Text frisch & branchenbezogen ist. Erzwingt Absätze statt Liste.
    """
    sys = _mk_system_prompt(lang)
    section = "tools" if kind == "tools" else "foerderprogramme"
    prompt = _read_prompt(lang, section)
    hint = (
        "Formatiere als kurze, dichte Absätze (keine Listen). "
        "Erläutere Zielgruppe, typische Eignung und grobe Kostenordnung (nicht numerisch). "
        "Beziehe dich nur auf die relevanten Snippets; keine Halluzinationen."
    ) if lang == "de" else (
        "Write compact paragraphs (no lists). Mention audience, typical suitability and rough cost ranges "
        "(qualitative only). Use only facts reflected in the snippets; avoid hallucinations."
    )
    user = (
        f"{prompt}\n\n"
        f"Briefing: {json.dumps(briefing, ensure_ascii=False)}\n\n"
        f"{hint}\n\n"
        f"Snippets:\n" + json.dumps(live_items, ensure_ascii=False)
    )
    return _compose_and_call_llm(sys, user, prefer_model=MODEL_NAME)

def _compliance_block(lang: str) -> str:
    return _section_from_prompt("compliance", {"industry":"","size":"","product":"","country":"", "region":""}, lang)

# --- Kontext → Template -------------------------------------------------------
def _context_for_template(body: Dict[str, Any], lang: str) -> Dict[str, Any]:
    lang = _lang(body, lang)
    brief = _extract_briefing(body)
    # Hook über der Executive Summary
    hook = _mk_hook(brief["industry"], lang)

    # Live-Kasten
    live_items = []
    live_html  = ""
    try:
        live_items = _make_live_items(brief, lang, n=5)
        live_html  = render_live_box_html(live_items, lang=lang)
    except Exception as e:
        log.warning("Live box failed: %s", e)
        live_items = []
        live_html  = ""

    # Abschnitte
    exec_sum = _section_from_prompt("executive_summary", brief, lang, prefer_model=EXEC_SUMMARY_MODEL)
    quick    = _section_from_prompt("quick_wins", brief, lang)
    risks    = _section_from_prompt("risks", brief, lang)
    recs     = _section_from_prompt("recommendations", brief, lang)
    roadmap  = _section_from_prompt("roadmap", brief, lang)
    vision   = _section_from_prompt("vision", brief, lang)
    gamech   = _section_from_prompt("gamechanger", brief, lang)

    # Tools & Förderprogramme → narrativ, angereichert mit Live-Snippets
    tools_html  = _render_tools_or_programs_narrative("tools", brief, lang, live_items)
    foerd_html  = _render_tools_or_programs_narrative("foerder", brief, lang, live_items)
    comp_html   = _compliance_block(lang)

    title = "KI‑Statusbericht" if lang == "de" else "AI Readiness Report"

    ctx: Dict[str, Any] = {
        "title": title,
        "lang": lang,
        "hook": hook,
        "month_year": _month_year_label(),
        "industry": brief["industry"],
        "company_size": brief["size"],
        "main_product": brief["product"],
        "country": brief["country"],
        "region": brief["region"],

        "executive_summary": exec_sum,
        "quick_wins": quick,
        "risks": risks,
        "recommendations": recs,
        "roadmap": roadmap,
        "vision": vision,
        "gamechanger": gamech,

        "live_box_html": live_html,
        "foerderprogramme_html": foerd_html,
        "tools_html": tools_html,
        "compliance_html": comp_html,

        # Footer-CTA (entschärft)
        "cta_text": "Ihre Meinung zählt: Feedback geben (kurz)" if lang == "de" else "Your opinion matters: Give feedback (short)",
        "stand_label": _month_year_label(),
    }
    return ctx
# === PART 3/5 ===

# --- Kompakt-Fallbacks (falls LLM nicht erreichbar) --------------------------
def _fallback_paragraph(lang: str, name: str, brief: Dict[str, str]) -> str:
    if lang == "de":
        return (f"{name}: Auf Basis der vorliegenden Angaben ({brief['industry']}, {brief['size']}, "
                f"{brief['product']}) werden kurzfristig pragmatische, datenschutzkonforme Schritte empfohlen, "
                "die Risiko- und Nutzenabwägungen sichtbar machen. Wo Details fehlen, bleiben Aussagen bewusst vorsichtig.")
    else:
        return (f"{name}: Based on the provided inputs ({brief['industry']}, {brief['size']}, "
                f"{brief['product']}), we recommend pragmatic, privacy‑compliant steps, "
                "with explicit risk‑benefit considerations. Where data is missing, phrasing remains cautious.")

def _ensure_min_text(txt: str, lang: str, name: str, brief: Dict[str, str]) -> str:
    t = (txt or "").strip()
    if len(t) < 120:
        return _fallback_paragraph(lang, name, brief)
    return t

# --- Public API ---------------------------------------------------------------
def analyze_briefing(body: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Haupteinstieg – synchron (wird von main.py aufgerufen).
    Gibt ein Kontext-Dict zurück; Rendering übernimmt Jinja (pdf_template*.html).
    """
    try:
        lang = _lang(body, lang)
        ctx = _context_for_template(body, lang)

        # Sicherheit: Mindestlänge der Kernabschnitte
        brief = {
            "industry": ctx.get("industry") or "",
            "size": ctx.get("company_size") or "",
            "product": ctx.get("main_product") or "",
        }
        for key, label in [
            ("executive_summary", "Executive Summary"),
            ("quick_wins", "Quick Wins"),
            ("risks", "Risiken"),
            ("recommendations", "Empfehlungen"),
            ("roadmap", "Roadmap"),
            ("vision", "Vision"),
            ("gamechanger", "Innovation & Gamechanger"),
        ]:
            ctx[key] = _ensure_min_text(ctx.get(key, ""), lang, label, brief)

        # HTML-Felder (Tools, Förder, Compliance) notfalls absichern
        for hk in ["foerderprogramme_html", "tools_html", "compliance_html", "live_box_html"]:
            if not isinstance(ctx.get(hk), str):
                ctx[hk] = ""

        return ctx
    except Exception as e:
        log.exception("analyze_briefing failed: %s", e)
        # Minimal-Kontext, damit das Template nicht leer ist
        lang = _lang(body or {}, lang)
        brief = _extract_briefing(body or {})
        return {
            "title": "KI‑Statusbericht" if lang == "de" else "AI Readiness Report",
            "lang": lang,
            "hook": _mk_hook(brief["industry"], lang),
            "month_year": _month_year_label(),
            "industry": brief["industry"],
            "company_size": brief["size"],
            "main_product": brief["product"],
            "country": brief["country"],
            "region": brief["region"],
            "executive_summary": _fallback_paragraph(lang, "Executive Summary", brief),
            "quick_wins": _fallback_paragraph(lang, "Quick Wins", brief),
            "risks": _fallback_paragraph(lang, "Risiken", brief),
            "recommendations": _fallback_paragraph(lang, "Empfehlungen", brief),
            "roadmap": _fallback_paragraph(lang, "Roadmap", brief),
            "vision": _fallback_paragraph(lang, "Vision", brief),
            "gamechanger": _fallback_paragraph(lang, "Innovation & Gamechanger", brief),
            "foerderprogramme_html": "",
            "tools_html": "",
            "compliance_html": _fallback_paragraph(lang, "Compliance", brief),
            "live_box_html": "",
            "cta_text": "Ihre Meinung zählt: Feedback geben (kurz)" if lang == "de" else "Your opinion matters: Give feedback (short)",
            "stand_label": _month_year_label(),
        }
# === PART 4/5 ===

# --- Diagnose / Selbsttest ----------------------------------------------------
def _selftest() -> Dict[str, Any]:
    """
    Kleiner Selbsttest für /diag/analyze (wird von main.py nicht direkt gebraucht,
    aber nützlich beim lokalen Testen).
    """
    try:
        ok_prompts = []
        for lang in ["de", "en"]:
            for name in [
                "prompt_prefix","prompt_suffix",f"prompt_additions_{'de' if lang=='de' else 'en'}",
                "executive_summary","quick_wins","risks","recommendations","roadmap",
                "vision","gamechanger","compliance","tools","foerderprogramme"
            ]:
                fp = _pfile(lang, name)
                ok_prompts.append(fp.exists())
        return {"ok": all(ok_prompts), "prompts_ok": sum(1 for x in ok_prompts if x)}
    except Exception as e:
        return {"ok": False, "error": repr(e)}

# --- optionale Direkt-HTML-Erzeugung (wenn Template-Rendering extern nicht greift)
def render_minimal_html(ctx: Dict[str, Any]) -> str:
    """
    Wird normalerweise nicht gebraucht (Jinja rendert in main.py).
    Ist aber praktisch für Debugging.
    """
    def _h2(t): return f'<h2 style="margin-top:24px">{t}</h2>'
    def _box(title, inner): 
        return f'<div style="border:1px solid #cfe3ff;border-radius:10px;padding:14px;margin:8px 0 16px">{_h2(title)}{inner}</div>'

    html = [
        "<!doctype html><meta charset='utf-8'><style>body{font-family:system-ui;line-height:1.5;}</style>",
        f"<h1>{ctx.get('title','')}</h1>",
        f"<p><em>{ctx.get('hook','')}</em></p>",
        _box("Executive Summary" if ctx["lang"]!="de" else "Zusammenfassung", f"<p>{ctx.get('executive_summary','')}</p>"),
        _box("Quick Wins", f"<p>{ctx.get('quick_wins','')}</p>"),
        _box("Risks" if ctx['lang']!='de' else 'Risiken', f"<p>{ctx.get('risks','')}</p>"),
        _box("Recommendations" if ctx['lang']!='de' else 'Empfehlungen', f"<p>{ctx.get('recommendations','')}</p>"),
        _box("Roadmap", f"<p>{ctx.get('roadmap','')}</p>"),
        _box("Vision", f"<p>{ctx.get('vision','')}</p>"),
        _box("Innovation & Gamechanger", f"<p>{ctx.get('gamechanger','')}</p>"),
        _box("Compliance", ctx.get('compliance_html','')),
        _box("Förderprogramme (Auswahl)" if ctx['lang']=='de' else "Funding (Selection)", ctx.get('foerderprogramme_html','')),
        _box("KI-Tools & Software" if ctx['lang']=='de' else "AI Tools & Software", ctx.get('tools_html','')),
        ctx.get("live_box_html",""),
        f"<p><strong>{ctx.get('cta_text','')}</strong></p>",
        "</body>"
    ]
    return "".join(html)
# === PART 5/5 ===

# --- Modul-Metadaten ----------------------------------------------------------
__all__ = [
    "analyze_briefing",
    "render_minimal_html",
    "_selftest",
]
