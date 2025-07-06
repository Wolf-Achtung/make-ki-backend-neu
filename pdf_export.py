import os
from datetime import datetime
from weasyprint import HTML

# Ordner für PDF-Downloads festlegen
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def create_pdf_from_template(
    template_html,
    summary,
    score,
    benchmark,
    compliance,
    innovation,
    tools_table,
    vision,
    checklisten_block,
    score_vis,
    praxisbeispiele,
    foerdermittel_table,
    foerdermittel_md,
    glossary,
    faq,
    tools_compact,
    copyright_text=None
):
    """
    Erstellt ein PDF aus dem übergebenen HTML-Template und füllt alle Platzhalter mit Inhalten.
    Alle Variablen sind Strings (HTML oder Markdown, vorher im Backend erzeugt).
    """

    html_content = (
        template_html
        .replace("{{EXEC_SUMMARY}}", summary)
        .replace("{{KI_SCORE}}", str(score))
        .replace("{{BENCHMARK}}", benchmark)
        .replace("{{COMPLIANCE}}", compliance)
        .replace("{{INNOVATION}}", innovation)
        .replace("{{TOOLS}}", tools_table)
        .replace("{{VISION}}", vision)
        .replace("{{CHECKLISTEN}}", checklisten_block)
        .replace("{{SCORE_VISUALISIERUNG}}", score_vis)
        .replace("{{PRAXISBEISPIELE}}", praxisbeispiele)
        .replace("{{FOERDERMITTEL_TAB}}", foerdermittel_table)
        .replace("{{FOERDERMITTEL_MD}}", foerdermittel_md)
        .replace("{{GLOSSAR}}", glossary)
        .replace("{{FAQ}}", faq)
        .replace("{{TOOLS_COMPACT}}", tools_compact)
    )
    # Lizenz- oder Copyright-Hinweis am Ende ergänzen
    if copyright_text:
        html_content += f"<div class='copyright'>{copyright_text}</div>"

    # Zeitstempel
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"KI-Readiness-{timestamp}.pdf"
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)

    # PDF mit WeasyPrint erzeugen
    HTML(string=html_content).write_pdf(filepath)
    print(f"PDF gespeichert unter: {filepath}")

    return filename  # Dateiname (für Download-Link/URL)
