import os
import datetime
import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

def markdown_to_html(text):
    """Konvertiert Markdown-Text in HTML."""
    if not text:
        return ""
    return markdown.markdown(text, extensions=["extra", "nl2br"])

def read_checklists():
    """Liest alle Checklisten aus dem data/checklisten-Ordner ein und gibt sie als HTML-String zurück."""
    base_dir = os.path.dirname(__file__)
    checklist_dir = os.path.join(base_dir, "data", "checklisten")
    if not os.path.isdir(checklist_dir):
        print("[CHECKLIST] Ordner nicht gefunden:", checklist_dir)
        return ""
    html_blocks = []
    for fname in sorted(os.listdir(checklist_dir)):
        if fname.endswith(".md"):
            fpath = os.path.join(checklist_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            # Optional: Dateiname als Überschrift
            headline = os.path.splitext(fname)[0].replace("_", " ").title()
            html_blocks.append(f"<h3>{headline}</h3>{markdown_to_html(content)}")
    if html_blocks:
        return "<section class='checklisten'>" + "".join(html_blocks) + "</section>"
    return ""

def export_pdf(report_data, filename="KI-Readiness-Report.pdf"):
    downloads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "downloads"))
    os.makedirs(downloads_dir, exist_ok=True)
    print(f"[PDF_EXPORT] Start PDF-Export nach: {downloads_dir}")

    # Alle Textfelder, die Markdown enthalten, konvertieren
    md_keys = [
        "executive_summary", "gesamtstrategie", "compliance", "innovation", "datenschutz",
        "roadmap", "praxisbeispiele", "tools", "foerderprogramme", "moonshot_vision",
        "eu_ai_act", "summary_solo", "summary_kmu", "summary_klein", "foerdermittel",
    ]
    report_data_html = report_data.copy()
    for key in md_keys:
        if key in report_data_html:
            report_data_html[key] = markdown_to_html(report_data_html[key])

    # --- Checklisten einbinden ---
    report_data_html["checklisten"] = read_checklists()

    # Das aktuelle Jahr bereitstellen
    report_data_html["jahr"] = datetime.datetime.now().year

    # Optional: Falls das Template noch auf report.xyz referenziert, dies ergänzen:
    # report_data_html["report"] = report_data_html

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
        raise RuntimeError(f"PDF-Template konnte nicht geladen werden: {e}")

    pdf_path = os.path.join(downloads_dir, filename)
    print(f"[PDF_EXPORT] Geplante PDF-Datei: {pdf_path}")

    try:
        HTML(string=html_content, base_url=os.path.dirname(__file__)).write_pdf(pdf_path)
        print(f"[PDF_EXPORT] PDF erfolgreich erzeugt: {pdf_path}")
    except Exception as e:
        print(f"[PDF_EXPORT][ERROR] PDF-Erstellung fehlgeschlagen: {e}")
        raise RuntimeError(f"PDF-Erstellung fehlgeschlagen: {e}")

    if os.path.exists(pdf_path):
        print(f"[PDF_EXPORT] PDF-Datei existiert: {pdf_path}")
    else:
        print(f"[PDF_EXPORT][ERROR] PDF-Datei fehlt nach Export! ({pdf_path})")

    return os.path.basename(pdf_path)

# Hinweise zu Logos:
# Damit WeasyPrint Bilder korrekt einbettet, sollten Logos z.B. unter /app/templates oder /app/static/logo.svg liegen
# Im Template muss die Pfadangabe relativ zum PDF-Export (base_url=...) oder als absolute URL erfolgen:
# Beispiel im HTML: <img src="static/logo.svg"> oder <img src="https://deine-domain.de/static/logo.svg">
