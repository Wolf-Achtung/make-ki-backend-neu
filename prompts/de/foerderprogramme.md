# Förderprogramme für Digitalisierung & KI (Stand: {{ datum }})

Liste die 3–5 relevantesten Förderprogramme für die Branche {{ branche }} im Bundesland {{ bundesland }} und für die Unternehmensgröße {{ unternehmensgroesse }} auf. Berücksichtige die bisherige Nutzung von Fördermitteln ({{ bisherige_foerdermittel }}) und das aktuelle Interesse an weiterer Förderung ({{ interesse_foerderung }}). Nutze die Programme aus {{ foerderprogramme_list }} und ergänze sie – falls sinnvoll – durch aktuelle Websearch‑Links ({{ websearch_links_foerder }}).

Stelle die Programme in einer HTML‑Tabelle mit vier Spalten dar:

<table>
  <tr>
    <th>Name</th>
    <th>Zielgruppe</th>
    <th>Förderhöhe</th>
    <th>Link</th>
  </tr>
  <!-- bis zu 5 Programme aufführen -->
</table>

Richtlinien:

- Wähle 3–5 Programme, die besonders gut zu {{ branche }}, {{ bundesland }} und {{ unternehmensgroesse }} passen. Falls keine geeigneten Programme gefunden werden, gib eine leere Tabelle und darunter den Hinweis „Keine passenden Förderprogramme für die gewählten Kriterien gefunden.“ aus.
- Fasse die Förderhöhe knapp (z. B. „bis 50 %“, „max. 10 000 €“). Sortiere die Programme nach Relevanz (Branche > Bundesland > Unternehmensgröße).
- Berücksichtige frühere Fördermittel und das Interesse an weiteren Programmen, um die Auswahl zu individualisieren.
- Tools oder andere Maßnahmen werden in separaten Kapiteln behandelt und gehören hier nicht hinein.

Die Ausgabe ist ein reines HTML‑Snippet: entweder die oben skizzierte Tabelle mit 0–5 Datenzeilen oder – wenn keine Programme passen – eine leere Tabelle und den Hinweis „Keine passenden Förderprogramme für die gewählten Kriterien gefunden.“. Vermeide weitere Kommentare oder Erklärungen im Output.

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
