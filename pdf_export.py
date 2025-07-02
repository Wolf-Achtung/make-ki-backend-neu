from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader
import os
from datetime import datetime

def create_pdf(data: dict, template_dir="templates", output_dir="downloads"):
    """
    Rendert ein PDF aus dem Template mit den übergebenen Daten,
    speichert es im Downloads-Ordner und gibt den Pfad zurück.
    """
    # Jinja2 Umgebung laden
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("pdf_template.html")
    
    # HTML rendern
    rendered_html = template.render(**data)
    
    # Downloads-Ordner sicherstellen
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Dateinamen mit Zeitstempel erzeugen
    filename = f"KI-Readiness-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf"
    output_path = os.path.join(output_dir, filename)
    
    # PDF generieren
    HTML(string=rendered_html).write_pdf(output_path)
    
    return output_path
