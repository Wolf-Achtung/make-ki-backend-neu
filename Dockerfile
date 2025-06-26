FROM python:3.11-slim

# Arbeitsverzeichnis festlegen
WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code kopieren
COPY . .

# Sicherstellen, dass logs-Verzeichnis vorhanden und beschreibbar ist
RUN mkdir -p /app/logs

# Start der App mit gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "main:app"]

