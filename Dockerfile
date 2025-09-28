# Dockerfile
# Mit integrierten Hotfixes für Template- und gpt_analyze-Probleme
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# ==========================================
# HOTFIX SECTION - Automatische Korrekturen
# ==========================================

# Fix 1: Korrigiere Template-Probleme
RUN echo "Applying template fixes..." && \
    # Fix pdf_template.html
    sed -i "s/{{ copyright_year|default(now().year if now else '2025', true) }}/{{ copyright_year|default('2025', true) }}/g" /app/templates/pdf_template.html 2>/dev/null || true && \
    sed -i "s/now().year/'2025'/g" /app/templates/pdf_template.html 2>/dev/null || true && \
    # Fix pdf_template_en.html
    sed -i "s/{{ copyright_year|ddefault(now().year if now else '2025', true) }}/{{ copyright_year|default('2025', true) }}/g" /app/templates/pdf_template_en.html 2>/dev/null || true && \
    sed -i "s/ddefault/default/g" /app/templates/pdf_template_en.html 2>/dev/null || true && \
    sed -i "s/now().year/'2025'/g" /app/templates/pdf_template_en.html 2>/dev/null || true && \
    echo "✅ Template fixes applied"

# Fix 2: Erstelle fehlende Prompt-Dateien
RUN mkdir -p /app/prompts && \
    # Erstelle vision_de.md falls sie fehlt
    if [ ! -f "/app/prompts/vision_de.md" ]; then \
        echo 'Erstelle eine inspirierende Vision für die KI-Zukunft des Unternehmens.\n\nBranche: {{ branche }}\nUnternehmensgröße: {{ company_size_label }}\n\nBeschreibe in 2-3 Absätzen:\n- Wie sieht die ideale KI-Integration in 3 Jahren aus?\n- Welche konkreten Vorteile entstehen?\n- Wie verändert sich die Arbeitsweise positiv?\n\nSchreibe warm, motivierend und konkret.' > /app/prompts/vision_de.md; \
    fi && \
    # Erstelle vision_en.md falls sie fehlt  
    if [ ! -f "/app/prompts/vision_en.md" ]; then \
        echo 'Create an inspiring vision for the AI future of the company.\n\nIndustry: {{ branche }}\nCompany size: {{ company_size_label }}\n\nDescribe in 2-3 paragraphs:\n- What does ideal AI integration look like in 3 years?\n- What concrete benefits arise?\n- How does the way of working change positively?\n\nWrite warmly, motivatingly and concretely.' > /app/prompts/vision_en.md; \
    fi && \
    echo "✅ Missing prompts created"

# Fix 3: Python-Hotfix für gpt_analyze.py
RUN python3 -c "
import os
import re

# Hotfix für Jinja2 Filter-Probleme
if os.path.exists('/app/gpt_analyze.py'):
    with open('/app/gpt_analyze.py', 'r') as f:
        content = f.read()
    
    # Füge Safe-Helper-Funktionen hinzu falls sie fehlen
    if 'def _safe_int' not in content:
        helper_code = '''
def _safe_int(value, default=0):
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            import re
            cleaned = re.sub(r\"[^\\\\d-]\", \"\", str(value))
            if cleaned:
                return int(cleaned)
    except:
        pass
    return default

def _safe_float(value, default=0.0):
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = str(value).replace(\",\", \".\")
            import re
            cleaned = re.sub(r\"[^\\\\d.-]\", \"\", cleaned)
            if cleaned and cleaned not in (\"\", \".\", \"-\"):
                return float(cleaned)
    except:
        pass
    return default
'''
        # Füge Helper nach den Imports ein
        import_end = content.find('\\n\\n', content.find('import'))
        if import_end > 0:
            content = content[:import_end] + helper_code + content[import_end:]
    
    # Speichere zurück
    with open('/app/gpt_analyze.py', 'w') as f:
        f.write(content)
    
    print('✅ Python hotfixes applied')
" || echo "⚠️  Could not apply Python fixes"

# ==========================================
# END HOTFIX SECTION
# ==========================================

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
