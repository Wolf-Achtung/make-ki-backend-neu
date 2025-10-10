# KI-Backend Gold-Standard+ Patch (Quellen-Footer, Risks-Tabelle, Health Schema, Δ/Exec-Summary)

Dieses Paket enthält **vollständige Dateien** für die wichtigsten Änderungen (keine Snippets).  
Stand: 2025-10-10

## Enthaltene Dateien (Zielpfade relativ zum Backend-Root `make-ki-backend-neu-main/make-ki-backend-neu-main/`)

- `templates/pdf_template.html` – Quellen‑Footer & Print‑CSS.
- `gpt_analyze.py` – Hybrid Live‑Search, Quellen‑Footer, Platzhalter‑Support.
- `schema.py` – `get_schema_info()` für `/health`.
- `main.py` – `/health` erweitert um Schema‑Infos.
- `prompts/de/risks_de.md` – neue Spalten (Likelihood/Impact/Mitigation/Owner/Frist).
- `prompts/en/risks_en.md` – englisches Pendant.
- `prompts/de/executive_summary_de.md` – Pflicht: Δ‑Referenz zu Benchmarks.
- `prompts/en/executive_summary_en.md` – Required: Δ vs. benchmark.
- `tests/test_normalize_and_scores.py` – Unit‑Tests für Normalize & Scoring.

## Installation

1. Legen Sie ein Backup Ihres Backends an.
2. Entpacken Sie dieses Paket **über** Ihr Backend (Dateien überschreiben).
3. Optional: `pytest -q` in der Backend‑Root ausführen.

## Hinweise

- Der Quellen‑Footer wird mit `{SOURCES_FOOTER_HTML}` in `pdf_template.html` gefüllt.  
- `/health` liefert nun `schema.etag`, `schema.version` (falls im Schema) sowie `fields`.
- Die Executive Summary bleibt LLM‑generiert, verweist aber klar auf die Δ‑Werte.
- Die Risikomatrix ist nun tabellarisch harmonisiert (EU‑AI‑Act‑tauglich).

Viel Erfolg!