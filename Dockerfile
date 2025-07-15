# ----------------------------
# Dockerfile für KI-Readiness-Check Backend
# inkl. automatischer DB-Initialisierung
# ----------------------------

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8

WORKDIR /app

# Linux-Packages installieren (z. B. für Cairo/Pango etc.)
RUN apt-get update && \
    apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libgdk-pixbuf2.0-dev \
    libxml2 \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu \
    curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 🚀 Variante 1: Mit kompletter DB-Initialisierung (für den ersten Run)
ENTRYPOINT ["sh", "-c", "python full_init.py && uvicorn main:app --host 0.0.0.0 --port 8000"]

# 🚀 Variante 2: Nur API starten (für Dauerbetrieb)
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
