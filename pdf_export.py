import os
import datetime
import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

# Projektwurzel für Railway-kompatible Pfade
def get_project_root():
    return os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = get_project_root()

# Robust: Alle Pflichtfelder und Defaults für das Report-Dict
REPORT_DEFAULTS = {
    "executive_summary": "",
    "gesamtstrategie": "",
    "branchenueberblick": "",
    "wettbewerb": "",
    "zielgruppen": "",
    "chancen_risiken": "",
    "empfehlungen": "",
    "roadmap": "",
    "innovation": "",
    "praxisbeispiele": "",
    "compliance": "",
    "datenschutz": "",
    "tools": "",
    "foerderprogramme": "",
    "checklisten": "",
    "moonshot_vision": "",
    "eu_ai_act": "",
}

# Markdown zu HTML-Konvertierung
def markdown_to_html(text, extensions=None):
    if not text:
        return ""
    if extensions is None:
        extensions = ["extra", "nl2br"]
    return markdown.markdown(text, extensions=extensions)

def read_checklists():
    checklist_dir = os.path.join(PROJECT_ROOT, "data", "checklisten")
    if not os.path.exists(checklist_dir):
        print("[PDF_EXPORT] Ordner nicht gefunden:", checklist_dir)
        return {}
    html_blocks = {}
    for fname in sorted(os.listdir(checklist_dir)):
        if fname.endswith(".md"):
            path = os.path.join(checklist_dir, fname)
            with open(path, "r") as f:
                html_blocks[fname[:-3].replace("_", " ").title()] = markdown_to_html(f.read())
    return html_blocks

def ensure_downloads_dir():
    downloads_dir = os.path.join(PROJECT_ROOT, "downloads")
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir, exist_ok=True)
    return downloads_dir

def get_safe_filename(base: str):
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{base}_{now}.pdf"

def export_pdf(report_data):
    report = REPORT_DEFAULTS.copy()
    if isinstance(report_data, dict):
        for k in report:
            if k in report_data and report_data[k] not in [None, ""]:
                report[k] = report_data[k]
        missing = [k for k in report if report[k] == "" and k in REPORT_DEFAULTS and (k not in report_data or not report_data.get(k))]
        print("[PDF_EXPORT][DEBUG] Fehlende oder leere Felder im Report:", missing)
    else:
        print("[PDF_EXPORT][ERROR] Falscher Typ:", type(report_data))
        raise ValueError("Report-Daten müssen ein Dict sein!")

    markdown_fields = [
    "executive_summary", "gesamtstrategie", "branchenueberblick", "wettbewerb", "zielgruppen",
    "chancen_risiken", "empfehlungen", "roadmap", "innovation", "praxisbeispiele", "compliance",
    "datenschutz", "tools", "foerderprogramme", "moonshot_vision", "eu_ai_act"
]
    for key in markdown_fields:
        report[key] = markdown_to_html(report.get(key, ""))

    report["checklisten"] = read_checklists()

    if not report["date"]:
        report["date"] = datetime.datetime.now().strftime("%d.%m.%Y")
    if not report["year"]:
        report["year"] = datetime.datetime.now().year

    downloads_dir = ensure_downloads_dir()
    filename_base = (report.get("org_name", "KI-Readiness").replace(" ", "_") or "KI-Readiness")
    filename = get_safe_filename(filename_base)
    pdf_path = os.path.join(downloads_dir, filename)

    try:
        env = Environment(
            loader=FileSystemLoader(os.path.join(PROJECT_ROOT, "templates")),
            autoescape=select_autoescape(["html", "xml"])
        )
        template = env.get_template("pdf_template.html")
        html_content = template.render(**report)
    except Exception as e:
        print("[PDF_EXPORT][ERROR] PDF-Template konnte nicht geladen/gerendert werden:", e)
        raise RuntimeError(f"PDF-Template konnte nicht geladen/gerendert werden: {e}")

    try:
        HTML(string=html_content, base_url=downloads_dir).write_pdf(pdf_path)
        print(f"[PDF_EXPORT] PDF erfolgreich erstellt: {pdf_path}")
        return os.path.basename(pdf_path)
    except Exception as e:
        print("[PDF_EXPORT][ERROR] PDF-Erstellung fehlgeschlagen:", e)
        raise RuntimeError(f"PDF-Erstellung fehlgeschlagen: {e}")
