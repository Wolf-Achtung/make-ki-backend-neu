Developer: # Aktuelle KI-Tools & Software für {{ branche }} (Stand: {{ datum }})

Beginnen Sie mit einer kurzen konzeptuellen Checkliste (3-7 Punkte), was Sie zur Erfüllung der Aufgabe tun werden. Erstellen Sie anschließend eine klar strukturierte Übersicht der relevantesten KI-Tools für {{ branche }} anhand folgender Vorgaben:

**1. Auswahlkriterien:**
- Praxisrelevanz, Innovationsgrad, Datenschutz (DE/EU berücksichtigen)
- Kompatibilität mit Ihrer IT-Infrastruktur ({{ it_infrastruktur }}) und Unternehmensgröße ({{ unternehmensgroesse }})
- Bezug zu typischen Anwendungsfällen wie {{ hauptleistung }}, {{ projektziel }}, {{ zielgruppen }}

**2. Branchen-Kontext:**
- Nutzen Sie die angegebene branchenspezifische Tool-Liste als Grundlage: {{ tools_list }}
- Ergänzen Sie ggf. mit tagesaktuellen Websearch-Links, sofern dort neue oder relevante Tools enthalten sind: {{ websearch_links_tools }}

**3. Darstellung:**
- Stellen Sie die Tools ausschließlich in einer HTML-Tabelle mit genau vier Spalten dar: **Name**, **Usecase/Einsatz**, **Kosten**, **Link**.
- Die Spalte **Kosten** enthält eine grobe Preisspanne als String (z.B. „ab 29 €/Monat“, „kostenlos“); zusätzliche Spalten für Anbieter oder Datenschutz sind nicht nötig.
- Listen Sie maximal 5–7 Tools auf, sortiert nach Relevanz für {{ branche }} und Ihre Hauptleistung {{ hauptleistung }}. Sind weniger als 5 passende Tools vorhanden, listen Sie nur diese auf. Gibt es keine passenden Tools, geben Sie stattdessen ausschließlich den Hinweis „Keine relevanten Tools gefunden.“ aus und verzichten Sie auf die Tabelle.
- Wählen Sie nur Lösungen, die für {{ branche }} und die Hauptleistung {{ hauptleistung }} besonders relevant sind. Vermeiden Sie Dopplungen mit Tools aus anderen Kapiteln.
- Verzichten Sie auf generische Praxistipps oder Einleitungshinweise – diese gehören in die Roadmap.

**Hinweis:**
- Geben Sie die Tabelle direkt als HTML aus, ohne Code-Fences oder Umrahmungen. Halten Sie Spaltenüberschriften kurz und prägnant.

Nach Erstellung der Tabelle oder des Hinweises führen Sie eine kurze Überprüfung durch, ob alle Auswahlkriterien und Vorgaben eingehalten wurden. Falls Ihnen ein Fehler auffällt, korrigieren Sie ihn selbstständig, bevor Sie das Ergebnis abschließend ausgeben.

## Output Format

- Die Ausgabe erfolgt als HTML-Tabelle mit exakt vier Spalten in folgender Reihenfolge: Name (String), Usecase/Einsatz (1–2 Sätze), Kosten (String, z.B. „ab 29 €/Monat“, „kostenlos“, „Preisspanne: 20–100 €/Monat“), Link (gültige URL im <a>-Tag oder Text „keine Angabe“).
- Beispiel:

<table>
  <tr>
    <th>Name</th>
    <th>Usecase/Einsatz</th>
    <th>Kosten</th>
    <th>Link</th>
  </tr>
  <tr>
    <td>ToolA</td>
    <td>Kundendialog automatisieren</td>
    <td>ab 29 €/Monat</td>
    <td><a href="https://beispiel.de">Webseite</a></td>
  </tr>
  <tr>
    <td>ToolB</td>
    <td>Qualitätskontrolle in Fertigung</td>
    <td>kostenlos</td>
    <td><a href="https://beispiel2.de">Webseite</a></td>
  </tr>
  <!-- max. 5–7 Zeilen, weniger Zeilen wenn weniger relevante Tools verfügbar sind -->
</table>

- Wenn keine relevanten Tools gefunden werden, geben Sie nur den Hinweis „Keine relevanten Tools gefunden.“ aus, ohne Tabelle.
- Die HTML-Tabelle muss in reinem HTML-Format ausgegeben werden, ohne Code-Fences oder andere Umrahmungen.