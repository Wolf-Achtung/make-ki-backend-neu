FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    sed \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Fix 1: Template-Korrekturen
RUN echo "Applying template fixes..." && \
    sed -i "s/now().year if now else '2025'/'2025'/g" /app/templates/pdf_template.html 2>/dev/null || true && \
    sed -i "s/now().year/'2025'/g" /app/templates/pdf_template.html 2>/dev/null || true && \
    sed -i "s/ddefault/default/g" /app/templates/pdf_template_en.html 2>/dev/null || true && \
    sed -i "s/now().year/'2025'/g" /app/templates/pdf_template_en.html 2>/dev/null || true && \
    echo "Template fixes applied"

# Fix 2: Erstelle fehlende Verzeichnisse und Dateien
RUN mkdir -p /app/prompts && \
    echo -e "Erstelle eine inspirierende Vision für die KI-Zukunft.\n\nBranche: {{ branche }}\nBeschreibe in 2-3 Absätzen die ideale KI-Integration." > /app/prompts/vision_de.md && \
    echo -e "Create an inspiring AI vision.\n\nIndustry: {{ branche }}\nDescribe ideal AI integration in 2-3 paragraphs." > /app/prompts/vision_en.md && \
    echo "Missing files created"

# Fix 3: Python-Fixes als einzeiliger Befehl
RUN python3 -c "import os, re; \
    path = '/app/gpt_analyze.py'; \
    content = open(path).read() if os.path.exists(path) else ''; \
    helper = '\ndef _safe_int(v, d=0): return d\ndef _safe_float(v, d=0.0): return d\n'; \
    open(path, 'w').write(helper + content) if content and '_safe_int' not in content else None; \
    print('Python fixes applied')" 2>/dev/null || echo "Python fixes skipped"

# Startup script
RUN echo '#!/bin/bash\n\
echo "Starting application..."\n\
sed -i "s/now().year/2025/g" /app/templates/*.html 2>/dev/null || true\n\
exec uvicorn main:app --host 0.0.0.0 --port 8000' > /app/start.sh && \
    chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
