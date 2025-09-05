Developer: # Maßnahmenplan: Digitalisierung & KI in {{ branche }} (Schwerpunkt {{ hauptleistung }})

Beginnen Sie mit einer prägnanten Checkliste (3–7 Stichpunkte), welche konzeptionellen Schritte für die Erstellung des Maßnahmenplans durchgeführt werden.

Erstellen Sie einen Maßnahmenplan für die kommenden 12 Monate, unterteilt in drei Zeitstufen: **0–3 Monate**, **3–6 Monate** und **6–12 Monate**. Listen Sie für jede Zeitstufe 2–3 priorisierte Maßnahmen auf. Jede Maßnahme besteht aus einem Stichwort (`title`) und einer kurzen ein-Satz-Umsetzung (`description`). Richten Sie die Auswahl an Ihren strategischen Zielen ({{ projektziel }}) und priorisierten Usecases ({{ ki_usecases }}) aus.

**Berücksichtigen Sie:**
- Branchenspezifische Herausforderungen
- Unternehmensgröße ({{ unternehmensgroesse }})
- Digitalisierungs- und Automatisierungsgrad ({{ digitalisierungsgrad }}/{{ automatisierungsgrad }})
- Anteil papierloser Prozesse ({{ prozesse_papierlos }})
- Vorhandene KI-Einsätze ({{ ki_einsatz | join(', ') }})
- Internes KI-Know-how ({{ ki_knowhow }}) und Risikofreude ({{ risikofreude }})

Passen Sie die Maßnahmen außerdem dem Investitionsbudget ({{ investitionsbudget }}) an und nennen Sie relevante Tools oder Förderprogramme nur stichpunktartig – Details erscheinen in separaten Kapiteln.

**Wichtige Hinweise:**
- Vermeiden Sie generische Tipps; jede Maßnahme muss individuell sinnvoll und konkret sein.
- Nutzen Sie stichpunktartige Darstellung und vermeiden Sie Wiederholungen anderer Kapitel.

**Beispielhafte Roadmap:**

– **0–3 Monate:** Fragebogen finalisieren und LLM-Prototyp testen; Mini-Landingpage veröffentlichen; erste Feedbackschleife starten.
– **3–6 Monate:** Pilotprojekt mit 1–2 Kunden oder Partnerbetrieben ({{ branche }}) durchführen; Prozesse weiter optimieren; Förderanträge stellen.
– **6–12 Monate:** MVP zu skalierbarem White-Label-Beratungstool weiterentwickeln; neue Märkte erschließen; Partnernetzwerk ausbauen.

Nutzen Sie diese Beispiele als Orientierung und passen Sie die Inhalte individuell an Hauptleistung und Unternehmensgröße an.

## Output Format

Liefern Sie das Ergebnis ausschließlich als Markdown-JSON-Codeblock im folgenden Schema:

```json
{
  "branche": "string (wie übergeben)",
  "hauptleistung": "string (wie übergeben)",
  "zeitplan": [
    {
      "zeitstufe": "0–3 Monate" | "3–6 Monate" | "6–12 Monate",
      "massnahmen": [
        { "title": "string", "description": "string" },
        { "title": "string", "description": "string" },
        { "title": "string", "description": "string" }
      ]
    },
    ...
  ]
}
```

- Felder wie "zeitstufe" und "massnahmen" sind immer erforderlich.
- Für jede Zeitstufe müssen 2–3 Maßnahmen enthalten sein.
- Verwenden Sie die übergebenen Platzhalterwerte für alle Variablen (meist Strings, `ki_einsatz` als Komma-getrennte Zeichenkette).
- Fehlt ein Wert, geben Sie das entsprechende Feld als leeren String oder eine leere Liste aus (z. B. `"investitionsbudget": ""`).
- Geben Sie keinerlei zusätzliche Kommentare oder Erklärungen außerhalb des JSON-Codeblocks aus.

Überprüfen Sie am Ende, ob das JSON alle geforderten Felder vollständig und korrekt enthält. Wenn nicht, verbessern Sie die Ausgabe entsprechend.