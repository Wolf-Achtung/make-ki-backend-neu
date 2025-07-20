import os
import datetime
import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

# --- Markdown zu HTML-Konvertierung
def markdown_to_html(text):
    return markdown.markdown(text, extensions=["extra", "nl2br"])

# --- Checklisten als HTML laden
def read_checklists():
    """
    Liest alle Checklisten aus dem ./data/checklisten-Ordner ein und gibt sie als HTML-String zurück.
    """
    checklist_dir = os.path.join(os.path.dirname(__file__), "data", "checklisten")
    if not os.path.exists(checklist_dir):
        print("[PDF_EXPORT] Ordner nicht gefunden:", checklist_dir)
        return ""

    html_blocks = []
    for fname in sorted(os.listdir(checklist_dir)):
        if fname.endswith(".md"):
            path = os.path.join(checklist_dir, fname)
            with open(path, encoding="utf-8") as f:
                content = f.read()
                title = fname[:-3].replace("_", " ").title()
                html = f"<h3>{title}</h3>\n" + markdown_to_html(content)
                html_blocks.append(html)
    return "\n".join(html_blocks)

# --- Hauptfunktion: PDF-Export
def export_pdf(report_data, filename="KI-Readiness-Report.pdf"):
    downloads_dir = os.path.join(os.path.dirname(__file__), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)
    pdf_path = os.path.join(downloads_dir, filename)
    print(f"[PDF_EXPORT] Start PDF-Export nach: {downloads_dir}")

    # --- Markdown-Felder zu HTML
    keys_md = [
        "executive_summary", "gesamtstrategie", "compliance", "innovation",
        "datenschutz", "roadmap", "praxisbeispiele", "tools",
        "foerderprogramme", "moonshot_vision", "eu_ai_act"
    ]
    report_data_html = report_data.copy()
    for key in keys_md:
        if key in report_data_html:
            report_data_html[key] = markdown_to_html(report_data_html[key])

    # --- Checklisten einfügen
    report_data_html["checklists_html"] = read_checklists()
    # --- Datum/Jahr automatisch einfügen
    report_data_html["date"] = datetime.datetime.now().strftime("%d.%m.%Y")
    report_data_html["year"] = datetime.datetime.now().year

    # --- Fallback für report_name
    if "report" not in report_data_html:
        report_data_html["report"] = report_data_html

    # --- HTML Rendering mit Jinja2
    try:
        env = Environment(
            loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
            autoescape=select_autoescape(['html'])
        )
        template = env.get_template("pdf_template.html")
        html_content = template.render(**report_data_html)
    except Exception as e:
        raise RuntimeError(f"PDF-Template konnte nicht geladen/rendered werden: {e}")

    # --- PDF Generierung
    try:
        HTML(string=html_content, base_url=downloads_dir).write_pdf(pdf_path)
        print(f"[PDF_EXPORT] PDF erfolgreich erzeugt: {pdf_path}")
    except Exception as e:
        raise RuntimeError(f"PDF-Erstellung fehlgeschlagen: {e}")

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"[PDF_EXPORT] PDF-Datei fehlt nach Export! ({pdf_path})")
    return os.path.basename(pdf_path)

# --- Hinweis zur Nutzung von Logos (siehe Template-Kommentar)
# Für statische Assets: z.B. unter /app/templates oder /app/static/logo.svg
# Nutzung im Template: <img src="/static/logo.svg"> oder rel. <img src="logo.svg">

