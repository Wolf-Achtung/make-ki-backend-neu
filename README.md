# KI-Status-Report – Gold-Standard Backend

Dieser Ordner enthält eine **bereinigte und lauffähige** FastAPI-Backend-Implementierung,
die alle vorhandenen Inhalte (Prompts, Data) einbindet und **Reports in Deutsch und Englisch**
als HTML (und optional PDF) rendert. Keine neuen Template-Namen wie „Base“ – die
Haupt-Templates heißen `report_template_de.html` und `report_template_en.html`.

## Features

- FastAPI + Jinja2 mit hübschen DE/EN-Templates
- Einbindung **aller** Prompts aus `prompts/` (DE & EN) – dynamisch
- Einbindung der Inhalte aus `data/` (robuste Parser, fehlerhafte Dateien werden übersprungen)
- Optional: Tavily-News (`TAVILY_API_KEY`) für aktuelle Meldungen
- Optional: OpenAI (`OPENAI_API_KEY`) zur inhaltlichen Veredelung (LLM)
- Optional: PDF-Export via WeasyPrint
- Optional: DB-Logging (SQLAlchemy + Postgres/SQLite) für Feedback & Nutzungsdaten
- Saubere Logging-Konfiguration, Healthcheck, CORS

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Schlüssel eintragen
uvicorn main:app --reload  # Entwicklung
# oder: uvicorn main:app --host 0.0.0.0 --port 8000
```

### API

- `GET /health` – Healthcheck
- `POST /api/report` – Report generieren
  - Body (Beispiel):
    ```json
    {
      "language": "de",
      "company": "Muster AG",
      "industry": "Finanzen",
      "include_news": true,
      "format": "html"
    }
    ```

Rückgabe: JSON mit `html` oder `pdf_path` und Metadaten.

## Ordnerstruktur

```
app/
  routers/
    health.py
    report.py
services/
  config.py
  data_loader.py
  i18n.py
  llm.py
  news.py
  rendering.py
  logging_setup.py
gpt_analyze.py
templates/
  report_template_de.html
  report_template_en.html
prompts/
data/
assets/
requirements.txt
main.py
```

> Hinweis: Einige Dateien in `prompts/` oder `data/` waren im Anhang unvollständig (z. B. mit `...`).
> Der Loader überspringt solche Fragmente robust und protokolliert Warnungen – damit bleibt das
> Backend dennoch stabil lauffähig.
