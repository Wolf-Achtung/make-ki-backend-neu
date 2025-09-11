# Compliance‑Status & Handlungsempfehlungen

Analysieren Sie die aktuelle Compliance‑Situation des Unternehmens anhand der Formulardaten (z. B. Datenschutzbeauftragte:r, technische Schutzmaßnahmen, DSFA, Meldewege, Löschregeln, Kenntnisse zum EU AI Act). Sie können intern eine kurze Checkliste zur Strukturierung nutzen, geben Sie diese jedoch nicht im Output aus.

## 1. Gesetzliche Anforderungen & Richtlinien
- Listen Sie die zutreffenden Rechtsgrundlagen auf, z. B. DSGVO, ePrivacy, Digital Services Act, Wettbewerbs- und Verbraucherschutzrecht und ggf. branchenspezifische Standards.
- Erläutern Sie stichpunktartig, wie vorhandene Unternehmensstrukturen (z. B. Datenschutzbeauftragte:r, technische Maßnahmen) diese Anforderungen erfüllen oder wo Lücken bestehen.

## 2. Consent Management & Kundenrechte
- Beschreiben Sie stichpunktartig das Einwilligungsmanagement (Consent Management), CRM-Prozesse, die Umsetzung von Privacy by Design/Default sowie relevante Besonderheiten.
- Beziehen Sie bestehende Prozesse wie Meldewege, Löschregeln und internes KI-Know-how ein.

## 3. KI-spezifische Compliance
- Listen Sie stichpunktartig besondere Pflichten bei der Nutzung von KI auf: Dokumentation, Transparenzpflichten, Fairness- und Bias-Analysen, Folgenabschätzungen sowie Anforderungen durch den EU AI Act (sofern relevant).

## 4. Sofortmaßnahmen & Strategische Schritte
- Nennen Sie 3–4 priorisierte Maßnahmen für die kurzfristige und mittelfristige Umsetzung, z. B.:
  - Datenschutz-Check
  - Erstellung einer Auftragsverarbeitungsvereinbarung
  - Einführung eines AI-Governance-Rahmens
  - Mitarbeiterschulungen
  - Lieferantenprüfung
  - Einführung eines Datenschutz-Management-Systems (DSMS)
- Passen Sie diese Maßnahmen an Unternehmensgröße und Haupttätigkeit an. Nutzen Sie die Formulardaten als Ausgangsbasis.

## 5. Schwachstellen & Lösungen
- Nennen Sie 2–3 aktuelle Schwachstellen (z. B. unklare Datenflüsse, fehlende Löschkonzepte, unzureichende Dokumentation).
- Geben Sie für jede Schwachstelle direkt einen konkreten Lösungsvorschlag bzw. ersten Behebungsschritt an.

**Beispiel-Tabelle:**

| Schwachstelle               | Lösungsvorschlag                                   |
|----------------------------|---------------------------------------------------|
| Fehlende Löschregelungen    | Entwicklung und Umsetzung eines klaren Löschkonzepts |
| Unzureichende Dokumentation | Erstellung einer aktuellen Verfahrensbeschreibung      |

**Hinweise:**
- Verwenden Sie ausschließlich die im Fragebogen befindlichen Informationen.
- Geben Sie keine Platzhalter oder Abkürzungen wie „n. v.“ aus; lassen Sie Punkte ohne Angaben weg.
- Vermeiden Sie generische Checklisten.
- Führen Sie keine Tools, Förderprogramme oder Roadmap-Maßnahmen auf; diese werden in separaten Abschnitten behandelt.

**Formatierung:**
- Geben Sie die Antwort als gegliedertes Markdown-Dokument mit den fünf nummerierten Hauptabschnitten (## 1.–## 5.) aus.
- Nutzen Sie für jeden Abschnitt kurze, stichpunktartige Listen.
- Im Abschnitt 5 können Sie eine Tabelle oder eine Liste zur Darstellung verwenden.
- Lassen Sie Abschnitte oder Stichpunkte ohne Angaben weg.

Setzen Sie reasoning_effort = medium, damit alle relevanten Aspekte sorgfältig, aber kompakt geprüft werden.

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
