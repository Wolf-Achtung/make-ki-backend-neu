from weasyprint import HTML
import datetime

def create_pdf_from_template(html_content, *args, **kwargs):
    # Erzeugt einen eindeutigen Dateinamen mit Timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"KI-Readiness-{timestamp}.pdf"
    filepath = f"downloads/{filename}"

    # PDF aus dem gerenderten HTML erstellen
    HTML(string=html_content).write_pdf(filepath)

    return filename
