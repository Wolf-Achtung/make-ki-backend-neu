
Erzeuge eine **kuratiere Werkzeugtabelle** (mind. 6 Einträge) als HTML-Fragment für **{{branche_label}}**, Größe **{{unternehmensgroesse_label}}**, Hauptleistung **{{hauptleistung}}**.

**Spalten (genau diese, in dieser Reihenfolge):**
- Tool
- Domain
- EU/EWR? (Ja/Nein/Unklar)
- AVV/SCC (Hinweis)
- TCO/Monat (€, falls verfügbar; sonst "—")
- Primär-Use-Case
- Bemerkung (1 Satz, kein Marketing)

**Regeln:**
- **Konkret & verifizierbar** (keine Platzhalter). Domains müssen real sein.
- **Dedupe**: keine doppelten Tools.
- **Compliance-Hinweis** für Non‑EU‑Anbieter (AVV/SCC, Pseudonymisierung, Secrets vermeiden).
- **Kein Vendor‑Marketing**, keine Eigenwerbung, keine Floskeln.
- Wenn Live‑Quellen fehlen, nenne robuste Basistools: OpenAI, Aleph Alpha, DeepL, Zapier/Make, Notion, n8n/Airflow, Github Actions u.a. (nur wenn relevant).

**Ausgabe:** Semantische `<table class="compact tools">` mit `<thead>`/`<tbody>`. Keine Zusatztexte.
