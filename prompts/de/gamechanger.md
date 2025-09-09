Developer: Ziel: Erzeuge das Kapitel **Innovation & Gamechanger** als gültiges HTML ohne <html>-Wrapper.

Kontext:
- Branche: {{ branche }}
- Unternehmensgröße: {{ company_size_label }} ({{ company_size_category }})
- Region/Bundesland: {{ bundesland|default('') }}
- Benchmark/Dimensionen: {{ benchmarks|tojson }}
- KPI-Kacheln: {{ kpis|tojson }}
- Innovations-Intro (optional): {{ branchen_innovations_intro|default('') }}
- Förder-Badges (optional): {{ funding_badges|default([])|join(', ') }}

**Checkliste:**
1. Eingabedaten analysieren und Verfügbarkeit prüfen.
2. Kapitelstruktur gemäß Vorgaben festlegen.
3. HTML-Abschnitte mit erlaubten Tags generieren und prüfen.
4. Vorgaben für Auslassungen und Platzhalter einhalten.
5. Finale Struktur in Output-Format bringen.

**Regeln:**
- Verwende nur die Tags <h3>, <p>, <ul>, <ol>, <table>.
- Keine Meta-Kommentare. Keine Platzhaltertexte.

**Struktur (max. ½ Seite):**
1. <h3>Moonshot</h3>
   - Ein kühner, branchenspezifischer Titel und ein Satz (konkret, messbar, kein Marketingsprech).
2. <h3>Reifegrad-Benchmark</h3>
   - <table> mit bis zu 4 Zeilen (Digitalisierung, Automatisierung, Papierlos, KI-Know-how); Spalten: Dimension | Ihr Wert (%) | Branchenmedian (%) | Gap (%).
   - Fehlen Werte für eine Zeile, diese Zeile auslassen. Gibt es keine Benchmarkdaten, Tabelle weglassen.
3. <h3>Förder-Forecast</h3>
   - <ul> mit 3 Punkten: „Startet“, „Endet“, „Wichtige Änderung (Kurzsatz + Quelle)“.
   - Ist für einen Punkt keine seriöse Information verfügbar, schreibe stattdessen: „– aktuell keine verlässlichen Änderungen bekannt“.
   - Teilweise Informationen sind erlaubt: Wenn für einen Punkt Informationen vorliegen, diese angeben, ansonsten Regel wie oben anwenden.
4. <h3>Nächste Schritte</h3>
   - <ul>: Für 30 Tage 2–3 konkrete Maßnahmen; für 6 Monate 2–3 Meilensteine (kurz und prüfbar). Fehlen Maßnahmen/Meilensteine, dann weglassen.
5. <h3>Realtime-Check</h3>
   - <p>: Kurzer Prüfhintweis zu Datenschutz (DSGVO/EU-AI-Act), Datenlage, Pilot-Metriken; kein Platzhalter. Fehlt Info, diesen Abschnitt auslassen.
6. <h3>Best-Practices</h3>
   - <ul>: Zwei knappe branchenspezifische Beispiele mit Ergebnis oder Kennzahl, kein Toolname. Fehlen Beispiele, den Abschnitt auslassen.

{{ prompt_prefix }}
{{ prompt_suffix }}

Beachte: Abschnitte ohne verfügbare Daten müssen inklusive Überschrift vollständig weggelassen werden; es dürfen keine Platzhalter erscheinen. Validierung: Nach Generierung des Outputs prüfen, ob die strikte Struktur, Vorgaben zu Auslassungen sowie ausschließlich erlaubte HTML-Tags eingehalten wurden. Bei Abweichungen selbstständig korrigieren.

**Output-Format:**

Der Output MUSS exakt folgende Struktur und Reihenfolge haben (keine zusätzlichen Einleitungen):

<h3>Moonshot</h3>
<p>[Titel-Satz]</p>

<h3>Reifegrad-Benchmark</h3>
<table>
  <tr><th>Dimension</th><th>Ihr Wert (%)</th><th>Branchenmedian (%)</th><th>Gap (%)</th></tr>
  [bis zu 4 Datenzeilen, nur wenn Werte vorhanden sind]
</table>

<h3>Förder-Forecast</h3>
<ul>
  <li>Startet: [Datum/Text oder „– aktuell keine verlässlichen Änderungen bekannt“]</li>
  <li>Endet: [Datum/Text oder „– aktuell keine verlässlichen Änderungen bekannt“]</li>
  <li>Wichtige Änderung: [Kurzsatz + Quelle oder „– aktuell keine verlässlichen Änderungen bekannt“]</li>
</ul>

<h3>Nächste Schritte</h3>
<ul>
  <li>30 Tage: [Maßnahme 1], [Maßnahme 2], ...</li>
  <li>6 Monate: [Meilenstein 1], [Meilenstein 2], ...</li>
</ul>

<h3>Realtime-Check</h3>
<p>[Prüfhinweis-Satz, falls Info vorhanden]</p>

<h3>Best-Practices</h3>
<ul>
  <li>[Beispiel 1]</li>
  <li>[Beispiel 2]</li>
</ul>

*Abschnitte ohne Daten komplett (mit Überschrift) auslassen, keine Platzhalter verwenden.*

Nach Fertigstellung: Bestätige, dass die Ausgabe den Regeln und der Struktur entspricht. Falls nicht, passe den Output eigenständig entsprechend an.