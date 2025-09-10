# Hauptrisiken – potenzielle Herausforderungen

Erstelle eine HTML‑Liste (`<ul>…</ul>`) mit maximal drei Hauptrisiken, die für den Einsatz von KI im Unternehmen relevant sind. Jede Zeile beginnt mit einem fettgedruckten Schlagwort (`<b>…</b>`) und beschreibt kurz das Risiko sowie – falls sinnvoll – eine erste Maßnahme zur Minimierung.

Nutze die Angaben aus den Bereichen Compliance, Hemmnisse, Risikofreude und Datenschutz sowie externe Faktoren wie Rechtsunsicherheit, begrenztes Budget, Zeitmangel, unklare Datenqualität, Bias/Transparenz oder Lieferantenabhängigkeit. Ergänzend kannst du Zeitbudget, vorhandene Tools, Hinweise auf regulierte Branchen, Trainingsinteressen und die Priorisierung der Vision berücksichtigen, um zusätzliche Risikodimensionen zu erkennen – ohne diese Variablennamen wörtlich zu nennen.

Priorisiere die Risiken in folgender Reihenfolge, sofern relevant:

1. **Rechtslage & Compliance:** Unsichere Rechtslage, fehlende Datenverarbeitungsverträge oder unzureichende Einwilligungen können zu rechtlichen Risiken führen; als Gegenmaßnahme hilft ein Datenschutz‑Audit und die Anpassung an EU‑AI‑Act und DSGVO.
2. **Datenschutz & Datenqualität:** Mangelhafte Datenqualität, fehlende Löschkonzepte oder unklare Datentransparenz bergen Risiken für Vertraulichkeit und Fairness; Abhilfe schaffen strukturierte Dateninventur, klare Lösch- und Zugriffskonzepte sowie regelmäßige Bias‑Checks.
3. **Budget‑ & Ressourcen‑Engpässe:** Geringes Budget, begrenztes Zeitbudget oder unzureichende Expertise können den Fortschritt hemmen; Planung schlanker Maßnahmen, Nutzung externer Services und gezielte Weiterbildungen reduzieren dieses Risiko.

Falls eine dieser Kategorien im Kontext nicht zutrifft, kannst du sie durch ein anderes relevantes Risiko ersetzen (z. B. Abhängigkeit von einzelnen Anbietern). In jedem Fall dürfen die KPI‑Kategorien (Digitalisierung, Automatisierung, Papierlosigkeit, KI‑Know‑how) nicht als Risiko genannt werden.

Die Ausgabe erfolgt ausschließlich als HTML‑String mit einer ungeordneten Liste (`<ul>…</ul>`). Keine weiteren Erklärungen oder Kommentare im Output.

## Zusätzliche Anweisungen für den KI‑Status‑Report (DE)

Die folgenden Richtlinien heben den KI‑Status‑Report auf den Gold‑Standard. Füge sie an den Schluss deiner bestehenden Promptvorlagen an, damit die generierten Reports einheitlich, präzise und handlungsorientiert sind.

### Listen kürzen und zusammenfassen

* **Quick Wins (3 Punkte)** – Liste höchstens drei unmittelbar umsetzbare Erfolge. Falls mehr Ideen existieren, fasse sie am Ende unter einem Sammelpunkt „Weitere Quick Wins“ zusammen. 
* **Risiken (3 Punkte)** – Nenne maximal drei Risiken. Bei zusätzlichen Risiken ergänze einen Sammelpunkt „Weitere Risiken“, der diese kurz zusammenfasst. 
* **Empfehlungen (5 Punkte)** – Präsentiere nicht mehr als fünf Empfehlungen. Zusätzliche Vorschläge werden unter „Weitere Empfehlungen“ aggregiert.

### Struktur der Quick Wins

Jeder Quick Win besteht aus den folgenden Feldern:

1. **Titel** – prägnante Bezeichnung der Maßnahme.
2. **Zeitaufwand/Effort** – geschätzter zeitlicher Aufwand (z. B. „45 Minuten“ oder „1–2 Tage“).
3. **Tool/Link** – benutztes Werkzeug, Dienst oder Web‑Link; alternativ „–“.
4. **Erwarteter Effekt** – ein Satz, der den Nutzen beschreibt.
5. **Start heute?** – „Ja“ oder „Nein“, um anzugeben, ob sofort gestartet werden kann.

### 12‑Monats‑Roadmap

Die Roadmap enthält 6–8 Einträge und für jeden Monat die Spalten:

* **Monat/Zeitpunkt** – z. B. „Monat 1“, „Q2“ oder explizites Datum.
* **Aufgabe** – zentrale Tätigkeit.
* **Verantwortliche/Rolle** – Person oder Rolle, die die Aufgabe voranbringt; bei Unklarheiten „Inhaber:in/Projektlead“ nutzen.
* **Abhängigkeiten** – erforderliche Voraussetzungen oder vorherige Schritte („keine“ falls keine).
* **Nutzen/Outcome** – erwarteter Mehrwert oder Ziel.

### Gamechanger‑Kapitel

Dieses Kapitel präsentiert bis zu drei innovative Ansätze. Jeder Block sollte neben „Moonshot“, „Benchmark“, „Forecast“ und „Best‑Practice“ auch einen **Trade‑off/Side‑Effect** enthalten. Beschreibe in einem Satz mögliche Risiken oder Nebenwirkungen der Idee.

### Förderlogik

1. **Länder vor Bund** – Zeige stets mindestens zwei Landesprogramme (z. B. Berlin) und priorisiere diese vor Bundesprogrammen.
2. **Synonyme & Alias-Mapping** – Berücksichtige Synonyme (Solo, Start‑up, Gründung) und Kürzel (BE → Berlin) für die Suche.
3. **GründungsBONUS & Coaching BONUS** – Für Berlin unbedingt diese Programme einbeziehen, wenn relevant.

### KI‑Tools‑Tabelle

Sorge dafür, dass folgende Spalten enthalten sind: **Tool**, **Einsatzgebiet**, **Datensitz** (oder Datenschutz) und **Kosten** (oder Kostenkategorie). Verwende eine einheitliche Kostenskala (z. B. „&lt;100 €“, „100–500 €“, „500–1 000 €“, „> 1 000 €“). Ergänze eine Fußnote, die die Kostenskala erklärt.

### Weitere Hinweise

* Entferne verbleibende KPI‑Reste aus der Executive Summary.
* Nutze einen seriösen, optimistischen Ton. Formuliere Empfehlungen präzise mit klaren Verantwortlichen und Zeiträumen.
* Stelle sicher, dass Tabellen und Fußnoten nicht abgeschnitten werden und ordentliche Umbrüche haben.
