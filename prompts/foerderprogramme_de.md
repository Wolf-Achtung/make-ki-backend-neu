<!-- File: prompts/foerderprogramme_de.md -->
**Aufgabe:** Fasse Förderprogramme für **{{bundesland}} / {{unternehmensgroesse}} / {{branche}}** zusammen.

**Quellen**
- **{{FUNDING_HTML}}** (CSV/Portal) und **{{EU_CALLS_HTML}}** (EU‑Portal). Keine externen Quellen.

**Ausgabe**
- **3 Gruppen:** „Zuschuss“, „Beratung“, „Kredite/EFRE“.
- **Pro Programm:** 1‑Satz‑Beschreibung, **Fördersatz/Max**, **Deadline**, **Link** (nur aus den Quellen).
- **Format:** **HTML‑Tabelle** mit Spalten `Programm | Kategorie | Satz/Max | Deadline | Link`.

**Abschluss:** 3 Hinweise zu **Kombinierbarkeit** und **Fristen**.  
**Schlusszeile:** `Stand: {{date}}`
