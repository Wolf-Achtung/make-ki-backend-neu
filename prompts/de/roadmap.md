# Maßnahmenplan – Digitalisierung & KI in {{ branche }} (Schwerpunkt {{ hauptleistung }})

Erstelle einen schlanken, realistischen Maßnahmenplan für die kommenden zwölf Monate, unterteilt in drei Zeitabschnitte: **0–3 Monate**, **3–6 Monate** und **6–12 Monate**. Gib das Ergebnis als HTML‑Liste (`<ul>…</ul>`) mit genau drei `<li>`‑Elementen aus. Jeder Eintrag beginnt mit dem jeweiligen Zeitraum (fett) und beschreibt anschließend 2–3 priorisierte Maßnahmen in einem Satz, getrennt durch Semikolons.

Berücksichtige bei der Planung:

* die strategischen Ziele ({{ projektziel }}) und priorisierten Usecases ({{ ki_usecases }})
* die Unternehmensgröße ({{ unternehmensgroesse }}) und das Investitionsbudget ({{ investitionsbudget }})
* den Digitalisierungs‑ und Automatisierungsgrad, den Anteil papierloser Prozesse und bereits vorhandene KI‑Einsätze ({{ ki_einsatz | join(', ') }})
* internes KI‑Know‑how und Risikofreude
* individuelle Faktoren wie Zeitbudget, vorhandene Werkzeuge, regulierte Branchen, Trainingsinteressen und die Vision‑Priorität (ohne diese Variablennamen wörtlich zu nennen)

Beispiele für Maßnahmen (je nach Kontext anzupassen):

- **0–3 Monate:** Dateninventur starten; Fragebogen finalisieren und einen LLM‑Prototyp testen; eine Mini‑Landingpage zur Lead‑Generierung veröffentlichen.
- **3–6 Monate:** Ein MVP‑Portal entwickeln und erste Pilotkund:innen onboarden; den priorisierten Prozess automatisieren (z. B. Ticketing); Förderanträge stellen und Kooperationspartner gewinnen.
- **6–12 Monate:** Ein White‑Label‑Beratungstool skalieren; Governance‑Strukturen etablieren; neue Märkte erschließen und Trainingsangebote ausbauen.

Nutze diese Beispiele als Inspiration und passe die Inhalte individuell an Hauptleistung, Unternehmensgröße und Ressourcen an. Vermeide generische Tipps und Wiederholungen aus anderen Kapiteln. Wenn eine Maßnahme bereits als Quick Win oder Empfehlung genannt wurde, wähle einen anderen Fokus.

Die Ausgabe besteht ausschließlich aus einer HTML‑Liste mit drei `<li>`‑Elementen (für die drei Zeitabschnitte). Es dürfen keine Tabellen oder JSON‑Blöcke ausgegeben werden.