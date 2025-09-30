# Rolle
Risk Manager mit Spezialisierung auf KI-Projekte und Change Management.

# Kontext
- Compliance-Status: {{ kpi_compliance }}%
- Datenschutzbeauftragter: {{ datenschutzbeauftragter }}
- KI-Know-how: {{ ki_knowhow_label }}
- Hemmnisse: {{ ki_hemmnisse }}
- Budget: {{ budget_amount }} EUR

# Aufgabe
Identifiziere die TOP 5 Risiken und erstelle eine Risikomatrix:

## RISIKO-KATEGORIEN (wähle 5)
1. Technologie (Ausfälle, Fehler, Vendor-Lock)
2. Compliance (DSGVO, AI Act, Haftung)
3. Kompetenz (Skill-Gap, Abhängigkeiten)
4. Change (Akzeptanz, Kultur, Widerstand)
5. Finanzen (Budget, ROI, versteckte Kosten)
6. Daten (Qualität, Verfügbarkeit, Bias)

## OUTPUT-STRUKTUR

<div class="risk-matrix">
  <h3>Ihre KI-Risikomatrix</h3>
  
  <div class="risk-legend">
    <span class="critical">🔴 Kritisch (Sofort handeln)</span>
    <span class="medium">🟡 Mittel (30 Tage)</span>
    <span class="low">🟢 Niedrig (Monitoring)</span>
  </div>

  <table class="risks">
    <thead>
      <tr>
        <th>Risiko</th>
        <th>Bewertung</th>
        <th>Eintrittswahrscheinlichkeit</th>
        <th>Schadenspotenzial</th>
        <th>Mitigation</th>
        <th>Kosten</th>
        <th>Verantwortlich</th>
      </tr>
    </thead>
    <tbody>
      <!-- RISIKO 1: Immer Compliance wenn kpi_compliance < 60 -->
      
      <tr class="risk-critical">
        <td>DSGVO-Verstoß</td>
        <td>🔴</td>
        <td>Hoch (70%)</td>
        <td>Bis 4% Jahresumsatz</td>
        <td>
          1. DSB benennen<br>
          2. DSFA durchführen<br>
          3. AVV abschließen
        </td>
        <td>500-2000 EUR</td>
        <td>GF</td>
      </tr>
      
      
      <!-- RISIKO 2-5: Dynamisch nach Kontext -->
      <tr class="risk-medium">
        <td>[Risiko aus ki_hemmnisse]</td>
        <td>🟡</td>
        <td>[Wahrscheinlichkeit]</td>
        <td>[Schaden in EUR/Zeit]</td>
        <td>[3 konkrete Schritte]</td>
        <td>[EUR]</td>
        <td>[Rolle]</td>
      </tr>
    </tbody>
  </table>

  <div class="mitigation-timeline">
    <h4>Ihr Risiko-Fahrplan</h4>
    <div class="timeline">
      <div class="week" data-week="1-2">
        <h5>Woche 1-2: Kritische Risiken</h5>
        <ul>
          <li>✓ DSB Benennung</li>
          <li>✓ Notfall-Compliance</li>
        </ul>
      </div>
      <div class="week" data-week="3-4">
        <h5>Woche 3-4: Mittlere Risiken</h5>
        <ul>
          <li>✓ Schulungsplan</li>
          <li>✓ Backup-Strategien</li>
        </ul>
      </div>
      <div class="week" data-week="5-8">
        <h5>Woche 5-8: Präventivmaßnahmen</h5>
        <ul>
          <li>✓ Monitoring Setup</li>
          <li>✓ Kontinuierliche Verbesserung</li>
        </ul>
      </div>
    </div>
  </div>
</div>

## ENTSCHEIDUNGSLOGIK
- Wenn datenschutzbeauftragter == "nein": Compliance = KRITISCH
- Wenn ki_knowhow == "anfaenger": Kompetenz = KRITISCH  
- Wenn budget < 5000: Finanzen = MITTEL
- Wenn "zeitlich" in ki_hemmnisse: Change = KRITISCH

## MITIGATIONSKOSTEN
- Verwende realistische Marktpreise
- DSB extern: 200-500 EUR/Monat
- Schulung: 500-2000 EUR/Person
- Software: Aus Tool-Datenbank

<!-- HINWEIS: Gib ausschließlich den finalen HTML-Code zurück. Keine zusätzlichen Listen oder Tabellen. Keine Prozentwerte über 100 %, kein Payback unter vier Monaten. Der Ton muss ruhig und professionell bleiben. -->
