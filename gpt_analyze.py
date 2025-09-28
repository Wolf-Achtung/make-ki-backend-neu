# gpt_analyze.py — Gold-Standard Ready (2025-09-28)
# Ziel: Narrative Reports ohne Zahlen & ohne Bullet-Listen, robuste Variablen,
# lockere Quality-Control, verbesserte Fallbacks, Diagnose-Logging.
# Kompatibel zu main.py: analyze_briefing(body, lang="de") -> HTML

from __future__ import annotations
import os
import re
import json
import math
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Drittanbieter
try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
except Exception as e:
    raise RuntimeError("Jinja2 wird benötigt: pip install jinja2") from e

# Optional: OpenAI / HTTPX
_openai_client = None
_httpx = None
try:
    import openai  # Falls OpenAI-Python vorhanden ist
    _openai_client = openai
except Exception:
    try:
        import httpx
        _httpx = httpx
    except Exception:
        pass  # Kein HTTP-Klient verfügbar -> Fallback-Generator nutzen

# ------------------------------------------------------------------------------
# Konfiguration
# ------------------------------------------------------------------------------

QUALITY_CONTROL_AVAILABLE = False  # Default: aus (kann per Env überschrieben werden)
MIN_QUALITY_SCORE = int(os.getenv("MIN_QUALITY_SCORE", "30"))

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")  # nur dieses Verzeichnis, kein Fallback
PDF_TEMPLATE_NAME = os.getenv("PDF_TEMPLATE_NAME", "pdf_template.html")

# Spracheinstellungen
DEFAULT_LANG = "de"
SUPPORTED_LANGS = {"de", "en"}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gpt_analyze")

# ------------------------------------------------------------------------------
# Jinja2: Filter
# ------------------------------------------------------------------------------

def filter_min(value, *args):
    try:
        seq = [v for v in ([value] + list(args)) if v is not None]
        return min(seq) if seq else value
    except Exception:
        return value

def filter_max(value, *args):
    try:
        seq = [v for v in ([value] + list(args)) if v is not None]
        return max(seq) if seq else value
    except Exception:
        return value

def filter_round(value, ndigits: int = 0):
    try:
        return round(float(value), int(ndigits))
    except Exception:
        return value

def filter_currency(value, symbol="€"):
    try:
        v = float(value)
        # Kein Tausenderpunkt o.ä., um Sprachen konsistent zu lassen
        s = f"{int(v):,}".replace(",", ".")
        return f"{s} {symbol}"
    except Exception:
        return str(value)

def filter_nl2p(text: str) -> str:
    """Wandelt Doppel-/Einzelzeilenumbrüche in Absätze/Zeilenbrüche um."""
    if not text:
        return ""
    parts = [f"<p>{p.strip()}</p>" for p in re.split(r"\n\s*\n", str(text).strip()) if p.strip()]
    return "\n".join(parts)

def filter_safe_join(items, sep=", "):
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
    setup_jinja_filters(env)
    return env

def setup_jinja_filters(env: Environment) -> None:
    env.filters["min"] = filter_min
    env.filters["max"] = filter_max
    env.filters["round"] = filter_round
    env.filters["currency"] = filter_currency
    env.filters["nl2p"] = filter_nl2p
    env.filters["safe_join"] = filter_safe_join

# ------------------------------------------------------------------------------
# Prompt-Engine (nur prompts/)
# ------------------------------------------------------------------------------

class PromptProcessor:
    def __init__(self, prompts_dir: str = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        if not os.path.isdir(self.prompts_dir):
            raise FileNotFoundError(f"Prompts-Verzeichnis fehlt: {self.prompts_dir}")
        self.env = Environment(
            loader=FileSystemLoader(self.prompts_dir),
            autoescape=False,  # Prompts sind Text
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        setup_jinja_filters(self.env)

    def _resolve_prompt_path(self, prompt_name: str, lang: str) -> str:
        lang = (lang or DEFAULT_LANG).lower()
        # 1) /prompts/{lang}/{prompt_name}.md
        candidate = os.path.join(self.prompts_dir, lang, f"{prompt_name}.md")
        if os.path.isfile(candidate):
            return os.path.relpath(candidate, self.prompts_dir)
        # 2) /prompts/{prompt_name}_{lang}.md
        candidate = os.path.join(self.prompts_dir, f"{prompt_name}_{lang}.md")
        if os.path.isfile(candidate):
            return os.path.relpath(candidate, self.prompts_dir)
        # 3) /prompts/{prompt_name}.md
        candidate = os.path.join(self.prompts_dir, f"{prompt_name}.md")
        if os.path.isfile(candidate):
            return os.path.relpath(candidate, self.prompts_dir)
        raise FileNotFoundError(f"Prompt nicht gefunden in prompts/: {prompt_name} (lang={lang})")

    def render_prompt(self, prompt_name: str, variables: Dict[str, Any], lang: str) -> str:
        tpl_path = self._resolve_prompt_path(prompt_name, lang)
        template = self.env.get_template(tpl_path)
        return template.render(**variables)

prompt_processor = PromptProcessor()

# ------------------------------------------------------------------------------
# Hilfsfunktionen: Variablen-Ermittlung & Validierung
# ------------------------------------------------------------------------------

def get_budget_amount(body: Dict[str, Any]) -> Optional[float]:
    """
    Heuristik: versucht budget amount aus body zu finden—ohne harte Abhängigkeit.
    """
    if not isinstance(body, dict):
        return None
    # Direktfelder
    for key in ("budget_amount", "budget", "estimated_budget", "plan_budget"):
        v = body.get(key)
        if v:
            try:
                return float(v)
            except Exception:
                pass
    # Geschachtelt
    for key in ("project", "meta", "input", "survey", "form"):
        node = body.get(key) or {}
        if isinstance(node, dict):
            for k2 in ("budget_amount", "budget", "estimated_budget"):
                v = node.get(k2)
                if v:
                    try:
                        return float(v)
                    except Exception:
                        continue
    return None  # Kein Zwangswert – wir bleiben narrativ

def _label_company_size(sz):
    if not sz:
        return "ein mittelständisches Unternehmen"
    s = str(sz).lower()
    if "small" in s or "klein" in s:
        return "ein kleines Unternehmen"
    if "micro" in s or "solo" in s or "einzel" in s:
        return "ein sehr kleines Unternehmen"
    if "large" in s or "groß" in s:
        return "ein großes Unternehmen"
    return "ein mittelständisches Unternehmen"

def get_template_variables(body: Dict[str, Any], lang: str) -> Dict[str, Any]:
    now = datetime.utcnow().strftime("%Y-%m-%d")
    meta = body.get("meta", {}) if isinstance(body, dict) else {}
    branche = body.get("branche") or meta.get("branche") or "Ihre Branche"
    company_size = body.get("company_size") or meta.get("company_size") or "Mittelstand"
    score_percent = body.get("score_percent") or meta.get("score_percent")  # optional
    digitalisierungsgrad = body.get("digitalisierungsgrad") or meta.get("digitalisierungsgrad")

    variables = {
        "lang": (lang or DEFAULT_LANG).lower(),
        "today": now,
        "report_version": body.get("report_version") or meta.get("report_version") or "GS-1.0",
        "branche": branche,
        "company_size_label": _label_company_size(company_size),
        # optionale KPIs (wir nutzen sie in Prompts nicht aktiv numerisch)
        "score_percent": score_percent,
        "digitalisierungsgrad": digitalisierungsgrad,
        "budget_amount": get_budget_amount(body),
        # Flags für Template
        "has_feedback": bool(body.get("feedback_link") or meta.get("feedback_link")),
        "feedback_link": body.get("feedback_link") or meta.get("feedback_link") or "",
        # Listenquellen (falls vorhanden)
        "funding_programs": body.get("funding_programs") or [],
        "tools": body.get("tools") or [],
    }
    return validate_template_variables(variables)

def validate_template_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    """
    Härtet kritische Keys ab, setzt neutrale Defaults (narrativ, nicht-numerisch).
    """
    defaults = {
        "branche": "Ihre Branche",
        "company_size_label": "ein mittelständisches Unternehmen",
        "report_version": "GS-1.0",
        "score_percent": None,
        "digitalisierungsgrad": None,
        "budget_amount": None,
    }
    for k, v in defaults.items():
        if variables.get(k) is None:
            variables[k] = v
    # Korrigiere Sprache
    variables["lang"] = variables.get("lang") if variables.get("lang") in SUPPORTED_LANGS else DEFAULT_LANG
    return variables

# ------------------------------------------------------------------------------
# Quality Control (abschaltbar)
# ------------------------------------------------------------------------------

def apply_quality_control(section_name: str, html_text: str) -> Dict[str, Any]:
    """
    Einfache Qualitätsprüfung: Mindestlänge, verbotene Muster (Prozente, Listen),
    narrative Form. Liefert Bewertung + ggf. Korrekturen.
    """
    result = {
        "section": section_name,
        "kept": True,
        "overall_score": 0,
        "issues": [],
        "final_text": html_text or "",
    }

    if not html_text or len(re.sub(r"\s+", "", html_text)) < 80:
        result["issues"].append("too_short")
        result["overall_score"] += 10

    # Keine Aufzählungen/Listen
    if re.search(r"<\s*ul|<\s*ol|<\s*li", html_text or "", re.I):
        result["issues"].append("list_tags_detected")
        result["overall_score"] += 20

    # Keine Prozent-/Zahlensprache
    if re.search(r"%|\b\d{1,3}(?:[.,]\d+)?\b", html_text or ""):
        result["issues"].append("numbers_detected")
        result["overall_score"] += 20

    # Pflicht: Absätze
    if not re.search(r"<\s*p\b", html_text or "", re.I):
        result["issues"].append("no_paragraphs")
        result["overall_score"] += 20

    # Einfaches Stil-Signal
    if re.search(r"\bnutzen\b|\bentlastung\b|\bvertrauen\b", html_text or "", re.I):
        result["overall_score"] -= 10  # positiv

    if not QUALITY_CONTROL_AVAILABLE:
        result["overall_score"] = 0
        result["kept"] = True
        return result

    # QC aktiv: Schwelle weich (30)
    result["kept"] = result["overall_score"] < MIN_QUALITY_SCORE
    return result

# ------------------------------------------------------------------------------
# GPT-Aufruf
# ------------------------------------------------------------------------------

def call_gpt_api(prompt: str, section_name: str, lang: str = "de") -> Optional[str]:
    """
    Ruft GPT/LLM auf. Wenn kein Client vorhanden ist, None -> wir nutzen Fallback.
    Systemprompt erzwingt narrative, zahlenfreie, listenfreie Absätze.
    """
    system_de = (
        "Du bist ein KI-Strategieberater. "
        "Erstelle professionellen, warmen, seriösen HTML-Fließtext in <p>-Absätzen, "
        "ohne Bullet-Listen, ohne Zahlen, ohne Prozentangaben. "
        "Nutze klare, kurze Absätze (3–5 Sätze), bildhafte, aber präzise Sprache. "
        "Keine Platzhalter. Keine Icons. Keine Tabellen. "
        "Beziehe dich kontextuell auf Branche, Größe und Rahmenbedingungen."
    )
    system_en = (
        "You are an AI strategy consultant. "
        "Write professional, warm, trustworthy HTML paragraphs (<p>), "
        "no bullet lists, no numbers, no percentages. "
        "Use short, vivid, precise paragraphs. No placeholders. No icons. No tables."
    )
    system = system_de if (lang or "de").startswith("de") else system_en

    if _openai_client and hasattr(_openai_client, "chat"):
        # neuere OpenAI SDKs
        try:
            resp = _openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "1200")),
            )
            txt = (resp.choices[0].message.content or "").strip()
            return txt
        except Exception as e:
            logger.warning(f"OpenAI chat.completions Fehler [{section_name}]: {e}")

    # Legacy openai
    if _openai_client and hasattr(_openai_client, "ChatCompletion"):
        try:
            resp = _openai_client.ChatCompletion.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "1200")),
            )
            txt = (resp["choices"][0]["message"]["content"] or "").strip()
            return txt
        except Exception as e:
            logger.warning(f"OpenAI ChatCompletion Fehler [{section_name}]: {e}")

    # HTTPX-Fallback (OpenAI REST)
    if _httpx:
        try:
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                return None
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.6,
                "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "1200")),
            }
            url = os.getenv("OPENAI_CHAT_URL", "https://api.openai.com/v1/chat/completions")
            r = _httpx.post(url, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            txt = (data["choices"][0]["message"]["content"] or "").strip()
            return txt
        except Exception as e:
            logger.warning(f"HTTPX OpenAI REST Fehler [{section_name}]: {e}")

    return None  # kein Client verfügbar

# ------------------------------------------------------------------------------
# Fallback-Texte (narrativ, ohne Zahlen & ohne Listen)
# ------------------------------------------------------------------------------

def _fb_par(*lines: str) -> str:
    ps = [f"<p>{l.strip()}</p>" for l in lines if l and l.strip()]
    return "\n".join(ps)

def generate_enhanced_fallback(section_name: str, variables: Dict[str, Any], lang: str) -> str:
    L = (lang or "de").lower().startswith("de")

    if section_name in ("executive_summary", "summary"):
        if L:
            return _fb_par(
                f"Ihr Unternehmen wirkt stabil und tatkräftig – {variables['company_size_label']} in {variables['branche']}.",
                "Genau hier setzt KI pragmatisch an: als leise Kollegin im Hintergrund, die Routinen sortiert, Wissen auffindbar macht und Entwürfe vorbereitet.",
                "Der erste Schritt bleibt bewusst klein: ein klarer Anwendungsfall, eine sichere Umgebung, echte Rückmeldungen aus dem Team – und eine Sprache, die alle mitnimmt."
            )
        else:
            return _fb_par(
                f"Your organisation stands on solid ground – {variables['company_size_label']} in {variables['branche']}.",
                "AI helps quietly at first: sorting routines, surfacing knowledge, preparing drafts without disrupting what already works.",
                "Start small and safe: a focused use case, a protected environment, authentic user feedback, and clear words everyone understands."
            )

    if section_name in ("quick_wins",):
        if L:
            return _fb_par(
                "Beginnen Sie mit einer kurzen Dateninventur und einer einfachen Team‑Checkliste: Wo liegen welche Informationen, wer ist zuständig, wofür werden sie genutzt.",
                "Planen Sie anschließend einen behutsamen Probebetrieb für einen einzigen Alltagsschritt – mit klarer Freigabe, festen Leitplanken und Raum für Feedback.",
                "So entsteht spürbare Entlastung ohne Risiko, und das Team erlebt, dass KI nicht überfordert, sondern Ordnung schafft."
            )
        else:
            return _fb_par(
                "Start with a brief data inventory and a simple team checklist: where things live, who owns them, what they are used for.",
                "Then run a careful pilot on one everyday task – with clear guardrails, a light review, and a feedback loop.",
                "This brings relief without risk and shows that AI brings order rather than burden."
            )

    if section_name in ("risks", "haupt_risiken"):
        if L:
            return _fb_par(
                "Die Stolpersteine sind bekannt: saubere Rechtsgrundlagen, klare Rollen, verlässliche Daten.",
                "Mit einer schlanken Governance, nachvollziehbaren Freigaben und behutsamer Pseudonymisierung bleiben Risiken beherrschbar.",
                "Regelmäßige Reviews und ein kurzer Leitfaden für gute Prompts bewahren Qualität und Ruhe im Betrieb."
            )
        else:
            return _fb_par(
                "Typical pitfalls are legal clarity, roles and data quality.",
                "A light governance, traceable approvals and careful pseudonymisation keep risks manageable.",
                "Short reviews and a prompt guideline maintain quality and calm operations."
            )

    if section_name in ("recommendations", "empfehlungen"):
        if L:
            return _fb_par(
                "Wählen Sie einen greifbaren Nutzenfall im Tagesgeschäft und definieren Sie einfache Erfolgskriterien gemeinsam mit dem Fachbereich.",
                "Bündeln Sie Rollen in einem kleinen Kernteam, dokumentieren Sie Entscheidungen und etablieren Sie einen offenen Feedbackkanal.",
                "So entstehen schnelle Lerneffekte, verlässliche Entscheidungen und eine belastbare Grundlage für den Ausbau."
            )
        else:
            return _fb_par(
                "Select a practical, high‑value use case and agree on simple success criteria with the business team.",
                "Bundle roles in a small core team, document decisions and establish an open feedback channel.",
                "This creates quick learning, reliable decisions and a solid base for scaling."
            )

    if section_name in ("roadmap",):
        if L:
            return _fb_par(
                "Kurzfristig: Orientierung schaffen – Policy‑Entwurf, Dateninventur, ein sicherer Probelauf im echten Ablauf.",
                "Mittelfristig: Pilot stabilisieren – Rollen klären, Dokumentation vereinbaren, Wiederverwendbarkeit aufbauen.",
                "Langfristig: skalieren – Bausteine, Plattform, klare Leitplanken und ruhige Qualifizierung."
            )
        else:
            return _fb_par(
                "Short term: alignment – policy draft, data inventory, a safe pilot in a real workflow.",
                "Medium term: stabilise – clarify roles, agree documentation, build reusable building blocks.",
                "Long term: scale – components, platform, guardrails and calm upskilling."
            )

    if section_name in ("funding", "foerderprogramme"):
        if L:
            return _fb_par(
                "Passende Programme auf Landes‑ und Bundesebene können Einstieg und Qualifizierung erleichtern.",
                "Halten Sie eine kurze Projektskizze bereit: Zielbild, Arbeitspakete, Nutzen und Verantwortlichkeiten.",
                "So erhöhen Sie die Chancen auf Unterstützung und gewinnen Zeit für die inhaltliche Arbeit."
            )
        else:
            return _fb_par(
                "Suitable state and federal programmes can ease entry and upskilling.",
                "Prepare a short project outline: goal, work packages, benefits and responsibilities.",
                "This increases approval chances and frees time for real work."
            )

    if section_name in ("tools", "ki_tools"):
        if L:
            return _fb_par(
                "Wählen Sie wenige, robuste Werkzeuge mit klarer Zuständigkeit statt vieler Insellösungen.",
                "Ein gemeinsamer Arbeitsraum und ein schlanker Freigabeprozess verhindern Tool‑Wildwuchs.",
                "So bleibt die Umgebung ruhig, nachvollziehbar und gut betreibbar."
            )
        else:
            return _fb_par(
                "Choose a few robust tools with clear ownership instead of many islands.",
                "A shared workspace and a light approval process prevent tool sprawl.",
                "This keeps the environment calm, traceable and operable."
            )

    if section_name in ("vision", "leitidee"):
        if L:
            return _fb_par(
                "Leitidee: Eine lebendige Wissenswerkstatt, in der Erfahrungen wachsen, gepflegt werden und sichere KI‑Assistenzen den Alltag erleichtern.",
                "So entsteht Orientierung, Wiederverwendbarkeit und Raum für gute Gespräche – ohne die Sorgfalt aus den Augen zu verlieren.",
                "Die Werkstatt bleibt bewusst leichtgewichtig: nachvollziehbar, kuratiert, datensparsam."
            )
        else:
            return _fb_par(
                "Guiding idea: A living knowledge workshop where experience grows and safe AI assistants ease the day.",
                "This builds orientation, reuse and space for good conversations without losing diligence.",
                "The workshop stays lightweight: traceable, curated, data‑sparing."
            )

    if section_name in ("compliance", "recht"):
        if L:
            return _fb_par(
                "Compliance bildet das Geländer: klare Zweckbindung, Pseudonymisierung, Rollen und dokumentierte Freigaben.",
                "Eine kurze Datenschutz‑Folgenabschätzung vor dem Go‑live schafft Sicherheit und vermeidet spätere Blockaden.",
                "Mit einem schlanken Verzeichnis der Verarbeitungstätigkeiten und transparenten Regeln bleibt der Betrieb auditfähig."
            )
        else:
            return _fb_par(
                "Compliance is the handrail: clear purpose limitation, pseudonymisation, roles and documented approvals.",
                "A short data protection impact assessment before go‑live prevents later roadblocks.",
                "With a light record of processing activities and transparent rules, operations remain audit‑ready."
            )

    # Default
    return _fb_par("Inhalt wird narrativ bereitgestellt.", "Bitte kurz Geduld – die nächsten Zeilen bringen Klarheit.")

# ------------------------------------------------------------------------------
# Erzeugung einer Sektion
# ------------------------------------------------------------------------------

def should_use_gpt(prompt_name: str) -> bool:
    # Für Tabellenähnliches (z. B. Glossar/Tool‑Listen) könnte man GPT meiden.
    # Wir bleiben großzügig: GPT für alle Kerntexte, nicht für reines Tabellengerüst.
    return prompt_name not in {"funding_table", "tools_table", "glossary"}

def generate_section_with_prompt(prompt_name: str, variables: Dict[str, Any], lang: str) -> str:
    """
    Rendert den Prompt, ruft GPT (wenn möglich) und validiert die Ausgabe.
    Fällt narrativ & hochwertig zurück.
    """
    prompt_text = ""
    try:
        prompt_text = prompt_processor.render_prompt(prompt_name, variables, lang)
    except Exception as e:
        logger.warning(f"Prompt-Rendering fehlgeschlagen [{prompt_name}]: {e}")
        return generate_enhanced_fallback(prompt_name, variables, lang)

    if should_use_gpt(prompt_name) and ( _openai_client or _httpx ):
        raw = call_gpt_api(prompt_text, prompt_name, lang)
        if raw and len(re.sub(r"\s+", "", raw)) > 150:
            qc = apply_quality_control(prompt_name, raw)
            if qc["kept"]:
                return qc["final_text"]
            else:
                logger.info(f"QC ersetzt Sektion [{prompt_name}] -> Fallback (score={qc['overall_score']}, issues={qc['issues']})")
                return generate_enhanced_fallback(prompt_name, variables, lang)

    # Kein GPT/zu kurz -> Fallback
    return generate_enhanced_fallback(prompt_name, variables, lang)

# ------------------------------------------------------------------------------
# Hauptfunktion: analyze_briefing
# ------------------------------------------------------------------------------

def analyze_briefing(body: Dict[str, Any], lang: str = DEFAULT_LANG) -> str:
    """
    Baut den HTML-Report zusammen (Narrativ). Wird von main.py aufgerufen.
    """
    t0 = time.time()
    lang = (lang or DEFAULT_LANG).lower()
    env = setup_jinja_env(TEMPLATES_DIR)
    tmpl = env.get_template(PDF_TEMPLATE_NAME)

    variables = get_template_variables(body, lang)

    diagnostics = {
        "gpt_calls": 0,
        "fallbacks_used": 0,
        "sections_generated": [],
        "errors": [],
        "qc": {"enabled": bool(QUALITY_CONTROL_AVAILABLE), "min_score": MIN_QUALITY_SCORE},
    }

    def _gen(name):
        nonlocal diagnostics
        txt = ""
        try:
            if should_use_gpt(name) and ( _openai_client or _httpx ):
                diagnostics["gpt_calls"] += 1
            txt = generate_section_with_prompt(name, variables, lang)
            if txt == "" or "Inhalt wird narrativ bereitgestellt" in txt:
                diagnostics["fallbacks_used"] += 1
            diagnostics["sections_generated"].append(name)
        except Exception as e:
            diagnostics["errors"].append(f"{name}: {e}")
            txt = generate_enhanced_fallback(name, variables, lang)
            diagnostics["fallbacks_used"] += 1
        return txt

    # Kernsektionen (de/en Prompts sollten entsprechend existieren)
    ctx = {
        "lang": lang,
        "today": variables["today"],
        "report_version": variables["report_version"],
        # Narrative Inhalte
        "executive_summary_html": _gen("executive_summary"),
        "quick_wins_html": _gen("quick_wins"),
        "risks_html": _gen("risks"),
        "recommendations_html": _gen("recommendations"),
        "roadmap_html": _gen("roadmap"),
        "compliance_html": _gen("compliance"),
        "vision_html": _gen("vision"),  # ggf. als „Leitidee“ betitelt im Template
        "innovation_html": _gen("innovation_gamechanger"),
        # Tabellen/Sammlungen: weiterhin vom Template gesteuert
        "funding_programs": variables.get("funding_programs") or [],
        "tools": variables.get("tools") or [],
        # Footer/Feedback
        "feedback_link": variables.get("feedback_link", ""),
    }

    # Diagnose im HTML als unsichtbarer Kommentar anhängen (hilft im PDF-Fehlerfall)
    diag_json = json.dumps(
        {
            "elapsed_s": round(time.time() - t0, 2),
            "diagnostics": diagnostics,
        },
        ensure_ascii=False
    )
    ctx["diagnostics_comment"] = f"<!-- diagnostics: {diag_json} -->"

    html = tmpl.render(**ctx)
    return html

# Backward-Compatibility Alias
def analyze_briefing_enhanced(body: Dict[str, Any], lang: str = DEFAULT_LANG) -> str:
    return analyze_briefing(body, lang)
