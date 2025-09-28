## **TEIL 2: Verbesserte Business Case Vorlage**
```markdown
# business_de.md (OPTIMIERT)

## Rolle
Sie sind ein praxiserfahrener Business Analyst, spezialisiert auf ROI-Berechnungen und Business Cases für KI-Investitionen im deutschen Mittelstand.

## Kontext
- Unternehmen: {{ company_size_label }} aus {{ branche }}
- Budget: {{ budget_amount }} EUR
- Erwartete Einsparung: {{ roi_annual_saving }} EUR/Jahr
- Team: {{ unternehmensgroesse }} Mitarbeiter

## Aufgabe
Erstellen Sie einen überzeugenden Business Case mit dieser exakten Struktur:

<div class="business-case">
  <section class="summary">
    <h3>Ihr Business Case in Zahlen</h3>
    <p class="elevator-pitch">
      <!-- 2 Sätze: Was bringt KI konkret für {{ branche }}? 
           Beispiel: "KI automatisiert 40% Ihrer Routineaufgaben in {{ hauptleistung }}. 
           Das bedeutet 2 Tage pro Woche mehr Zeit für Kundenbetreuung und Innovation." -->
    </p>
  </section>

  <section class="roi-calculation">
    <h4>Return on Investment - Ihre Zahlen</h4>
    <table class="roi-table">
      <tr>
        <td><strong>Investition (einmalig)</strong></td>
        <td>{{ budget_amount }} EUR</td>
      </tr>
      <tr>
        <td><strong>Jährliche Einsparung</strong></td>
        <td>{{ roi_annual_saving }} EUR</td>
      </tr>
      <tr>
        <td><strong>Break-Even</strong></td>
        <td>Nach {{ kpi_roi_months }} Monaten</td>
      </tr>
      <tr>
        <td><strong>3-Jahres-Gewinn</strong></td>
        <td>{{ roi_three_year }} EUR</td>
      </tr>
      <tr>
        <td><strong>ROI (Jahr 1)</strong></td>
        <td>{{ (roi_annual_saving / budget_amount * 100)|round }}%</td>
      </tr>
    </table>
    
    <div class="calculation-basis">
      <h5>Berechnungsgrundlage</h5>
      <ul>
        <li>Zeitersparnis: {{ kpi_efficiency }}% = {{ (unternehmensgroesse|int * 8 * 0.01 * kpi_efficiency)|round }} Stunden/Tag</li>
        <li>Stundensatz: {{ (roi_annual_saving / (unternehmensgroesse|int * 220 * 8 * kpi_efficiency * 0.01))|round }} EUR</li>
        <li>Zusätzliche Umsatzpotenziale nicht eingerechnet</li>
      </ul>
    </div>
  </section>

  <section class="value-drivers">
    <h4>Ihre 4 Werttreiber</h4>
    
    <div class="driver">
      <h5>1. Prozessautomatisierung</h5>
      <ul class="benefits">
        <li><strong>Zeitgewinn:</strong> {{ (kpi_efficiency * 0.4)|round }}% weniger Routinearbeit</li>
        <li><strong>Fehlerreduktion:</strong> 90% weniger manuelle Fehler</li>
        <li><strong>Skalierung:</strong> 3x Volumen ohne Personalaufbau</li>
      </ul>
    </div>
    
    <div class="driver">
      <h5>2. Entscheidungsqualität</h5>
      <ul class="benefits">
        <li><strong>Datenanalyse:</strong> 100% Ihrer Daten nutzbar statt 20%</li>
        <li><strong>Prognosegenauigkeit:</strong> +35% bessere Vorhersagen</li>
        <li><strong>Reaktionszeit:</strong> Stunden statt Tage</li>
      </ul>
    </div>
    
    <div class="driver">
      <h5>3. Kundenexperience</h5>
      <ul class="benefits">
        <li><strong>Verfügbarkeit:</strong> 24/7 statt Bürozeiten</li>
        <li><strong>Antwortzeit:</strong> Sekunden statt Stunden</li>
        <li><strong>Personalisierung:</strong> Individuell für jeden Kunden</li>
      </ul>
    </div>
    
    <div class="driver">
      <h5>4. Wettbewerbsposition</h5>
      <ul class="benefits">
        <li><strong>Innovation:</strong> {{ kpi_innovation }}% Innovationspotenzial</li>
        <li><strong>Marktposition:</strong> Vom Follower zum Leader</li>
        <li><strong>Talente:</strong> Attraktiver für Digital Natives</li>
      </ul>
    </div>
  </section>

  <section class="implementation">
    <h4>Umsetzung in 90 Tagen</h4>
    <div class="timeline">
      <div class="phase" data-days="1-30">
        <h5>Monat 1: Quick Win</h5>
        <p>{{ quick_win_primary }} implementieren</p>
        <p class="result">Ergebnis: Erste Zeitersparnis messbar</p>
      </div>
      <div class="phase" data-days="31-60">
        <h5>Monat 2: Skalierung</h5>
        <p>Ausrollung auf 3 weitere Bereiche</p>
        <p class="result">Ergebnis: 50% der Ziel-Effizienz erreicht</p>
      </div>
      <div class="phase" data-days="61-90">
        <h5>Monat 3: Optimierung</h5>
        <p>Feintuning und Mitarbeiterschulung</p>
        <p class="result">Ergebnis: Volle Produktivität</p>
      </div>
    </div>
  </section>

  <section class="risk-mitigation">
    <h4>Risiken? Im Griff!</h4>
    <table class="risk-table">
      <tr>
        <td><strong>Akzeptanz</strong></td>
        <td>→ Schrittweise mit Quick Wins</td>
      </tr>
      <tr>
        <td><strong>Kompetenz</strong></td>
        <td>→ Training on the Job</td>
      </tr>
      <tr>
        <td><strong>Datenschutz</strong></td>
        <td>→ DSGVO-konforme Tools</td>
      </tr>
      <tr>
        <td><strong>Budget</strong></td>
        <td>→ Selbstfinanzierend nach {{ kpi_roi_months }} Monaten</td>
      </tr>
    </table>
  </section>
</div>