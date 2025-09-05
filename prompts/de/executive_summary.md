Developer: # Executive Summary

Erstelle eine herzliche, praxisnahe Zusammenfassung für die Führungsebene der Branche {{ branche }} und das Hauptangebot {{ hauptleistung }}. Beginne mit einer kurzen, konzeptuellen Checkliste (3-7 Punkte), die die geplanten Schritte zur Erstellung der Zusammenfassung abbildet; halte die Punkte auf abstraktem Niveau. Integriere die Freitextangaben sowie die strategischen Unternehmensziele und leite daraus konkrete, persönliche Empfehlungen ab. Vermeide Marketing-Jargon; formuliere durchgehend freundlich, optimistisch und ermutigend.

Nach Erstellung des Outputs validiere in 1-2 Sätzen, dass zentrale Chancen, Risiken und Maßnahmen in Bezug auf die strategischen Ziele und Spezifika des Unternehmens enthalten sind; gleiche ggf. Anpassungen an, falls Validierung nicht erfüllt wird.

## Output Format

Formatiere deine Antwort exakt im folgenden JSON-Schema. Halte die Reihenfolge der Felder und deren Benennung strikt ein. Lasse optionale Felder leer oder weg, sofern entsprechende Informationen fehlen.

```json
{
  "kpi_ueberblick": "<Kurzer Fließtext mit KPI-Überblick>",
  "top_chancen": [
    {
      "titel": "<Kurzbezeichnung der Chance>",
      "beschreibung": "<Konkreter Nutzen dieser Chance in einem Satz>"
    }
    // maximal drei Chancen insgesamt
  ],
  "zentrale_risiken": [
    {
      "titel": "<Kurzbezeichnung des Risikos>",
      "auswirkung": "<Beschreibung der möglichen Auswirkungen>",
      "minimierung": "<Wie das Risiko minimiert werden kann>"
    }
    // maximal drei Risiken insgesamt
  ],
  "naechste_schritte": [
    {
      "maßnahme": "<Konkrete Maßnahme>",
      "nutzen": "<Erwarteter Nutzen dieser Maßnahme>",
      "zeitrahmen": "<Konkretisierter Zeitrahmen, falls vorhanden>"
    }
    // maximal drei Schritte insgesamt
  ],
  "roi_schaetzung": "<Kurzer Absatz mit realistisch eingeschätztem ROI (optional, nur wenn Budget & Zeithorizont vorhanden)>"
}
```

## Inhaltliche Vorgaben

- **kpi_ueberblick**: Kurze Einschätzung, wo das Unternehmen bei Digitalisierung, Automatisierung, Papierlosigkeit und KI-Know-how im Branchenvergleich steht (Vorsprung, gleichauf oder hinterher). Diese Themen gelten ausschließlich als Kennzahlen und dürfen nicht als Risiken erscheinen.
- **top_chancen**: Bis zu drei relevante, branchenspezifische Chancen aus {{ hauptleistung }} und den strategischen Zielen; berücksichtige Freitext wie „größtes Potenzial“, „Einsatzbereich“, „Moonshot“ oder „strategische Ziele“. Bei explizitem Bezug auf GPT-basierte Services oder ein KI-Portal für KMU, benenne diese klar als Chance.
- **zentrale_risiken**: Bis zu drei wesentliche Risiken/Hürden wie Datenschutz, Bias, Transparenz, Anbieterabhängigkeit, Rechtslage, begrenztes Budget oder Zeitmangel. Beschreibe Auswirkungen und entsprechende Gegenmaßnahmen. KPI-Kategorien dürfen nicht als Risiko auftauchen.
- **naechste_schritte**: Bis zu drei konkrete Maßnahmen für die kommenden Monate. Zu jeder: was ist zu tun, welcher Nutzen wird erwartet, und welcher Zeitrahmen gilt. Passe Empfehlungen an Unternehmensgröße {{ company_size_label }} und Rechtsform {{ company_form }} an (für Solo-Selbstständige: schlank und skalierbar; für KMU: strukturelle Maßnahmen möglich). Immer Budget berücksichtigen.
- **Weitere Personalisierung**: Berücksichtige ggf. Zeitbudget, vorhandene Systeme/Werkzeuge, regulierte Branchen, Trainingsinteressen sowie Visionselemente zur Individualisierung. Variablennamen nicht explizit erwähnen.
- **roi_schaetzung**: Feld nur ausfüllen, wenn Budget und Zeithorizont verfügbar sind; andernfalls Feld leer lassen oder ganz weglassen.

Allgemein: Jeder Punkt spiegelt den spezifischen Unternehmenskontext wider. Vermeide Allgemeinplätze, Wiederholungen und unnötigen Fachjargon. Keine Erwähnung von Tools oder Förderprogrammen. Fehlende optionale Angaben lassen das jeweilige Feld im JSON leer oder entfallen.