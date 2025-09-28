# gpt_analyze.py — Gold-Standard Ready (2025-09-28)
# Ziel
# ----
# Narrative KI-Statusberichte ohne Zahlen & ohne Bullet-Listen.
# - Prompts werden ausschließlich aus `prompts/` geladen (kein intransparenter Fallback).
# - HTML wird über `templates/pdf_template.html` gerendert.
# - Förderprogramme/Tools zusätzlich als kurze narrative Absätze (neben evtl. vorhandenen Tabellen).
# - Compliance-Abschnitt wird immer bereitgestellt (LLM-Output oder narrativer Fallback).
# - Sanfte/abschaltbare Quality-Control (standardmäßig AUS).
# - Ausführliches, aber schlankes Logging (Diagnostics im HTML-Kommentar).
#
# Beibehalt der externen Schnittstelle:
#   analyze_briefing(body: dict, lang: str="de") -> str (HTML)

from __future__ import annotations

import os
import re
import json
import time
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
PDF_TEMPLATE_NAME = os.getenv("PDF_TEMPLATE_NAME", "pdf_template.html")

DEFAULT_LANG = "de"
SUPPORTED_LANGS = {"de", "en"}

# Quality-Control (weich/abschaltbar)
QUALITY_CONTROL_AVAILABLE = str(os.getenv("QUALITY_CONTROL_AVAILABLE", "false")).lower() in {"1","true","yes","on"}
MIN_QUALITY_SCORE = int(os.getenv("MIN_QUALITY_SCORE", "30"))

# Logging
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
logger = logging.getLogger("gpt_analyze")

# Optional: OpenAI/HTTPX
_openai_client = None
_httpx = None
try:
    import openai
    _openai_client = openai
except Exception:
    pass

if _openai_client is None:
    try:
        import httpx
        _httpx = httpx
    except Exception:
        _httpx = None

# ---------------------------------------------------------------------------
# Jinja: Filters
# ---------------------------------------------------------------------------

def filter_min(a, b):
    try:
        return min(a, b)
    except Exception:
        return a

def filter_max(a, b):
    try:
        return max(a, b)
    except Exception:
        return a

def filter_round(v, p=0):
    try:
        return round(float(v), int(p))
    except Exception:
        return v

def filter_currency(v, symbol="€"):
    try:
        s = f"{int(float(v)):,}".replace(",", ".")
        return f"{s} {symbol}"
    except Exception:
        return str(v)

def filter_nl2p(text: str) -> str:
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", str(text).strip())
    return "\n".join(f"<p>{b.strip()}</p>" for b in blocks if b.strip())

def filter_safe_join(items: List[str], sep=", "):
    try:
        return sep.join([str(i) for i in items if i])
    except Exception:
        return ""

def setup_jinja_env(templates_dir: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["min"] = filter_min
    env.filters["max"] = filter_max
    env.filters["round"] = filter_round
    env.filters["currency"] = filter_currency
    env.filters["nl2p"] = filter_nl2p
    env.filters["safe_join"] = filter_safe_join
    return env

# ---------------------------------------------------------------------------
# Prompt-Engine (strict: nur PROMPTS_DIR)
# ---------------------------------------------------------------------------

class PromptProcessor:
    def __init__(self, prompts_dir: str = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        if not os.path.isdir(self.prompts_dir):
            raise FileNotFoundError(f"Prompts-Verzeichnis fehlt: {self.prompts_dir}")
        self.env = Environment(
            loader=FileSystemLoader(self.prompts_dir),
            autoescape=False,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _resolve_path(self, prompt_name: str, lang: str) -> str:
        lang = (lang or DEFAULT_LANG).lower()
        candidates = [
            os.path.join(self.prompts_dir, lang, f"{prompt_name}.md"),
            os.path.join(self.prompts_dir, f"{prompt_name}_{lang}.md"),
            os.path.join(self.prompts_dir, f"{prompt_name}.md"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return os.path.relpath(c, self.prompts_dir)
        raise FileNotFoundError(f"Prompt nicht gefunden: {prompt_name} (lang={lang}) in {self.prompts_dir}")

    def render(self, prompt_name: str, variables: Dict[str, Any], lang: str) -> str:
        rel = self._resolve_path(prompt_name, lang)
        tpl = self.env.get_template(rel)
        return tpl.render(**variables)

prompt_processor = PromptProcessor()

# ---------------------------------------------------------------------------
# Variablen & Validierung
# ---------------------------------------------------------------------------

def _label_company_size(sz: Optional[str]) -> str:
    if not sz: return "ein mittelständisches Unternehmen"
    s = str(sz).lower()
    if "klein" in s or "small" in s: return "ein kleines Unternehmen"
    if "groß" in s or "large" in s: return "ein großes Unternehmen"
    if "micro" in s or "solo" in s: return "ein sehr kleines Unternehmen"
    return "ein mittelständisches Unternehmen"

def _pick(d: Dict[str, Any], *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default

def _budget_from_string(budget_str: Optional[str]) -> Optional[int]:
    if not budget_str:
        return None
    s = str(budget_str).strip().lower().replace("€","").replace(" ", "")
    mapping = {
        "unter2000": 1500, "unter_2000": 1500, "unter-2000": 1500,
        "2000-10000": 6000, "2.000-10.000": 6000,
        "10000-50000": 25000, "10.000-50.000": 25000,
        "50000-100000": 75000, "50.000-100.000": 75000,
        "ueber50000": 75000, "über50.000": 75000, "über_50000": 75000
    }
    for k, v in mapping.items():
        if k in s or s in k:
            return v
    # Freiform -> erste Zahl
    m = re.findall(r"\d{3,}", s)
    if m:
        try: return int(m[0])
        except Exception: pass
    return None

def get_template_variables(body: Dict[str, Any], lang: str) -> Dict[str, Any]:
    meta = body.get("meta", {}) if isinstance(body, dict) else {}
    form = body.get("form", {}) if isinstance(body, dict) else {}

    branche = _pick(body, "branche", default=_pick(meta, "branche", default="Ihre Branche"))
    company_size = _pick(body, "company_size", "unternehmensgroesse",
                         default=_pick(meta, "company_size", default="Mittelstand"))
    bundesland = _pick(body, "bundesland", default=_pick(meta, "bundesland", default=""))

    budget_str = _pick(body, "budget", "investitionsbudget",
                       default=_pick(form, "budget", default="2000-10000"))
    budget_amount = _budget_from_string(budget_str)

    # Basis
    v: Dict[str, Any] = {
        "lang": (lang or DEFAULT_LANG).lower(),
        "today": datetime.utcnow().strftime("%Y-%m-%d"),
        "datum": datetime.utcnow().strftime("%d.%m.%Y"),   # praktisch fürs Template statt now()
        "report_version": _pick(body, "report_version", default=_pick(meta, "report_version", default="GS-1.0")),
        "branche": branche,
        "bundesland": bundesland,
        "company_size_label": _label_company_size(company_size),
        "unternehmensgroesse": company_size,
        "budget": budget_str,
        "budget_amount": budget_amount,
        "feedback_link": _pick(body, "feedback_link", default=_pick(meta, "feedback_link", default="")),
        # Collections
        "funding_programs": body.get("funding_programs") or [],
        "tools": body.get("tools") or [],
    }

    # Robuste Defaults für Prompts/Templates (aus deinen Logs abgeleitet)
    v.setdefault("ki_usecases", body.get("ki_usecases") or [])
    v.setdefault("kpi_compliance", "")
    v.setdefault("kpi_roi_months", "")
    v.setdefault("roi_investment", "")
    v.setdefault("datenschutzbeauftragter", "")
    v.setdefault("score_percent", None)  # None => KPI-Widgets im Template bleiben aus
    v.setdefault("digitalisierungsgrad", body.get("digitalisierungsgrad") or 0)
    v.setdefault("automatisierungsgrad", body.get("automatisierungsgrad") or "")
    v.setdefault("risikofreude", body.get("risikofreude") or 0)
    v.setdefault("copyright_year", datetime.utcnow().year)

    return v


# ---------------------------------------------------------------------------
# Quality Control (sanft / optional)
# ---------------------------------------------------------------------------

def _strip_lists_and_numbers(html: str) -> str:
    if not html: return ""
    # Entferne UL/OL/LI
    html = re.sub(r"</?\s*(ul|ol|li)[^>]*>", "", html, flags=re.I)
    # Entferne % und nackte Zahlen (grobe Heuristik), aber belasse Worte
    html = re.sub(r"\b\d{1,3}([.,]\d+)?\s*%?", "", html)
    # Whitespace normalisieren
    html = re.sub(r"\s{2,}", " ", html).strip()
    return html

def apply_quality_control(section_name: str, html: str) -> Dict[str, Any]:
    score = 0
    issues = []
    if not html or len(re.sub(r"\s+","", html)) < 80:
        score += 10; issues.append("too_short")
    if re.search(r"<\s*(ul|ol|li)\b", html or "", re.I):
        score += 20; issues.append("list_tags")
    if re.search(r"%|\b\d{1,3}(?:[.,]\d+)?\b", html or ""):
        score += 20; issues.append("numbers")

    kept = True
    final_text = html
    if QUALITY_CONTROL_AVAILABLE:
        kept = score < MIN_QUALITY_SCORE
        if not kept:
            final_text = _strip_lists_and_numbers(html)

    return {"section": section_name, "overall_score": score, "issues": issues, "kept": kept, "final_text": final_text}

# ---------------------------------------------------------------------------
# GPT/LLM-Aufruf
# ---------------------------------------------------------------------------

def call_gpt_api(prompt: str, section_name: str, lang: str="de") -> Optional[str]:
    system_de = (
        "Du bist ein KI-Strategieberater. "
        "Erstelle warmen, seriösen HTML-Fließtext in <p>-Absätzen. "
        "Keine Bullet-Listen, keine Zahlen oder Prozente, keine Tabellen. "
        "Kurze Absätze (3–5 Sätze), klare Bilder, konkrete Wirkung."
    )
    system_en = (
        "You are an AI strategy consultant. "
        "Write warm, trustworthy HTML paragraphs (<p>). "
        "No lists, no numbers/percentages, no tables. "
        "Use short, vivid, precise paragraphs."
    )
    system = system_de if (lang or "de").startswith("de") else system_en

    # OpenAI SDK v1
    if _openai_client and hasattr(_openai_client, "chat"):
        try:
            resp = _openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
                temperature=0.6,
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS","1200"))
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"OpenAI chat.completions Fehler [{section_name}]: {e}")

    # OpenAI SDK v0 (legacy)
    if _openai_client and hasattr(_openai_client, "ChatCompletion"):
        try:
            resp = _openai_client.ChatCompletion.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
                temperature=0.6,
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS","1200"))
            )
            return (resp["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            logger.warning(f"OpenAI ChatCompletion Fehler [{section_name}]: {e}")

    # HTTPX Rest
    if _httpx:
        api_key = os.getenv("OPENAI_API_KEY","")
        if api_key:
            try:
                headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}
                payload={
                    "model":os.getenv("OPENAI_MODEL","gpt-4o-mini"),
                    "messages":[{"role":"system","content":system},{"role":"user","content":prompt}],
                    "temperature":0.6,
                    "max_tokens":int(os.getenv("OPENAI_MAX_TOKENS","1200"))
                }
                url = os.getenv("OPENAI_CHAT_URL","https://api.openai.com/v1/chat/completions")
                r = _httpx.post(url, headers=headers, json=payload, timeout=60)
                r.raise_for_status()
                data = r.json()
                return (data["choices"][0]["message"]["content"] or "").strip()
            except Exception as e:
                logger.warning(f"HTTPX OpenAI Fehler [{section_name}]: {e}")

    return None

# ---------------------------------------------------------------------------
# Fallbacks (narrativ)
# ---------------------------------------------------------------------------

def _p(*lines: str) -> str:
    return "\n".join(f"<p>{l.strip()}</p>" for l in lines if l and l.strip())

def fallback_text(section: str, v: Dict[str,Any], lang: str) -> str:
    de = lang.startswith("de")
    if section == "executive_summary":
        return _p(
            f"Ihr Unternehmen ist {v.get('company_size_label','ein Unternehmen')} in {v.get('branche','Ihrer Branche')}.",
            "KI kann hier leise Ordnung schaffen: Informationen sind schneller auffindbar, Entwürfe entstehen im Hintergrund und Gespräche werden konkreter.",
            "Wir beginnen behutsam mit einem klaren Anwendungsfall, festen Leitplanken und einem offenen Feedbackkanal."
        ) if de else _p(
            f"Your organisation is {v.get('company_size_label','an organisation')} in {v.get('branche','your industry')}.",
            "AI can quietly bring order: information is easier to find, drafts appear in the background and conversations become more concrete.",
            "We start small with a clear use case, guardrails and an open feedback loop."
        )
    if section == "quick_wins":
        return _p(
            "Eine kurze Dateninventur schafft Orientierung: Wo liegen welche Informationen und wer pflegt sie.",
            "Ein kleiner Probelauf mit klarer Freigabe zeigt zügig Nutzen – ohne die gewohnten Abläufe zu stören."
        ) if de else _p(
            "A short data inventory brings orientation: where data lives and who curates it.",
            "A small pilot with clear approval shows value quickly without disrupting routines."
        )
    if section in ("risks","haupt_risiken"):
        return _p(
            "Wesentlich sind klare Rechtsgrundlagen, Rollen und nachvollziehbare Entscheidungen.",
            "Mit leichter Governance, Pseudonymisierung und Reviews bleiben Risiken beherrschbar."
        ) if de else _p(
            "Legal clarity, roles and traceable decisions matter most.",
            "With light governance, pseudonymisation and short reviews risks stay manageable."
        )
    if section in ("recommendations","empfehlungen"):
        return _p(
            "Definieren Sie mit dem Fachbereich einen greifbaren Nutzenfall und einfache Erfolgskriterien.",
            "Bilden Sie ein kleines Kernteam, dokumentieren Sie Entscheidungen und halten Sie den Feedbackkanal offen."
        ) if de else _p(
            "Agree on a practical value case and simple success criteria with the business team.",
            "Form a small core team, document decisions and keep a feedback channel open."
        )
    if section == "roadmap":
        return _p(
            "Kurzfristig: Orientierung mit Policy‑Entwurf, Dateninventur und sicherem Probebetrieb.",
            "Mittelfristig: Rollen klären, Dokumentation vereinbaren und Bausteine wiederverwendbar machen.",
            "Langfristig: Plattform, Leitplanken und ruhige Qualifizierung für den breiten Einsatz."
        ) if de else _p(
            "Short term: orientation with policy draft, data inventory and safe pilot.",
            "Medium term: clarify roles, agree documentation and make components reusable.",
            "Long term: platform, guardrails and steady upskilling for broad adoption."
        )
    if section in ("funding","foerderprogramme"):
        return _p(
            "Programme auf Landes‑ und Bundesebene können den Einstieg erleichtern.",
            "Eine kurze Projektskizze mit Zielbild, Arbeitspaketen und Verantwortlichkeiten erhöht die Chancen."
        ) if de else _p(
            "State and federal programmes can ease the entry.",
            "A short project outline with goal, work packages and responsibilities raises approval chances."
        )
    if section in ("tools","ki_tools"):
        return _p(
            "Wählen Sie wenige, robuste Werkzeuge mit klarer Zuständigkeit.",
            "Ein gemeinsamer Arbeitsraum und schmaler Freigabeprozess verhindern Tool‑Wildwuchs."
        ) if de else _p(
            "Pick a few robust tools with clear ownership.",
            "A shared workspace and a light approval process prevent tool sprawl."
        )
    if section in ("vision","leitidee"):
        return _p(
            "Leitidee: Eine kuratierte Wissenswerkstatt, in der sichere KI‑Assistenzen den Alltag entlasten.",
            "Sie bringt Orientierung, Wiederverwendbarkeit und Ruhe in die Arbeit – ohne die Sorgfalt zu verlieren."
        ) if de else _p(
            "Guiding idea: a curated knowledge workshop where safe AI assistants ease daily work.",
            "It brings orientation, reuse and calm without losing diligence."
        )
    if section in ("compliance","recht"):
        return _p(
            "Compliance ist das Geländer: Zweckbindung, Pseudonymisierung, Rollen und dokumentierte Freigaben.",
            "Eine kurze Datenschutz‑Folgenabschätzung vor dem Start verhindert spätere Blockaden."
        ) if de else _p(
            "Compliance is the handrail: purpose limitation, pseudonymisation, roles and documented approvals.",
            "A short data‑protection impact assessment before launch prevents later roadblocks."
        )
    return _p("Narrativer Abschnitt wird bereitgestellt.")

# ---------------------------------------------------------------------------
# Funding & Tools: narrative builder (optional zu Tabellen)
# ---------------------------------------------------------------------------

def build_funding_rich_html(programs: List[Dict[str,Any]], lang: str) -> str:
    if not programs: return ""
    de = lang.startswith("de")
    out = ["<div>"]
    for p in programs[:5]:
        name = p.get("name") or p.get("programm") or ""
        target = p.get("target") or p.get("zielgruppe") or ("Unternehmen" if de else "organisations")
        region = p.get("region") or p.get("bundesland") or ("deutschlandweit" if de else "nationwide")
        purpose = p.get("purpose") or p.get("zweck") or ("digitale Kompetenzen" if de else "digital capabilities")
        line = f"<p><b>{name}</b>: "
        if de:
            line += f"geeignet für {target}, ausgerichtet auf {purpose}; verfügbar {region}."
        else:
            line += f"suitable for {target}, focused on {purpose}; available {region}."
        line += "</p>"
        out.append(line)
    out.append("</div>")
    return "\n".join(out)

def build_tools_rich_html(tools: List[Dict[str,Any]], lang: str) -> str:
    if not tools: return ""
    de = lang.startswith("de")
    out = ["<div>"]
    for t in tools[:6]:
        name = t.get("name") or ""
        use = t.get("usecase") or t.get("einsatz") or ("Ideation/Assistenz" if de else "ideation/assistance")
        dp = t.get("datenschutz") or t.get("data_location") or ("EU/DSGVO‑freundlich" if de else "EU/GDPR‑friendly")
        price = t.get("cost") or t.get("price_tier") or ("moderat" if de else "moderate")
        line = f"<p><b>{name}</b>: "
        if de:
            line += f"{use}; Datenschutz: {dp}; Kostenrahmen: {price}."
        else:
            line += f"{use}; data protection: {dp}; price tier: {price}."
        line += "</p>"
        out.append(line)
    out.append("</div>")
    return "\n".join(out)

# ---------------------------------------------------------------------------
# Sektionserzeugung
# ---------------------------------------------------------------------------

def should_use_gpt(prompt_name: str) -> bool:
    return prompt_name not in {"funding_table","tools_table","glossary"}

def generate_section_with_prompt(prompt_name: str, variables: Dict[str,Any], lang: str) -> str:
    prompt_text = ""
    try:
        prompt_text = prompt_processor.render(prompt_name, variables, lang)
    except Exception as e:
        logger.warning(f"Prompt-Rendering fehlgeschlagen [{prompt_name}]: {e}")
        return fallback_text(prompt_name, variables, lang)

    txt = None
    if should_use_gpt(prompt_name) and (_openai_client or _httpx):
        txt = call_gpt_api(prompt_text, prompt_name, lang)
        if txt:
            qc = apply_quality_control(prompt_name, txt)
            if qc["kept"] and len(re.sub(r"\s+","", qc["final_text"])) > 150:
                return qc["final_text"]

    return fallback_text(prompt_name, variables, lang)

# ---------------------------------------------------------------------------
# Haupt-API
# ---------------------------------------------------------------------------

def analyze_briefing(body: Dict[str,Any], lang: str=DEFAULT_LANG) -> str:
    """
    Baut den HTML-Report und rendert das PDF-Template.
    """
    t0 = time.time()
    lang = (lang or DEFAULT_LANG).lower()
    env = setup_jinja_env(TEMPLATES_DIR)
    tmpl = env.get_template(PDF_TEMPLATE_NAME)

    v = get_template_variables(body or {}, lang)

    diagnostics = {
        "lang": lang,
        "gpt_calls": 0,
        "fallbacks_used": 0,
        "sections": [],
        "errors": [],
        "qc": {"enabled": QUALITY_CONTROL_AVAILABLE, "min_score": MIN_QUALITY_SCORE},
    }

    def _gen(name: str) -> str:
        nonlocal diagnostics
        if should_use_gpt(name) and (_openai_client or _httpx):
            diagnostics["gpt_calls"] += 1
        try:
            txt = generate_section_with_prompt(name, v, lang)
            if txt == "" or "Narrativer Abschnitt" in txt:
                diagnostics["fallbacks_used"] += 1
            diagnostics["sections"].append(name)
            return txt
        except Exception as e:
            diagnostics["errors"].append(f"{name}: {e}")
            diagnostics["fallbacks_used"] += 1
            return fallback_text(name, v, lang)

    # Narrative Abschnitte
    ctx: Dict[str,Any] = {
        "lang": lang,
        "today": v["today"],
        "report_version": v["report_version"],
        "executive_summary_html": _gen("executive_summary"),
        "quick_wins_html": _gen("quick_wins"),
        "risks_html": _gen("risks"),
        "recommendations_html": _gen("recommendations"),
        "roadmap_html": _gen("roadmap"),
        "compliance_html": _gen("compliance"),
        "vision_html": _gen("vision"),
        "gamechanger_html": _gen("gamechanger"),
        # Rohdaten/Listen zur optionalen Tabelle
        "funding_programs": v.get("funding_programs") or [],
        "tools": v.get("tools") or [],
        # Narrative Kurzbeschreibungen zusätzlich
        "funding_rich_html": build_funding_rich_html(v.get("funding_programs") or [], lang),
        "dynamic_funding_html": build_funding_rich_html(v.get("funding_programs") or [], lang),
        "tools_rich_html": build_tools_rich_html(v.get("tools") or [], lang),
        # Feedback-Link
        "feedback_link": v.get("feedback_link",""),
    }

    # Post-Processing: Vision-Heading modernisieren (ohne "Kühne Idee")
    vh = ctx.get("vision_html","")
    vh = re.sub(r"<h3>\\s*Kühne\\s+Idee\\s*</h3>", "<h3>Leitidee</h3>" if lang=="de" else "<h3>Guiding Idea</h3>", vh, flags=re.I)
    ctx["vision_html"] = vh

    # Diagnostics als unsichtbarer HTML-Kommentar anhängen
    diag = {"elapsed_s": round(time.time()-t0,2), **diagnostics}
    ctx["diagnostics_comment"] = f"<!-- diagnostics: {json.dumps(diag, ensure_ascii=False)} -->"

    html = tmpl.render(**ctx)
    return html
