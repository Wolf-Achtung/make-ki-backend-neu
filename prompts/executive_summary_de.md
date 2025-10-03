<!-- File: prompts/executive_summary_de.md -->
**Rolle:** Strategy‑Consultant. **Aufgabe:** prägnante **Executive Summary** zum KI‑Status.

**Eckdaten**
- **Unternehmen:** Branche={{branche}}, Größe={{unternehmensgroesse}}, Region={{bundesland}}, Leistung={{hauptleistung}}
- **Kennzahlen:** Score={{score_percent:.1f}} %, ROI Jahr 1={{roi_year1_pct:.1f}} %, Payback={{payback_months:.1f}} Monate

**Ausgabe**
- **1 kompakter Absatz (nur ein `<p>…</p>`)** mit **3–5 messbaren Kernaussagen** (handlungsleitend, ohne Floskeln).

**Schlusszeile (separat, außerhalb des `<p>`):** `Stand: {{date}}`
