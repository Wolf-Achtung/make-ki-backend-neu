Developer: # Förderprogramme für Digitalisierung & KI (Stand: {{ datum }})

Beginnen Sie mit einer kurzen Checkliste (3-7 Punkte), welche konzeptionellen Schritte zur Auswahl und Darstellung der relevanten Förderprogramme vorgenommen werden. Stellen Sie anschließend die 3–5 relevantesten Förderprogramme (aktuell, passend für {{ branche }}, {{ bundesland }}, {{ unternehmensgroesse }}) in einer HTML-Tabelle dar. Berücksichtigen Sie Ihre bisherigen Erfahrungen mit Fördermitteln ({{ bisherige_foerdermittel }}) sowie Ihr Interesse an weiterer Förderung ({{ interesse_foerderung }}).

**1. Kriterien:**
- Förderhöhe (Summe oder Anteil)
- Zielgruppe
- Förderschwerpunkt (z. B. KI/Digitalisierung)
- Fristen
- Ansprechpartner/Link

**2. Branchen-Kontext:**
- Nutzen Sie die branchenspezifische Förderliste: {{ foerderprogramme_list }} (Format: strukturierte Liste von Förderprogrammen mit Name, Zielgruppe, Förderhöhe, Link)
- Ergänzen Sie ggf. neue Programme oder relevante News aus den Websearch-Ergebnissen: {{ websearch_links_foerder }}
- Berücksichtigen Sie auch Angaben zu bereits genutzten Fördermitteln und aktuellem Förderinteresse.

**3. Darstellung:**
- Verwenden Sie eine HTML-Tabelle mit folgenden Spalten: **Name**, **Zielgruppe**, **Förderhöhe**, **Link**.
- Fassen Sie die Förderhöhe kurz (z. B. „bis 50%“, „max. 10 000 €“). Listen Sie 3–5 relevante Programme, abgestimmt auf {{ branche }}, {{ bundesland }} und {{ unternehmensgroesse }}. Vermeiden Sie Dopplungen.
- Falls keine geeigneten Programme gefunden werden, zeigen Sie eine leere Tabelle und darunter den Hinweis: „Keine passenden Förderprogramme für die gewählten Kriterien gefunden.“
- Sortieren Sie die Programme nach Relevanz (Branche, Bundesland, Unternehmensgröße; höchste Relevanz zuerst).
- Tools oder andere Maßnahmen sind in separaten Kapiteln zu behandeln und hier zu vermeiden.

Nach Erstellung der Tabelle validieren Sie in 1–2 Sätzen, ob alle Kriterien erfüllt wurden (z. B. Relevanz, Anzahl, Dopplungen) und entscheiden Sie anhand des Ergebnisses, ob eine Korrektur erforderlich ist.

**Tabellenformat (HTML):**

Geben Sie ausschließlich folgende HTML-Struktur aus (ohne Code-Block-Markierungen):

<table>
  <tr>
    <th>Name</th>
    <th>Zielgruppe</th>
    <th>Förderhöhe</th>
    <th>Link</th>
  </tr>
  <tr>
    <td>[Programmname 1]</td>
    <td>[Zielgruppe 1]</td>
    <td>[Förderhöhe 1]</td>
    <td><a href="[Programm-Link-1]">Mehr erfahren</a></td>
  </tr>
  <!-- Bis zu 5 Programme aufführen -->
</table>
<!-- Falls keine Förderprogramme gelistet werden können: -->
<p>Keine passenden Förderprogramme für die gewählten Kriterien gefunden.</p>

**Variablen:**
- `{{ datum }}`: Aktuelles Datum
- `{{ branche }}`: Zielbranche
- `{{ bundesland }}`: Bundesland
- `{{ unternehmensgroesse }}`: Unternehmensgröße
- `{{ bisherige_foerdermittel }}`: Bereits genutzte Fördermittel
- `{{ interesse_foerderung }}`: Interesse an weiterer Förderung
- `{{ foerderprogramme_list }}`: Strukturierte Liste, idealerweise als Array von Objekten mit Feldern Name, Zielgruppe, Förderhöhe, Link
- `{{ websearch_links_foerder }}`: Optional, strukturierte Liste neuer Programme oder Nachrichten

**Hinweis:** Fehlen erforderliche Variablen oder ist die Liste der Förderprogramme leer, geben Sie die leere Tabelle und den Hinweistext aus.