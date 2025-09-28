# ---------- KI-Report-Generator • Production Dockerfile ----------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_BASE=/app \
    PDF_TEMPLATE_NAME=pdf_template.html

WORKDIR /app

# Systemtools für sed/unzip
RUN apt-get update && apt-get install -y --no-install-recommends sed unzip && \
    rm -rf /var/lib/apt/lists/*

# Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code
COPY . .

# --- Robustheits-Fixes am Build ---
# 1) Templates-Verzeichnis sicherstellen und ggf. pdf_template verschieben
RUN mkdir -p /app/templates && \
    if [ -f "/app/pdf_template.html" ] && [ ! -f "/app/templates/pdf_template.html" ]; then \
        mv /app/pdf_template.html /app/templates/pdf_template.html ; \
    fi

# 2) Jinja now()/Tippfehler ddefault: defensiv sowohl in /app/templates als auch im Root patchen
RUN sed -i 's/now().year/2025/g' /app/templates/*.html 2>/dev/null || true && \
    sed -i 's/now().year/2025/g' /app/*.html 2>/dev/null || true && \
    sed -i 's/ddefault/default/g' /app/templates/*.html 2>/dev/null || true && \
    sed -i 's/ddefault/default/g' /app/*.html 2>/dev/null || true

# 3) Schutz: etwaige fehlerhafte Überschreibung des Jinja-Default-Filters entfernen
#    (falls im Repo noch vorhanden)
RUN sed -i '/env\.filters\["default"\]/d' /app/gpt_analyze.py || true

# 4) Schutz: Key-Angleichung quickwins_html -> quick_wins_html (falls Altcode vorhanden)
RUN sed -i 's/quickwins_html/quick_wins_html/g' /app/gpt_analyze.py || true

# 5) Prompts bereitstellen:
#    - Falls prompts.zip vorhanden, entpacken
#    - Falls prompts/-Ordner vorhanden, ist er bereits kopiert
RUN mkdir -p /app/prompts && \
    if [ -f "/app/prompts.zip" ]; then unzip -o /app/prompts.zip -d /app/prompts; fi

EXPOSE 8000

# Start
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
