import os
from datetime import datetime
from weasyprint import HTML

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def create_pdf(html_content):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"KI-Readiness-{timestamp}.pdf"
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    print("==== HTML-Inhalt vor PDF-Erstellung ====")
    print(html_content[:1000])  # Nur ein Ausschnitt!
    print("==== /HTML-Inhalt ====")

    HTML(string=html_content).write_pdf(filepath)
    print(f"PDF gespeichert unter: {filepath}")

    return filename
