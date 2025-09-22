# main.py — Template‑Only renderer (language folders supported)
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from gpt_analyze import analyze_briefing

BASE = Path(__file__).resolve().parent
TEMPLATE_DIR = Path(os.getenv("TEMPLATE_DIR","gold3/templates"))
TEMPLATE_DE = os.getenv("TEMPLATE_DE","pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN","pdf_template_en.html")

env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=select_autoescape(['html','xml']))

def render(lang: str, body: dict) -> str:
    tpl_name = TEMPLATE_DE if str(lang).lower().startswith("de") else TEMPLATE_EN
    template = env.get_template(tpl_name)
    result = analyze_briefing(body, lang=lang)
    return template.render(**result)

if __name__ == "__main__":
    sample = {"company":"Muster GmbH","branche":"Dienstleistung","unternehmensgroesse":"50-100","bundesland":"Berlin"}
    print(render("de", sample)[:500])
