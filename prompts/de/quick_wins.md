# Quick Wins – sofort umsetzbare Maßnahmen

## Stilhinweis

Die Quick‑Wins sollen wie gut gemeinte Hinweise aus der Praxis wirken. Verwenden Sie einen warmen, verständlichen Ton und ganze Sätze, um auch Leser:innen ohne technisches Vorwissen mitzunehmen. Orientieren Sie sich am folgenden Beispieltext, der zeigt, wie man KI‑Themen greifbar und freundlich formuliert:

> Wenn heute von „Künstlicher Intelligenz“ die Rede ist, denken viele an komplizierte Technik, riesige Konzerne oder Zukunftsvisionen, die mit dem eigenen Alltag wenig zu tun haben. Doch für kleine und mittlere Unternehmen, für Freiberufler und Selbstständige, liegt genau hier eine große Chance: KI ist längst nicht mehr nur ein Werkzeug für die „Großen“. Sie kann auch in überschaubaren Strukturen helfen, den Arbeitsalltag leichter, klarer und effizienter zu gestalten.
>
> Aus jahrzehntelanger Erfahrung als Geschäftsführer in der Medienbranche weiß ich: Wirkliche Fortschritte entstehen nicht durch Schlagworte oder Hochglanzpräsentationen, sondern durch Lösungen, die im Alltag tragen. KI kann zum Beispiel Routinearbeiten abnehmen, dabei unterstützen, Informationen schneller einzuordnen oder neue Wege der Kundenansprache eröffnen. Und oft geht es gar nicht darum, alles sofort umzukrempeln, sondern in kleinen Schritten anzufangen – dort, wo es spürbar entlastet.

Verwenden Sie einen ähnlichen Erzählstil: Jede Maßnahme soll mit einem fett formatierten Schlüsselwort beginnen und dann in ein bis zwei vollständigen Sätzen beschreiben, was getan wird, welcher konkrete Nutzen daraus entsteht und wie aufwendig die Maßnahme ist (z. B. „geringer Aufwand“, „mittelgroßer Aufwand“). Verzichten Sie auf Bulletpoints und Fachjargon – schreiben Sie so, als ob Sie einem Freund oder einer Kollegin erklären, wie sie sofort loslegen kann.

Erstellen Sie eine HTML‑Liste (`<ul>…</ul>`) mit höchstens drei Quick Wins für das Unternehmen. Jede Zeile soll ein prägnanter Satz sein, der eine konkrete Sofortmaßnahme beschreibt, die innerhalb der nächsten 0–3 Monate realistisch umsetzbar ist. Beginnen Sie jede Zeile mit einem fettgedruckten Schlüsselwort (`<b>…</b>`) und formulieren Sie den Nutzen klar und positiv.

Nutze die Angaben aus den Freitextfeldern (Vision, größtes Potenzial, Moonshot, Einsatzbereich, strategische Ziele) sowie branchenspezifische Informationen, um maßgeschneiderte Vorschläge zu machen. Berücksichtige optional das wöchentliche Zeitbudget, vorhandene Werkzeuge, Hinweise auf regulierte Branchen, Trainingsinteressen und die Vision‑Priorität, um die Quick Wins weiter an Ressourcen, Compliance‑Rahmen, Lernbedarf und Strategie anzupassen – ohne die Variablennamen wörtlich zu nennen. Je geringer das Zeitbudget (z. B. ≤ 5 Stunden pro Woche), desto kleiner und schneller sollte der Quick Win sein; bei größerem Zeitbudget (z. B. 5–15 Stunden) dürfen die Maßnahmen etwas umfangreicher ausfallen.

Beachten Sie folgende Leitlinien:

- **Dateninventur:** Wenn die Datenqualität niedrig oder unklar ist, sollte die erste Maßnahme eine strukturierte Dateninventur oder ein Data‑Clearing sein.
 - **Automatisierung & Skripte:** Bei Interesse an Automatisierung oder geringem Zeitbudget kann eine kleine Automatisierung – zum Beispiel mit allgemeinen No‑Code‑Tools – ein Quick Win sein.  Nennen Sie keine spezifischen Produktnamen (wie Zapier oder n8n), sondern beschreiben Sie die Lösung allgemein.
- **Governance light:** Für Solo‑Unternehmen oder kleine Teams kann eine „Policy Light“ (eine kurze, leicht verständliche KI‑Richtlinie) ein sinnvoller Quick Win sein.
- **Pilot & Feedback:** Wenn das größte Potenzial in GPT‑Services oder einem KI‑Portal liegt, kann ein MVP‑Pilot mit ersten Kunden oder Partnern ein wertvoller Quick Win sein.
- Wähle maximal drei Quick Wins; wiederhole keine Punkte aus den Empfehlungen oder dem Maßnahmenplan.

Sollte zu wenig Kontext vorhanden sein, gib nur die wenigen verfügbaren Quick Wins aus. Sind gar keine sinnvollen Vorschläge ableitbar, gib als Liste den Hinweis aus: `<ul><li>Keine Quick Wins ableitbar. Für konkrete Vorschläge werden mehr Angaben benötigt.</li></ul>`.

Die Ausgabe ist ausschließlich ein HTML‑Block mit einer ungeordneten Liste (`<ul>…</ul>`), der 1–3 `<li>`‑Einträge enthält. Jeder Eintrag besteht aus einem fett gedruckten Titel und ein bis zwei freundlichen, ganzen Sätzen, die Aufwand, Nutzen und ein mögliches erstes Vorgehen beschreiben. Bei fehlendem Kontext geben Sie statt einer Liste die oben genannte Fehlermeldung aus.

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
