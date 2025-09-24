# ----------------------------
# Dockerfile – Multi-Stage (fix)
# ----------------------------

# Stage 1: Builder mit Dev-Headern (für Wheels)
FROM python:3.11-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential python3-dev libffi-dev \
    libcairo2-dev libxml2-dev libxslt1-dev \
    libjpeg62-turbo-dev zlib1g-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip wheel setuptools \
 && pip wheel --wheel-dir=/build/wheels -r requirements.txt

# Stage 2: Runtime minimal
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Nur Runtime-Libs (HTML→PDF, Fonts, Netzwerk)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    librsvg2-2 \
    libxml2 libxslt1.1 \
    shared-mime-info \
    fonts-dejavu fonts-liberation \
    tzdata curl \
    # optional, falls ihr WebP-Assets nutzt:
    libwebp7 \
 && rm -rf /var/lib/apt/lists/*

# Wheels aus Builder installieren (kein Compiler nötig)
COPY --from=builder /build/wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*

# App rein
COPY . .

EXPOSE 8000

# Optionaler Healthcheck (aktivieren, wenn /health eingebaut ist)
# HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
#   CMD curl -fsS http://localhost:8000/health || exit 1

# DB-Init nur, wenn RUN_DB_INIT=true; sonst überspringen.
# Danach FastAPI starten.
ENTRYPOINT ["sh", "-c", "[ \"$RUN_DB_INIT\" = \"true\" ] && python full_init.py || echo 'DB-Init übersprungen'; uvicorn main:app --host 0.0.0.0 --port 8000"]
