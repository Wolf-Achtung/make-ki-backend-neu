<!-- Datei: prompts/de/executive_summary_de.md -->
<!-- PURPOSE: Executive Summary (DE) -->
<!-- OUTPUT: Nur HTML ohne Code-Fences oder Markdown-Placeholder. -->

<!--
Anleitung:
- Liefere zu Beginn einen prägnanten Zwei-Zeilen-Abschnitt: Satz 1 fasst den aktuellen KI-Reifegrad samt Haupthebel zusammen. Satz 2 nennt zwei wichtigste Handlungsfelder und das ROI-Zeitfenster.
- Danach folgt eine ausführliche, professionelle Executive Summary mit klarer Gliederung (<h3>, <p>, <ul>).
- Nutze einen motivierenden, sachlichen Stil ohne Marketing-Floskeln.
-->

<p><strong>Kernaussage</strong><br>
1. {{ briefing.branche_label }}: Ihr aktueller KI-Reifegrad liegt bei {{ scoring.score_total }} %, vor allem getrieben durch {{ briefing.hauptleistung }} und {{ briefing.pull_kpis.top_use_case or 'den identifizierten Use-Case' }}.<br>
2. Wichtigste Schritte: {{ briefing.pull_kpis.zeitbudget or 'Fokus setzen' }} und gezielte Automatisierung; ROI-Payback in rund {{ kpi_roi_months }} Monaten realistisch.
</p>

<h3>Strategische Einordnung</h3>
<p>Ihr Unternehmen aus der Branche <strong>{{ briefing.branche_label }}</strong> weist einen KI-Readiness-Score von <strong>{{ scoring.score_total }} %</strong> (Badge: {{ scoring.score_badge }}) auf. Die Hauptleistung <strong>{{ briefing.hauptleistung }}</strong> und die angestrebten Ziele zeigen, dass das Potenzial besonders in {{ briefing.pull_kpis.top_use_case or 'den priorisierten Use-Cases' }} liegt.</p>

<h3>Handlungsfelder &amp; Prioritäten</h3>
<p>Auf Basis Ihres Fragebogens ergeben sich folgende Schwerpunkte:</p>
<ul>
  <li><strong>Effizienzsteigerung:</strong> Automatisieren Sie Prozessschritte mit hohem manuellen Aufwand (z. B. Dokumentation, Terminplanung). Nutzen Sie dabei KI-Tools mit niedrigem Integrationsaufwand.</li>
  <li><strong>Compliance und Governance:</strong> Stärken Sie Datenschutz (DSGVO/EU AI Act) durch klare Verantwortlichkeiten, Dokumentation und Schulungen; nutzen Sie Tools, die „yes“ bei <em>gdpr_ai_act</em> bieten.</li>
  <li><strong>Know-how und Kultur:</strong> Fördern Sie Mitarbeiterkompetenz in KI durch Workshops und Pilotprojekte; schaffen Sie eine offene Innovationskultur.</li>
</ul>

<h3>Erwarteter Nutzen &amp; Wirtschaftlichkeit</h3>
<p>Die Investitionssumme von <strong>{{ roi_investment | round(2) }} €</strong> führt bei richtiger Priorisierung zu einer jährlichen Einsparung von rund <strong>{{ roi_annual_saving | round(2) }} €</strong> und einem Payback innerhalb von <strong>{{ kpi_roi_months }} Monaten</strong>. Das ROI-Potenzial über drei Jahre beträgt <strong>{{ roi_three_year }} €</strong> (je nach Umsetzung).</p>

<h3>Risiken &amp; Reife</h3>
<p>Risiken liegen vor allem in Datenqualität, Change-Management und der Einhaltung regulatorischer Vorgaben. Erarbeiten Sie eine klare Roadmap, um Deadlines und Verantwortlichkeiten festzulegen. Unsere Risikomatrix (siehe Abschnitt „Risiken“) liefert dazu konkrete Maßnahmen.</p>

<p><em>Hinweis:</em> Diese Zusammenfassung basiert auf Ihren Antworten und aktuellen Benchmarks. Sie dient als Leitfaden, der durch die nachfolgenden Kapitel (Quick Wins, Roadmap, Risiken, Compliance, Tools etc.) vertieft wird.</p>
