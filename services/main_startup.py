# -*- coding: utf-8 -*-

from __future__ import annotations
import importlib, logging
from typing import Callable, Dict, Any

__all__ = ["load_analyzer"]
log = logging.getLogger("startup")

def load_analyzer() -> Callable[[Dict[str, Any], str], Dict[str, str]]:
    """Load gpt_analyze.analyze dynamically and return a callable.

    Falls back to a minimal narrative generator to keep PDFs non-empty
    if the module is missing or defective.
    """
    try:
        mod = importlib.import_module("gpt_analyze")
        if not hasattr(mod, "analyze"):
            raise AttributeError("gpt_analyze.analyze() is missing")
        version = getattr(mod, "__version__", "unversioned")
        log.info("Analyzer loaded: gpt_analyze v%s", version)
        return mod.analyze  # type: ignore[no-any-return]
    except Exception as e:
        log.exception("Analyzer load failed. Using fallback. Reason: %s", e)

        def fallback_analyze(briefing: Dict[str, Any], lang: str = "de") -> Dict[str, str]:
            if lang == "en":
                return {
                    "sichere_sofortschritte": (
                        "Start with an EU-hosted core for customer data, deploy an EU-hosted writing assistant "
                        "and automate calendar/e-mail routines to save time while staying GDPR-conform."
                    ),
                    "risiken": (
                        "Reduce risk through purpose limitation, data minimisation and a practical deletion policy. "
                        "Avoid vendor lock-in and keep human approval for critical outputs."
                    ),
                    "roadmap": (
                        "30 days: clean data and assign roles. 90 days: stabilise the pilot and add two routines. "
                        "365 days: professionalise training, versioning and annual review."
                    ),
                    "compliance": (
                        "Embed GDPR, ePrivacy, DSA and EU AI Act pragmatically: clear roles, data classification, "
                        "processor agreements, deletion policy, transparency notices, human approval and export options."
                    ),
                }
            else:
                return {
                    "sichere_sofortschritte": (
                        "Starten Sie mit einem EU-gehosteten Kern fuer Kundendaten, nutzen Sie einen EU-gehosteten "
                        "Schreibassistenten und automatisieren Sie Kalender-/E-Mail-Routinen - schnell spuerbare Entlastung, DSGVO-konform."
                    ),
                    "risiken": (
                        "Begrenzen Sie Risiken ueber Zweckbindung, Datensparsamkeit und ein praxistaugliches Loeschkonzept. "
                        "Vermeiden Sie Vendor-Lock-in und behalten Sie die menschliche Freigabe bei."
                    ),
                    "roadmap": (
                        "30 Tage: Daten ordnen und Rollen vergeben. 90 Tage: Pilot stabilisieren, zwei Routinen ergaenzen. "
                        "365 Tage: Schulung, Versionierung und jaehrliche Ueberpruefung professionalisieren."
                    ),
                    "compliance": (
                        "Verankern Sie DSGVO, ePrivacy, DSA und EU-AI-Act pragmatisch: klare Rollen, Datenklassifizierung, "
                        "Auftragsverarbeitung, Loeschkonzept, Transparenzhinweise, menschliche Freigabe und Exportmoeglichkeiten."
                    ),
                }
        return fallback_analyze
