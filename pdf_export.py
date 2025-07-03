import os
from datetime import datetime
from weasyprint import HTML

# Downloads-Ordner festlegen und sicherstellen, dass er existiert
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def create_pdf(html_content):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"KI-Readiness-{timestamp}.pdf"
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    # PDF mit WeasyPrint erzeugen
    HTML(string=html_content).write_pdf(filepath)
    print(f"PDF gespeichert unter: {filepath}")

    return filename  # Wir geben nur den Dateinamen zurück, für die URL
