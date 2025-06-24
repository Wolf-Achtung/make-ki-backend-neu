# Basis-Image
FROM python:3.11-slim

# Arbeitsverzeichnis
WORKDIR /app

# Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code kopieren
COPY . .

# Port setzen (für Railway optional, aber üblich)
ENV PORT=8000

# Startbefehl
CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]

