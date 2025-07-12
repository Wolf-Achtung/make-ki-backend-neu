import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
import markdown  # NEU!

def markdown_to_html(text):
    """Hilfsfunktion, um Markdown in HTML zu konvertieren (mit einfachen Einstellungen)."""
    if not text:
        return ""
    return markdown.markdown(text, extensions=["extra", "nl2br"])

def export_pdf(report_data, filename="KI-Readiness-Report.pdf"):
    downloads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "downloads"))
    os.makedirs(downloads_dir, exist_ok=True)
    print(f"[PDF_EXPORT] Start PDF-Export nach: {downloads_dir}")

    # Alle Textfelder, die Markdown enthalten, konvertieren
    md_keys = [
        "executive_summary",
        "gesamtstrategie",
        "compliance",
        "innovation",
        "datenschutz",
        "roadmap",
        "praxisbeispiele",
        "tools",
        "foerderprogramme",
        "moonshot_vision",
        "eu_ai_act",
        "summary_solo",
        "summary_kmu",
        "summary_klein",
        "foerdermittel",
        # ggf. weitere Felder ergänzen!
    ]
    # Kopie, damit wir Original nicht überschreiben
    report_data_html = report_data.copy()
    for key in md_keys:
        if key in report_data_html:
            report_data_html[key] = markdown_to_html(report_data_html[key])

    # HTML Rendering
    try:
        env = Environment(
            loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
            autoescape=select_autoescape(["html", "xml"])
        )
        template = env.get_template("pdf_template.html")
        html_content = template.render(**report_data_html)
    except Exception as e:
        print(f"[PDF_EXPORT][ERROR] HTML-Rendering fehlgeschlagen: {e}")
        raise

    pdf_path = os.path.join(downloads_dir, filename)
    print(f"[PDF_EXPORT] Geplante PDF-Datei: {pdf_path}")

    try:
        HTML(string=html_content).write_pdf(pdf_path)
        print(f"[PDF_EXPORT] PDF erfolgreich erzeugt: {pdf_path}")
    except Exception as e:
        print(f"[PDF_EXPORT][ERROR] PDF-Erstellung fehlgeschlagen: {e}")
        raise

    if os.path.exists(pdf_path):
        print(f"[PDF_EXPORT] PDF-Datei existiert: {pdf_path}")
    else:
        print(f"[PDF_EXPORT][ERROR] PDF-Datei fehlt nach Export! ({pdf_path})")

    return pdf_path
