# Dockerfile
# Mit integrierten Hotfixes für Template- und gpt_analyze-Probleme
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    sed \
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
    sed -i "s/now().year if now else '2025'/'2025'/g" /app/templates/pdf_template.html 2>/dev/null || true && \
    sed -i "s/now().year/'2025'/g" /app/templates/pdf_template.html 2>/dev/null || true && \
    sed -i "s/ddefault/default/g" /app/templates/pdf_template_en.html 2>/dev/null || true && \
    echo "✅ Template fixes applied"

# Fix 2: Erstelle fehlende Prompt-Dateien
RUN mkdir -p /app/prompts && \
    echo 'Erstelle eine inspirierende Vision für die KI-Zukunft des Unternehmens.\n\nBranche: {{ branche }}\nUnternehmensgröße: {{ company_size_label }}\n\nBeschreibe in 2-3 Absätzen:\n- Wie sieht die ideale KI-Integration in 3 Jahren aus?\n- Welche konkreten Vorteile entstehen?\n- Wie verändert sich die Arbeitsweise positiv?\n\nSchreibe warm, motivierend und konkret.' > /app/prompts/vision_de.md 2>/dev/null || true && \
    echo 'Create an inspiring vision for the AI future of the company.\n\nIndustry: {{ branche }}\nCompany size: {{ company_size_label }}\n\nDescribe in 2-3 paragraphs:\n- What does ideal AI integration look like in 3 years?\n- What concrete benefits arise?\n- How does the way of working change positively?\n\nWrite warmly, motivatingly and concretely.' > /app/prompts/vision_en.md 2>/dev/null || true && \
    echo "✅ Missing prompts created"

# Fix 3: Erstelle Python-Fix-Script und führe es aus
RUN cat > /tmp/fix_python.py << 'EOF' && \
import os
import re
import sys

try:
    if not os.path.exists('/app/gpt_analyze.py'):
        print("gpt_analyze.py not found")
        sys.exit(0)
    
    with open('/app/gpt_analyze.py', 'r') as f:
        content = f.read()
    
    # Add helper functions if missing
    if '_safe_int' not in content and 'safe_int' not in content:
        helper_code = """
# Helper functions for safe type conversion
def _safe_int(value, default=0):
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            import re
            cleaned = re.sub(r'[^\d-]', '', str(value))
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
            cleaned = str(value).replace(',', '.')
            import re
            cleaned = re.sub(r'[^\d.-]', '', cleaned)
            if cleaned and cleaned not in ('', '.', '-'):
                return float(cleaned)
    except:
        pass
    return default
"""
        # Find location after imports
        import_end = content.find('\\n\\n', content.find('import'))
        if import_end > 0:
            content = content[:import_end] + helper_code + content[import_end:]
            with open('/app/gpt_analyze.py', 'w') as f:
                f.write(content)
            print("Added helper functions to gpt_analyze.py")
    else:
        print("Helper functions already present")
        
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOF
    python3 /tmp/fix_python.py && \
    rm /tmp/fix_python.py && \
    echo "✅ Python fixes applied"

# ==========================================
# END HOTFIX SECTION
# ==========================================

# Create startup script
RUN cat > /app/start.sh << 'EOF' && \
#!/bin/bash
echo "🚀 Starting application..."
# Additional runtime fixes if needed
sed -i "s/now().year/'2025'/g" /app/templates/*.html 2>/dev/null || true
# Start application
exec uvicorn main:app --host 0.0.0.0 --port 8000
EOF
    chmod +x /app/start.sh

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application using the startup script
CMD ["/app/start.sh"]
