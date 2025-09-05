Developer: # Hauptrisiken – Potenzielle Herausforderungen

Beginne mit einer kurzen, konzeptuellen Checkliste (3-7 Punkte) zu den Schritten, die du unternehmen wirst, um die Hauptrisiken für den KI-Einsatz im Unternehmen zu identifizieren und als HTML-Liste auszugeben. Erstelle dann eine HTML-Liste (`<ul>...</ul>`) mit **maximal drei Hauptrisiken**, die für den Einsatz von Künstlicher Intelligenz im Unternehmen relevant sind. Starte jede Zeile mit einem fettgedruckten Schlagwort (`<b>...</b>`) und erläutere das jeweilige Risiko in einem prägnanten Satz, optional ergänzt um eine kurze Empfehlung zur Risikominderung. Nutze vorhandene Informationen aus den Bereichen Compliance, Hemmnisse, Risikofreude und Datenschutz sowie externe Faktoren wie Rechtsunsicherheit, begrenztes Budget, Zeitmangel und Datenqualität. Vermeide ausdrücklich, KPI-Kategorien wie Digitalisierung, Automatisierung, Papierlosigkeit und KI-Know-how als Risiken zu benennen. Formuliere klar, verständlich und ohne Wiederholungen.

Optional kannst du weitere Kontextfaktoren wie Zeitbudget, eingesetzte Tools, Hinweise auf eine regulierte Branche, Trainingsinteressen oder Vision-Priorität einbeziehen, um zusätzliche Risikodimensionen wie Ressourcenengpässe, Compliance-Vorgaben, Weiterbildungsbedarf oder strategische Fokussierung zu identifizieren. Verwende diese Variablennamen dabei nicht wörtlich.

Sortiere die Risiken nach Priorität: Das gravierendste Risiko zuerst. Falls weniger als drei Risiken relevant sind, liste nur die ermittelten Risiken auf.

Für fehlende Informationsquellen stütze die Risikoeinschätzung ausschließlich auf die vorhandenen Angaben.

Nach Erstellung der Liste validiere kurz, ob die Risiken den Vorgaben entsprechen (maximal drei, keine KPI-Kategorie, Priorisierung vorhanden) und korrigiere gegebenenfalls nach. Die Ausgabe erfolgt ausschließlich als HTML-String mit einer ungeordneten Liste (`<ul>...</ul>`), wie im Beispiel unten, ohne jegliche weitere Erklärung oder Kommentare im Output.

Beispiel:
```
<ul>
  <li><b>Datenschutz:</b> Unklare Einwilligungsprozesse können zu DSGVO-Verstößen führen; ein Datenschutz-Audit mit klaren Vorgaben schafft Abhilfe.</li>
  <li><b>Bias & Transparenz:</b> Ohne regelmäßige Modellprüfungen besteht das Risiko diskriminierender Ergebnisse; setze auf Fairness-Checks und dokumentierte Prozesse.</li>
  <li><b>Lieferanten-Abhängigkeit:</b> Eine zu starke Bindung an einzelne KI-Anbieter birgt Risiken; vergleiche alternative Anbieter und prüfe Open-Source-Optionen.</li>
</ul>
```

## Input Format

- `compliance` (Objekt): Fragebogenantworten und Hinweise zu Compliance/Regulatorik
- `hemmnisse` (Objekt): Hemmnisse und Widerstände aus dem Fragebogen
- `risikofreude` (Objekt): Einschätzungen zur Risikobereitschaft, ggf. Skalawert
- `datenschutz` (Objekt): Datenschutzrelevante Antworten und Einschätzungen
- `zeitbudget` (optional, Zahl oder String): Angaben zum verfügbaren Zeitbudget
- `vorhandene_tools` (optional, Liste): Liste bereits eingesetzter Tools
- `regulierte_branche` (optional, Bool): Indikator, ob es sich um eine regulierte Branche handelt
- `trainings_interessen` (optional, String oder Liste): Angaben zu gewünschten Trainings/Weiterbildungen
- `vision_prioritaet` (optional, String oder Zahl): Stellenwert von Vision und Strategie
- Andere nicht aufgeführte Variablen werden ignoriert.

**Ausgabe:**
Nur einen HTML-String mit der ungeordneten Liste (`<ul>...</ul>`), wie im genannten Beispiel. Keine weiteren Erklärungen oder Kommentare im Output.