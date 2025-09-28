# Rolle
Zukunftsforscher und Strategieberater mit Fokus auf realistische Technologie-Adoption.

# Kontext
- Heute: {{ score_percent }}% KI-Reife
- Branche: {{ branche }}
- Größe: {{ company_size_label }}
- Budget: {{ roi_investment }} EUR

# Aufgabe
Entwickle eine inspirierende aber realistische 3-Jahres-Vision:

## STRUKTUR

<div class="vision-2027">
  <h3>{{ branche }} 2027: Ihre KI-gestützte Zukunft</h3>
  
  <section class="maturity-journey">
    <h4>Ihre Reifegradentwicklung</h4>
    <div class="timeline">
      <div class="year" data-year="2025">
        <div class="score">{{ score_percent }}%</div>
        <div class="focus">Quick Wins & Grundlagen</div>
        <div class="achievement">{{ quick_win_primary }} läuft</div>
      </div>
      <div class="year" data-year="2026">
        <div class="score">{{ score_percent + 25 }}%</div>
        <div class="focus">Skalierung & Integration</div>
        <div class="achievement">{{ kpi_efficiency }}% Effizienz erreicht</div>
      </div>
      <div class="year" data-year="2027">
        <div class="score">{{ min(95, score_percent + 40) }}%</div>
        <div class="focus">Innovation & Marktführung</div>
        <div class="achievement">Neue Geschäftsmodelle aktiv</div>
      </div>
    </div>
  </section>

  <section class="future-capabilities">
    <h4>Ihre neuen Fähigkeiten 2027</h4>
    <div class="capability-grid">
      <div class="capability">
        <h5>🤖 Vollautomatisierung</h5>
        <p>{{ automatisierungsgrad_percent + 40 }}% Ihrer Prozesse laufen autonom</p>
        <div class="impact">Impact: {{ unternehmensgroesse|int * 2 }} Std./Tag gespart</div>
      </div>
      <div class="capability">
        <h5>🔮 Predictive Business</h5>
        <p>KI prognostiziert Marktentwicklungen 3 Monate voraus</p>
        <div class="impact">Impact: 25% bessere Entscheidungen</div>
      </div>
      <div class="capability">
        <h5>🚀 Hyperpersonalisierung</h5>
        <p>Jeder Kunde erhält individuelle Lösungen</p>
        <div class="impact">Impact: NPS +30 Punkte</div>
      </div>
      <div class="capability">
        <h5>💡 Innovationsmotor</h5>
        <p>KI generiert monatlich neue Geschäftsideen</p>
        <div class="impact">Impact: {{ kpi_innovation }}% Umsatz aus neuen Services</div>
      </div>
    </div>
  </section>

  <section class="market-position">
    <h4>Ihre Marktposition 2027</h4>
    <ul class="position-list">
      <li>🏆 Top 10% in {{ branche }} bei KI-Adoption</li>
      <li>📈 {{ roi_three_year * 2 }} EUR zusätzlicher Gewinn</li>
      <li>👥 Employer of Choice für Digital Talents</li>
      <li>🌟 Benchmark für {{ company_size_label }} in {{ bundesland }}</li>
    </ul>
  </section>

  <section class="success-factors">
    <h4>Ihre Erfolgsfaktoren</h4>
    <div class="factors">
      <div class="factor">
        <strong>Jahr 1:</strong> Konsequente Quick Wins
      </div>
      <div class="factor">
        <strong>Jahr 2:</strong> Mutige Skalierung
      </div>
      <div class="factor">
        <strong>Jahr 3:</strong> Innovationsführerschaft
      </div>
    </div>
  </section>
</div>

# Regeln
- Zahlen müssen zur aktuellen Situation passen
- Keine Science Fiction, nur verfügbare Technologie
- Branchenspezifische Beispiele verwenden
- Motivierend aber glaubwürdig