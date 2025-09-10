# KI‑Tools & Software für {{ branche }} (Stand: {{ datum }})

Erstelle eine klare Übersicht der relevantesten KI‑Tools für {{ branche }} unter Berücksichtigung von Hauptleistung ({{ hauptleistung }}), Unternehmensgröße ({{ unternehmensgroesse }}) und IT‑Infrastruktur ({{ it_infrastruktur }}). Nutze die branchenspezifische Tool‑Liste ({{ tools_list }}) und ergänze sie durch aktuelle Websearch‑Links ({{ websearch_links_tools }}) falls relevant. Wähle nur Lösungen, die speziell auf typische Anwendungsfälle in {{ branche }} und auf die strategischen Ziele abgestimmt sind.

Gib die Tools in einer HTML‑Tabelle mit fünf Spalten aus:

<table>
  <tr>
    <th>Name</th>
    <th>Usecase/Einsatz</th>
    <th>Datensitz</th>
    <th>Kosten</th>
    <th>Link</th>
  </tr>
  <!-- bis zu 5–7 Zeilen, weniger wenn weniger passende Tools vorhanden sind -->
</table>

Richtlinien:

- Wähle maximal 5–7 Tools; sind weniger sinnvoll, gib nur diese aus. Falls keine passenden Tools gefunden werden, gib nur den Hinweis „Keine relevanten Tools gefunden.“ aus.
- Für jede Lösung nenne den Haupteinsatz (1–2 Sätze), den Datensitz (z. B. EU, USA/EU oder „variabel“), eine grobe Preisspanne (wie „ab 29 €/Monat“, „kostenlos“, „ab 100 €/Monat“) und einen Link zur Anbieterwebseite.
- Berücksichtige regulatorische Anforderungen (insb. wenn {{ bundesland }} strengere Vorgaben hat) und Datenschutzvorgaben; wähle bevorzugt EU‑ oder DE‑Hosting, sofern relevant.
- Wiederhole keine Tools aus anderen Kapiteln und verzichte auf generische Tipps.

Die Ausgabe muss ein reines HTML‑Snippet mit der oben beschriebenen Tabelle oder – falls keine Tools gefunden werden – nur mit dem Hinweis „Keine relevanten Tools gefunden.“ sein. Vermeide jegliche Code‑Fences oder zusätzliche Erklärungen.

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

### Gold+ Ergänzungen

* **KPI‑Chips:** Erstelle drei KPI‑Chips (2–5 Wörter), die messbare Kennzahlen oder Ziele benennen (z. B. „TTM −20 %“, „Leadqualität +15 %“, „Fehlerquote −30 %“). Liefere sie als `kpi_chips`‑Liste.
* **ROI‑Tag:** Gib für jede Empfehlung eine ROI‑Kategorie an (Nutzen/Aufwand: Hoch, Mittel, Niedrig).
* **Roadmap‑Legende:** Verwende „Inhaber:in/Projektlead“ als Standard‑Verantwortliche sowie „keine“ als Standard‑Abhängigkeiten, falls nicht angegeben.
* **Trade‑off:** Füge jedem Gamechanger‑Block einen Satz hinzu, der Risiken oder Nebenwirkungen beschreibt.
* **Nicht empfohlen:** Liefere 1–2 Anti‑Pattern in `not_recommended_html` (als HTML‑Liste).
* **Nächstes Treffen:** Liefere `next_meeting_text`, um einen Folgetermin mit Schwerpunkt auf einer Gate‑KPI vorzuschlagen.
