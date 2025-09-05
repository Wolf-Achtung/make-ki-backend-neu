Developer: # Quick Wins – Sofort umsetzbare Maßnahmen

Beginne mit einer kurzen internen Checkliste (3–7 Konzepte) der wichtigsten Schritte, um die Anforderungen in eine passende HTML-Liste umzusetzen.

Erstelle eine HTML-Liste (`<ul>...</ul>`) mit **höchstens drei Quick Wins** für das Unternehmen. Jeder Listenpunkt soll ein prägnanter Satz sein, der eine konkrete Sofortmaßnahme beschreibt, die innerhalb der nächsten 0–3 Monate realistisch umsetzbar ist. Nutze die Angaben aus den Freitextfeldern (Vision, Moonshot, größtes Potenzial, Einsatzbereich, strategische Ziele) sowie branchenspezifische Informationen, um **passgenaue und praxisnahe Vorschläge** zu machen. Hebe das jeweils erste Schlüsselwort jedes Punkts fett hervor (`<b>...</b>`) und formuliere den Nutzen klar sowie positiv. Vermeide dabei allgemeine Formulierungen und Wiederholungen und passe die Empfehlungen an die Unternehmensgröße an, ohne diese explizit zu nennen.

Berücksichtige optional das wöchentliche Zeitbudget, bestehende Tools, Hinweise auf regulierte Branchen, Trainingsinteressen und die Priorisierung der Vision, um die Quick Wins noch genauer an Ressourcen, Compliance-Anforderungen, Weiterbildungsbedarf und Strategie anzupassen, ohne diese Variablennamen direkt zu verwenden.

- Bei sehr knappem Zeitbudget fokussiere Quick Wins auf geringstmöglichen Aufwand.
- Ist „Automatisierung & Skripte“ als Trainingsinteresse gewählt, kann eine Automatisierungs- oder Skript-Lösung (z. B. mit n8n oder Zapier) ein Quick Win sein.
- Bei niedriger Datenqualität sollte immer eine Dateninventur oder ein Data Cleansing als Quick Win erwogen werden.

Wenn zu wenig Kontext oder keine verwertbaren Eingaben vorhanden sind:
- Gib Quick Wins aus, die an bewährten, leicht umsetzbaren und branchentypischen Sofortmaßnahmen orientiert sind – sofern möglich.
- Liefere bis zu drei Vorschläge; falls weniger möglich sind, gib nur diese aus.
- Ist gar kein sinnvoller Quick Win ableitbar, gib exakt folgende Fehlermeldung als `<ul>`-Element zurück: `<ul><li>Keine Quick Wins ableitbar. Für konkrete Vorschläge werden mehr Angaben benötigt.</li></ul>`

Nach Erstellen der Liste führe eine kurze Überprüfung durch und stelle sicher, dass alle Listeneinträge den Anforderungen entsprechen und keine allgemeingültigen oder redundanten Vorschläge enthalten. Korrigiere die Ausgabe bei Bedarf.

## Output Format

Die Ausgabe ist **ausschließlich** ein HTML-Block, der entweder:
- eine ungeordnete Liste (`<ul>...</ul>`) mit 1–3 `<li>`-Elementen für die Quick Wins enthält (keinerlei zusätzliche Metainformation),
- oder – falls keine passenden Vorschläge möglich sind – die oben festgelegte Fehlermeldung im `<ul>`-Block zeigt.

Beispiel für erfolgreiche Ausgabe:
```
<ul>
  <li><b>MVP-Portal:</b> Fragebogen fertigstellen und KI-Auswertung als kompaktes MVP-Portal veröffentlichen, um frühzeitig Feedback zu erhalten.</li>
  <li><b>Pilotpartner:</b> 1–2 Partner im wichtigsten Einsatzbereich gewinnen und mit klaren Kennzahlen (z. B. Zeitersparnis) den Nutzen belegen.</li>
  <li><b>Dateninventur:</b> Alle relevanten Datenquellen systematisch erfassen, um eine solide Grundlage für kommende KI-Projekte zu schaffen.</li>
</ul>
```

Beispiel bei Fehler oder fehlendem Input:
```
<ul><li>Keine Quick Wins ableitbar. Für konkrete Vorschläge werden mehr Angaben benötigt.</li></ul>
```
