import os
import pdfkit
from jinja2 import Environment, FileSystemLoader, select_autoescape

def export_pdf(report_data, filename="KI-Readiness-Report.pdf"):
    downloads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "downloads"))
    os.makedirs(downloads_dir, exist_ok=True)

    # Logging: Export beginnt
    print(f"[PDF_EXPORT] Start PDF-Export nach: {downloads_dir}")

    # HTML Rendering
    try:
        env = Environment(
            loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
            autoescape=select_autoescape(["html", "xml"])
        )
        template = env.get_template("report_template.html")
        html_content = template.render(**report_data)
    except Exception as e:
        print(f"[PDF_EXPORT][ERROR] HTML-Rendering fehlgeschlagen: {e}")
        raise

    # Zielpfad
    pdf_path = os.path.join(downloads_dir, filename)
    print(f"[PDF_EXPORT] Geplante PDF-Datei: {pdf_path}")

    # PDF Export
    try:
        pdfkit.from_string(html_content, pdf_path)
        print(f"[PDF_EXPORT] PDF erfolgreich erzeugt: {pdf_path}")
    except Exception as e:
        print(f"[PDF_EXPORT][ERROR] PDF-Erstellung fehlgeschlagen: {e}")
        raise

    # Kontrolle, ob Datei wirklich da ist
    if os.path.exists(pdf_path):
        print(f"[PDF_EXPORT] PDF-Datei existiert: {pdf_path}")
    else:
        print(f"[PDF_EXPORT][ERROR] PDF-Datei fehlt nach Export! ({pdf_path})")

    return pdf_path
