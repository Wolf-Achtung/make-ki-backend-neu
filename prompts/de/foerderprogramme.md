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