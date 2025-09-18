# gpt_analyze.py — Gold-Standard (2025-09-18 HF2)
# - Prompts-first (./prompts/de|en/*.md)
# - OpenAI mit Modell-Fallback (gpt-5 → gpt-4o → gpt-4o-mini → 3.5 …)
# - Live-Kasten: Tavily first (SerpAPI Fallback) via websearch_utils.search_links
# - Liefert Kontext-Dict für Jinja-Templates (pdf_template*.html)

from __future__ import annotations
import os, json, csv, time, logging, datetime as dt
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

# bevorzugte Modelle (werden im Code alias-bereinigt)
MODEL_NAME         = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini").strip()
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", MODEL_NAME).strip()
SUMMARY_MODEL_NAME = os.getenv("SUMMARY_MODEL_NAME", MODEL_NAME).strip()

TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.3"))
MAX_TOKENS  = int(os.getenv("GPT_MAX_TOKENS", "1400"))
DEFAULT_LANG = (os.getenv("DEFAULT_LANG", "de") or "de").lower()

# ====== Websuche-Import MIT GUARD ============================================
# Robust gegen ältere/beschädigte websearch_utils.py-Versionen.
# Falls einzelne Funktionen fehlen, stellen wir Minimal-Fallbacks bereit,
# damit das Modul IMMER importierbar bleibt (keine "Analysemodul nicht geladen"-PDFs).
try:
    from websearch_utils import search_links, live_query_for, render_live_box_html
except Exception as e:
    log.warning("websearch_utils import failed (%s) – using in-process fallbacks", e)
    # search_links versuchen wir separat zu importieren; wenn auch das fehlschlägt → No-Op.
    try:
        from websearch_utils import search_links  # type: ignore
    except Exception:
        def search_links(query: str, **kwargs) -> List[Dict[str, Any]]:  # type: ignore
            return []

    def live_query_for(industry: str, size: str, product: str, lang: str = "de") -> str:  # type: ignore
        ind = (industry or "").strip()
        siz = (size or "").strip()
        prod = (product or "").strip()
        if (lang or "de").lower().startswith("de"):
            # site:de hält Treffer nahe D/A/CH
            return f'{ind} {prod} Mittelstand {siz} (Förderung KI OR Zuschuss KI OR Programm KI OR Tool KI OR Software KI) site:de'
        return f'{ind} {prod} SME {siz} (AI grant OR subsidy OR program OR funding OR AI tool OR software)'

    def render_live_box_html(items: List[Dict[str, Any]], lang: str = "de") -> str:  # type: ignore
        # Minimaler Platzhalter (kein Layout), falls echte Funktion nicht verfügbar ist.
        if not items:
            return ""
        month = dt.datetime.now().strftime("%B %Y")
        title = f"Neu seit {month}" if (lang or "de").lower().startswith("de") else f"New since {month}"
        lis = "".join(
            f'<li><a href="{it.get("url","")}" target="_blank" rel="noopener">{it.get("title") or it.get("domain") or it.get("url")}</a></li>'
            for it in items
        )
        return f'<div class="live-box"><strong>{title}</strong><ul>{lis}</ul></div>'

# ====== Monatsbeschriftung & kleine Helfer ===================================
MONTHS_DE = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"]

def _month_year(lang: str = "de") -> str:
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
_PROMPT_CACHE: Dict[Tuple[str, str], str] = {}

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

# === Teil 2/6 ===

def _extract_briefing(body: Dict[str, Any]) -> Dict[str,str]:
    # tolerante Keys aus DE/EN-Fragebogen
    industry = _first(body.get("branche"), body.get("industry"), body.get("sector"))
    size     = _first(body.get("unternehmensgroesse"), body.get("company_size"), body.get("size"))
    product  = _first(body.get("hauptleistung"), body.get("hauptprodukt"),
                      body.get("main_product"), body.get("main_service"))
    country  = _first(body.get("land"), body.get("country"))
    region   = _first(body.get("bundesland"), body.get("state"), body.get("region"))
    company  = _first(body.get("unternehmen"), body.get("company"), body.get("firma"))

    return {
        "industry": industry or "Beratung",
        "size": size or "KMU",
        "product": product or "Dienstleistung",
        "country": country or "Deutschland",
        "region": region or "",
        "company": company or "",
    }

# ---------- OpenAI-Model-Resolver mit Fallbackkette ----------
def _model_alias(name: str) -> str:
    name = (name or "").strip().lower()
    aliases = {
        "gpt-5": "gpt-4o",
        "gpt5": "gpt-4o",
        "gpt-5-pro": "gpt-4o",
        "gpt-5-mini": "gpt-4o-mini",
    }
    return aliases.get(name, name or "gpt-4o-mini")

def _choose_models(prefer: Optional[str] = None) -> List[str]:
    chain = [prefer, MODEL_NAME, EXEC_SUMMARY_MODEL, SUMMARY_MODEL_NAME, "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
    out, seen = [], set()
    for m in chain:
        m = _model_alias(m or "")
        if not m or m in seen: 
            continue
        seen.add(m); out.append(m)
    return out

def _call_openai(messages: List[Dict[str, Any]], prefer_model: Optional[str] = None,
                 temperature: float = TEMPERATURE, max_tokens: int = MAX_TOKENS) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    models = _choose_models(prefer_model)
    budgets = [max_tokens, int(max_tokens*0.8), int(max_tokens*0.6), 1000, 800, 600]

    with httpx.Client(http2=True, timeout=httpx.Timeout(connect=20.0, read=60.0, write=30.0, pool=60.0)) as c:
        for m in models:
            for mx in budgets:
                payload = {"model": m, "messages": messages, "max_tokens": mx}
                # Temperatur nur mitsenden, wenn sicher akzeptiert
                if not m.startswith("gpt-5"):
                    payload["temperature"] = temperature
                try:
                    r = c.post(OPENAI_ENDPOINT, headers=headers, json=payload)
                    if r.status_code == 400:
                        log.info("LLM %s refused (400) – try next", m)
                        continue
                    r.raise_for_status()
                    js = r.json()
                    return (js["choices"][0]["message"]["content"] or "").strip()
                except Exception as e:
                    log.debug("LLM %s failed (max_tokens=%s): %s", m, mx, e)
                    continue
    return ""  # harter Fallback – wird später durch Text-Fallbacks ersetzt

def _system_prompt(lang: str) -> str:
    if lang == "de":
        return ("Du bist Redakteur:in für warme, empathische Business-Reports. "
                "Schreibe als Absätze (keine Listen, keine Zahlen), "
                "qualitativ (z. B. ‚deutlich über Branchenniveau‘) und beziehe DSGVO, ePrivacy, DSA, EU-AI-Act ein.")
    return ("You write warm, empathetic business reports. "
            "Use paragraphs (no lists, no numeric KPIs), qualitative wording, "
            "and reference GDPR, ePrivacy, DSA and the EU AI Act.")

def _compose_section(lang: str, section_name: str, briefing: Dict[str,str], extras: Optional[Dict[str,Any]]=None,
                     prefer_model: Optional[str]=None) -> str:
    """Liest ./prompts/<lang>/<section_name>.md und erzeugt einen Abschnitt."""
    prefix = load_prompt("prompt_prefix", lang)
    suffix = load_prompt("prompt_suffix", lang)
    additions = load_prompt(f"prompt_additions_{'de' if lang=='de' else 'en'}", lang, "")

    prompt = load_prompt(section_name, lang, "")
    brief = (f"Branche/Industry: {briefing['industry']}\n"
             f"Unternehmensgröße/Company size: {briefing['size']}\n"
             f"Hauptleistung/Main offer: {briefing['product']}\n"
             f"Location: {briefing['country']} {briefing['region']}\n"
             f"Schreibe in Absätzen; ohne Aufzählungen und ohne Zahlenangaben.\n")
    if extras:
        brief += "\nKontext:\n" + json.dumps(extras, ensure_ascii=False)

    messages = [
        {"role":"system","content":_system_prompt(lang)},
        {"role":"user","content":f"{prefix}\n\n{prompt}\n\n{additions}\n\n{brief}\n\n{suffix}"}
    ]
    return _call_openai(messages, prefer_model=prefer_model)
# === Teil 3/6 ===

def _build_live_box(lang: str, industry: str, size: str, product: str) -> str:
    try:
        q = live_query_for(industry, size, product, lang=lang)
        items = search_links(query=q, days=int(os.getenv("SEARCH_DAYS","14")),
                             max_results=int(os.getenv("SEARCH_MAX_RESULTS","5")),
                             prefer="tavily")
        return render_live_box_html(items, lang=lang)
    except Exception as e:
        log.warning("live box failed: %s", e)
        return ""

# optionale CSV-Seeds → kompakte Tabellen als Zusatz (wenn vorhanden)
def _read_csv(path: Path) -> List[Dict[str,str]]:
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                r = csv.DictReader(f)
                return [{k:(v or "").strip() for k,v in row.items()} for row in r]
    except Exception as e:
        log.debug("csv read failed %s: %s", path, e)
    return []

def _table_html(rows: List[Dict[str,str]], cols: List[Tuple[str,str]]) -> str:
    if not rows: return ""
    thead = "".join(f"<th>{title}</th>" for _,title in cols)
    trs = []
    for r in rows[:10]:
        tds = []
        for key,_ in cols:
            val = (r.get(key) or "").strip()
            if key.endswith("_url") and val:
                val = f'<a href="{val}" target="_blank" rel="noopener">{val}</a>'
            tds.append(f"<td>{val}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return f'<div class="table-wrap"><table class="compact"><thead><tr>{thead}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'

def _seed_tables(industry: str, size: str, country_or_region: str, lang: str) -> Tuple[str,str]:
    tools_csv    = DATA_DIR.joinpath("tools.csv")
    funding_csv  = DATA_DIR.joinpath("foerderprogramme.csv")
    tools = _read_csv(tools_csv)
    funds = _read_csv(funding_csv)
    # sehr einfache Filter (optional)
    def _flt(rows, key, needle):
        if not needle: return rows
        out=[]
        n = needle.lower()
        for r in rows:
            v = (r.get(key) or "*").lower()
            if v=="*" or n in v:
                out.append(r)
        return out
    tools = _flt(tools, "industry", industry)
    tools = _flt(tools, "company_size", size)
    funds = _flt(funds, "industry", industry)
    funds = _flt(funds, "company_size", size)
    funds = _flt(funds, "region", country_or_region)

    tools_table = _table_html(tools, [
        ("name","Tool"), ("use_case","Anwendung" if lang=="de" else "Use case"),
        ("target","Zielgruppe" if lang=="de" else "Target"),
        ("cost_tier","Kosten" if lang=="de" else "Cost"),
        ("homepage_url","URL"),
    ])
    funds_table = _table_html(funds, [
        ("name","Programm"), ("what","Förderinhalt" if lang=="de" else "Scope"),
        ("target","Zielgruppe" if lang=="de" else "Target"),
        ("amount","Förderhöhe" if lang=="de" else "Amount"),
        ("info_url","Info"),
    ])
    return tools_table, funds_table

# Minimal-Fallbacks (falls LLM komplett ausfällt)
def _fallback_texts(lang: str, brief: Dict[str,str]) -> Dict[str,str]:
    if lang=="de":
        return {
            "exec": ("Auf Basis Ihrer Angaben ergeben sich praxisnahe Einstiege: "
                     "klar umrissene Workflows, saubere Datenquellen und Verfahren mit menschlicher Abnahme."),
            "risks": ("Vermeiden Sie Tool-Wildwuchs; achten Sie auf Einwilligung, Herkunft und Nachvollziehbarkeit."),
            "recs": ("Benennen Sie eine verantwortliche Person, definieren Sie Leitplanken, und starten Sie mit einem geführten Pilot."),
            "road": ("90 Tage: Datenhygiene & Pilot • 180 Tage: 2–3 Piloten skalieren • 12 Monate: Integration & Schulung."),
            "vision": ("Eine Praxis, in der KI Routinen entlastet und Menschen Qualität & Beziehung gestalten."),
            "game": ("Wissensgestützte Assistenten (RAG) und klare Feedback-Schleifen liefern spürbaren Nutzen."),
            "comp": ("<p>DSGVO, ePrivacy, DSA und EU-AI-Act: Datenminimierung, Transparenz, Logging & menschliche Aufsicht.</p>")
        }
    else:
        return {
            "exec": ("Pragmatic entries: tightly scoped workflows, clean data sources and human approvals."),
            "risks": ("Avoid tool sprawl; keep consent, provenance and auditability visible."),
            "recs": ("Name an owner, set guardrails and start with one guided pilot."),
            "road": ("90 days: hygiene & pilot • 180 days: scale 2–3 pilots • 12 months: integration & training."),
            "vision": ("AI relieves routine; people deliver quality and relationship."),
            "game": ("RAG assistants and tight feedback loops create tangible value."),
            "comp": ("<p>GDPR, ePrivacy, DSA, EU AI Act: minimisation, transparency, logging & human oversight.</p>")
        }
# === Teil 4/6 ===

def _compose_all_sections(lang: str, brief: Dict[str,str]) -> Dict[str,str]:
    out: Dict[str,str] = {}
    out["executive_summary"] = _compose_section(lang, "executive_summary", brief, prefer_model=EXEC_SUMMARY_MODEL)
    out["quick_wins"]        = _compose_section(lang, "quick_wins", brief)
    out["risks"]             = _compose_section(lang, "risks", brief)
    out["recommendations"]   = _compose_section(lang, "recommendations", brief)
    out["roadmap"]           = _compose_section(lang, "roadmap", brief)
    out["vision"]            = _compose_section(lang, "vision", brief)
    out["gamechanger"]       = _compose_section(lang, "gamechanger", brief)
    out["compliance_html"]   = _compose_section(lang, "compliance", brief)
    return out

def _ensure_minimum(out: Dict[str,str], lang: str, brief: Dict[str,str]) -> Dict[str,str]:
    fb = _fallback_texts(lang, brief)
    out["executive_summary"] = out.get("executive_summary") or fb["exec"]
    out["quick_wins"]        = out.get("quick_wins")        or fb["exec"]
    out["risks"]             = out.get("risks")             or fb["risks"]
    out["recommendations"]   = out.get("recommendations")   or fb["recs"]
    out["roadmap"]           = out.get("roadmap")           or fb["road"]
    out["vision"]            = out.get("vision")            or fb["vision"]
    out["gamechanger"]       = out.get("gamechanger")       or fb["game"]
    out["compliance_html"]   = out.get("compliance_html")   or fb["comp"]
    return out

def _hook_sentence(industry: str, lang: str) -> str:
    return (f"{industry}: Wo KI heute pragmatisch Nutzen stiftet — und wo Vorsicht hilft."
            if lang=="de" else
            f"{industry}: where AI creates practical value today — and where caution pays off.")

def _blend_live_and_seeds(lang: str, brief: Dict[str,str], out: Dict[str,str]) -> Dict[str,str]:
    # Live-Kasten (immer Zusatz)
    live_html = _build_live_box(lang, brief["industry"], brief["size"], brief["product"])
    if live_html:
        out["live_box_html"] = live_html

    # optionale Tabellen aus data/*.csv
    tools_table, funds_table = _seed_tables(brief["industry"], brief["size"], brief["country"] or brief["region"], lang)
    if tools_table:
        out["tools_html"] = (out.get("tools_html","") + tools_table)
    if funds_table:
        out["foerderprogramme_html"] = (out.get("foerderprogramme_html","") + funds_table)
    return out
# === Teil 5/6 ===

def analyze_briefing(body: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Haupteinstieg — liefert ein Kontext-Dict für Jinja.
    Keine Jinja-Reste in Strings; alle Abschnitte sind befüllt (LLM oder Fallback).
    """
    L = _lang(body or {}, lang)
    brief = _extract_briefing(body or {})
    try:
        sections = _compose_all_sections(L, brief)  # Prompts-first → LLM
    except Exception as e:
        log.exception("LLM composition failed: %s", e)
        sections = {}

    sections = _ensure_minimum(sections, L, brief)  # nie leer
    sections = _blend_live_and_seeds(L, brief, sections)

    ctx: Dict[str, Any] = {
        "title": "KI-Statusbericht" if L=="de" else "AI Readiness Report",
        "lang": L,
        "company": brief["company"],
        "industry": brief["industry"],
        "company_size": brief["size"],
        "main_product": brief["product"],
        "country": brief["country"],
        "region": brief["region"],
        "month_year": _month_year(L),
        "hook": _hook_sentence(brief["industry"], L),

        "executive_summary": sections["executive_summary"],
        "quick_wins": sections["quick_wins"],
        "risks": sections["risks"],
        "recommendations": sections["recommendations"],
        "roadmap": sections["roadmap"],
        "vision": sections["vision"],
        "gamechanger": sections["gamechanger"],
        "compliance_html": sections["compliance_html"],

        "foerderprogramme_html": sections.get("foerderprogramme_html",""),
        "tools_html": sections.get("tools_html",""),
        "live_box_html": sections.get("live_box_html",""),

        "stand_datum": _month_year(L),
        "cta_text": "Ihre Meinung zählt: Feedback geben (kurz)" if L=="de" else "Your opinion matters: Give feedback (short)",
        "report_version": "GS-2025-09-18-HF2",
    }
    return ctx
# === Teil 6/6 ===

def _selftest() -> Dict[str, Any]:
    try:
        ok = []
        for lang in ("de","en"):
            for name in ("prompt_prefix","prompt_suffix","executive_summary","quick_wins",
                         "risks","recommendations","roadmap","vision","gamechanger","compliance","tools","foerderprogramme"):
                ok.append(_pfile(lang, name).exists())
        return {"ok": all(ok), "found": sum(1 for x in ok if x)}
    except Exception as e:
        return {"ok": False, "error": repr(e)}

if __name__ == "__main__":
    sample = {"lang":"de","branche":"Beratung","unternehmensgroesse":"KMU",
              "hauptleistung":"KI-Automatisierung","country":"Deutschland","company":"Beispiel GmbH"}
    out = analyze_briefing(sample, "de")
    # nur Kurz-Dump (kein HTML rendern – das macht Jinja in main.py)
    print(json.dumps({k:(v[:120]+"…") if isinstance(v,str) and len(v)>120 else v for k,v in out.items()},
                     ensure_ascii=False, indent=2))
