import os
import uuid
import tempfile
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

# Setze den Pfad zu deinen Templates
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "pdf_template.html")

def export_pdf(report_data):
    # Jinja2 Umgebung
    env = Environment(loader=FileSystemLoader(os.path.dirname(TEMPLATE_PATH)))
    template = env.get_template(os.path.basename(TEMPLATE_PATH))

    # Daten für das Template
    html_content = template.render(**report_data)

    # PDF-Name + Temp-Pfad
    pdf_filename = f"KI-Readiness-Report_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)

    # PDF generieren
    HTML(string=html_content).write_pdf(pdf_path)

    return pdf_path
