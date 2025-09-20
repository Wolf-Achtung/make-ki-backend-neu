# gpt_analyze.py — Gold-Standard (clean, minimal, robust)
__VERSION__ = "2025-09-20-gold"

import os, re, json
from pathlib import Path
from datetime import datetime as _dt
from typing import Dict, Any

# Optional: Jinja2 for HTML rendering (used by main.py too)
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except Exception:  # keep import-time safe
    Environment = None  # type: ignore

ROOT = Path(__file__).resolve().parent
TEMPLATES = Path(os.getenv("TEMPLATE_DIR", ROOT / "templates"))

# ---------------- Helpers ----------------

def _norm(value: str) -> str:
    s = (value or "").strip() if isinstance(value, str) else ""
    return s if s else "n. v."

TOKENS = {"t30": "30 Tage", "t90": "90 Tage", "t365": "365 Tage"}

def fix_time_labels(text: str) -> str:
    if not text:
        return text
    for k, v in TOKENS.items():
        text = text.replace(k, v)
    # häufiges Artefakt: „bis Tage“ ohne Zahl
    text = re.sub(r"\b(bis|Heute bis)\s+Tage\b", "bis 30 Tage", text)
    return text

_CODEFENCE_RE = re.compile(r"```.*?```", re.S)
_BULLET_RE = re.compile(r"(?m)^\s*[-•\*]\s+")

def sanitize_narrative(text: str) -> str:
    if not text:
        return text
    # remove code fences
    text = _CODEFENCE_RE.sub("", text)
    # try to turn bullets into flowing sentences
    text = _BULLET_RE.sub("", text)
    # collapse spaces
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

_URL_RE = re.compile(r"https?://\S+")

def curate_live_item(txt: str) -> str:
    if not txt:
        return ""
    txt = _URL_RE.sub("", txt)          # URLs raus
    txt = re.sub(r"\s{2,}", " ", txt)
    return txt.strip()

def curate_live_updates(items: list[str], max_items: int = 3) -> str:
    curated = []
    for it in items[:max_items]:
        it = curate_live_item(it)
        if it:
            curated.append(it)
    return " ".join(curated)

# ---------------- Core ----------------

def build_context(briefing: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """
    Build a robust rendering context from a (possibly sparse) briefing.
    This function is deliberately conservative: it never returns empty meta,
    it normalizes language and replaces fragile time tokens.
    """
    lang = (lang or "de").lower()
    if lang not in ("de", "en", "both"):
        lang = "de"

    meta = {
        "title": "KI‑Statusbericht" if lang == "de" else "AI Status Report",
        "branche": _norm(str(briefing.get("branche", ""))),
        "groesse": _norm(str(briefing.get("unternehmensgroesse", briefing.get("groesse", "")))),
        "standort": _norm(str(briefing.get("standort", briefing.get("region", "")))),
        "sprache": lang if lang in ("de", "en") else "de",
        "date": _dt.now().strftime("%d.%m.%Y"),
    }

    # Pull pre-generated narrative (if the pipeline created it), else minimal defaults.
    def get(k: str, default: str) -> str:
        v = briefing.get(k) or briefing.get(f"{k}_{lang}") or ""
        v = sanitize_narrative(str(v))
        v = fix_time_labels(v)
        return v or default

    # Minimal warm defaults (never empty HTML)
    defaults_de = {
        "executive_summary": "Kurzfassung: Dieser Report bietet eine narrative, umsetzungsorientierte Bestandsaufnahme inklusive Roadmap.",
        "quick_wins": "Starten Sie mit EU‑freundlichen Werkzeugen (z. B. CRM, Schreibassistenz, einfache Automatisierung) und einer klaren menschlichen Freigabe.",
        "risks": "Achten Sie auf Datenschutz, Halluzinationen/Qualität, Kostenkontrolle und Vendor‑Lock‑in. Arbeiten Sie mit Redaktionsschleife und Export‑Strategie.",
        "recommendations": "Kleine Schritte, klare Verantwortlichkeiten, messbare Ergebnisse. EU‑Hosting bevorzugen, DPIA/VVT vorbereiten.",
        "roadmap": "Erste Etappe: heute bis 30 Tage. Zweite Etappe: bis 90 Tage. Dritte Etappe: bis 365 Tage – jeweils mit Fokus auf Datenbasis, Pilot, Skalierung.",
        "vision": "Ein leichter, EU‑freundlicher Copilot mit Prüfspur unterstützt Antwortentwürfe und Wissenssuche – mit menschlicher Freigabe.",
        "compliance": "Adressieren Sie DSGVO, ePrivacy, DSA und EU‑AI‑Act pragmatisch: Rollen klären, Datenminimierung, Transparenz, Dokumentation.",
        "foerderprogramme": "BAFA‑Beratungsförderung (Bund), ggf. Landesprogramme; regionale Listings je nach Standort priorisieren.",
        "live_updates": "Aktuelle Hinweise werden kuratiert eingeblendet – bitte Fachprüfung im Team einplanen.",
    }
    defaults_en = {
        "executive_summary": "Summary: Narrative, action‑oriented status with a concrete roadmap.",
        "quick_wins": "Start with EU‑friendly tools (CRM, writing assistant, simple automation) and human approval.",
        "risks": "Watch privacy, hallucinations/quality, cost control and vendor lock‑in. Use editorial review and export strategy.",
        "recommendations": "Small steps, clear owners, measurable outcomes. Prefer EU hosting, prepare DPIA/records.",
        "roadmap": "Stage one: today to 30 days. Stage two: to 90 days. Stage three: to 365 days – data foundation, pilot, scale.",
        "vision": "A lightweight EU‑friendly copilot with audit trail drafts replies and surfaces knowledge – human approval required.",
        "compliance": "Address GDPR, ePrivacy, DSA and EU AI Act pragmatically: roles, data minimization, transparency, documentation.",
        "foerderprogramme": "BAFA (federal) and state programs; prioritize by location.",
        "live_updates": "Curated recent notes – verify within your team.",
    }

    defaults = defaults_de if lang == "de" else defaults_en

    ctx: Dict[str, Any] = {
        "meta": meta,
        "executive_summary": get("executive_summary", defaults["executive_summary"]),
        "quick_wins": get("quick_wins", defaults["quick_wins"]),
        "risks": get("risks", defaults["risks"]),
        "recommendations": get("recommendations", defaults["recommendations"]),
        "roadmap": get("roadmap", defaults["roadmap"]),
        "vision": get("vision", defaults["vision"]),
        "compliance": get("compliance", defaults["compliance"]),
        "foerderprogramme": get("foerderprogramme", defaults["foerderprogramme"]),
        "live_updates": get("live_updates", defaults["live_updates"]),
    }
    return ctx

def render_html(context: Dict[str, Any], lang: str = "de") -> str:
    """
    Render HTML via Jinja2; caller ensures templates exist.
    Supports lang in {"de","en"}.
    """
    if Environment is None:
        raise RuntimeError("Jinja2 not available")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
        enable_async=False,
    )
    tpl_name = "pdf_template_en.html" if lang == "en" else "pdf_template.html"
    tpl = env.get_template(tpl_name)
    return tpl.render(context)

