
from jinja2 import Template
import os

def generate_html(data: dict, gpt_result: dict) -> str:
    # Lade das HTML-Template
    template_path = os.path.join(os.path.dirname(__file__), "template.html")
    with open(template_path, "r", encoding="utf-8") as file:
        template_text = file.read()

    # Template-Fix (z. B. "analyse.know-how" → "analyse.knowhow")
    template_text = template_text.replace("analyse.know-how", "analyse.knowhow")

    # Initialisiere Jinja2-Template
    template = Template(template_text)

    # Zusammenführen
    merged = {**data, **gpt_result}

    # Ergänze verschachtelte GPT-Abschnitte (Dummy-Werte möglich)
    merged["analyse"] = {
        "branche": data.get("branche", ""),
        "ziel": data.get("ziel", ""),
        "tools": data.get("tools", ""),
        "prozesse": data.get("prozesse", ""),
        "infrastruktur": data.get("infrastruktur", ""),
        "knowhow": data.get("knowhow", ""),
        "massnahmen": data.get("massnahmen", ""),
        "verantwortung": data.get("verantwortung", ""),
        "herausforderung": data.get("herausforderung", ""),
        "datenschutz": data.get("datenschutz", ""),
        "unternehmen": data.get("unternehmen", "")
    }

    merged["empfehlungen"] = {
        "datenschutz_optimierung": "...",
        "fortbildung": "...",
        "prozess_automatisierung": "...",
        "tool_optimierung": "..."
    }

    merged["foerdertipps"] = {
        "förderprogramme": "...",
        "schulungsprogramme": "..."
    }

    merged["compliance"] = {
        "datenschutz": "...",
        "sicherheit": "..."
    }

    merged["trendreport"] = {
        "branchenspezifische_trends": "...",
        "ki_trends": "..."
    }

    merged["zukunft"] = { "zukunftsaussichten": "..." }
    merged["gamechanger"] = { "potentieller_gamechanger": "..." }
    merged["beratungsempfehlung"] = { "beratungsbedarf": "..." }

    return template.render(**merged)
