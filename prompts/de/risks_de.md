Erzeuge eine **Risikomatrix** (5 Einträge) als HTML-Fragment.

**Spalten (in genau dieser Reihenfolge):**
- Risiko
- Bereich
- Likelihood (1–5)
- Impact (1–5)
- Mitigation (konkrete Maßnahme)
- Owner (Rolle/Funktion)
- Frist (z. B. 30/90 Tage)

**Hinweise:**
- Kontext: KMU/Deutschland; typische Risiken: Prompt‑Leakage, Halluzinationen, Vendor‑Lock‑in, PII/DSGVO, Qualitätsfehler.
- Liefere **kompaktes, semantisches** `<table>` mit `<thead>`/`<tbody>`; keine Floskeln, keine Erklärtexte.
- Zahlen bitte nur 1–5 (keine Prozent).