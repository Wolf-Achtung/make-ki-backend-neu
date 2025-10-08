<!-- s. frühere Lieferung – unverändert produktiv -->
<section class="card executive-summary">
  <div class="lede">
    <p class="keyline"><strong>Kernaussage 1:</strong>
      Der KI‑Readiness‑Score beträgt <strong>{{SCORING_JSON.score | fallback: "SCORING_JSON.score_total"}}</strong>% (Badge:
      <strong>{{SCORING_JSON.badge}}</strong>); größte Hebel liegen bei
      <em>Automatisierung</em> und <em>Compliance</em> gemessen an der Δ‑Abweichung zu den Benchmarks.
    </p>
    <p class="keyline"><strong>Kernaussage 2:</strong>
      Mit 1–2 priorisierten Automatisierungen entlang der Hauptleistung ist ein <strong>Payback ≤ 4 Monate</strong> realistisch –
      bei klaren Verantwortlichkeiten und schlanker Governance.
    </p>
  </div>

  <h3>Strategische Einordnung</h3>
  <p>
    Für <strong>{{BRIEFING_JSON.branche_label}}</strong> (Größe: {{BRIEFING_JSON.unternehmensgroesse_label}}) zeigt das Profil
    deutliche Stärken in den Bereichen mit positiver Δ‑Abweichung. Besonders relevant für die
    <em>Hauptleistung</em> („{{BRIEFING_JSON.hauptleistung}}“): Nutzen entsteht durch schnelleres
    Erstellen, Prüfen und Ausliefern standardisierter Ergebnisse.
  </p>
  <ul class="pill-list">
    <li><span class="pill">Digitalisierung: {{SCORING_JSON.kpis.digitalisierung.value}}% (Δ {{SCORING_JSON.kpis.digitalisierung.delta | signed}} pp)</span></li>
    <li><span class="pill">Automatisierung: {{SCORING_JSON.kpis.automatisierung.value}}% (Δ {{SCORING_JSON.kpis.automatisierung.delta | signed}} pp)</span></li>
    <li><span class="pill">Compliance: {{SCORING_JSON.kpis.compliance.value}}% (Δ {{SCORING_JSON.kpis.compliance.delta | signed}} pp)</span></li>
    <li><span class="pill">Prozessreife: {{SCORING_JSON.kpis.prozessreife.value}}% (Δ {{SCORING_JSON.kpis.prozessreife.delta | signed}} pp)</span></li>
    <li><span class="pill">Innovation: {{SCORING_JSON.kpis.innovation.value}}% (Δ {{SCORING_JSON.kpis.innovation.delta | signed}} pp)</span></li>
  </ul>

  <h3>Prioritäten (0–14 Tage)</h3>
  <ol>
    <li><strong>Top‑Use‑Case schärfen</strong> ({{BRIEFING_JSON.pull_kpis.top_use_case | fallback: "—"}}): Scope, Datenquellen, Erfolgskriterien (3 KPIs).</li>
    <li><strong>Mini‑Pilot entlang der Hauptleistung</strong>: E2E‑Flow (Input → Auswertung → Ergebnis) inkl. Review‑Checklist.</li>
    <li><strong>Compliance‑Startpaket</strong>: DPIA‑Trigger, Rollen/RACI, Löschregeln, AVV/SCC‑Status; kurze No‑PII‑Guideline.</li>
  </ol>

  <h3>ROI & Payback</h3>
  <p>
    Orientierungsgröße: <strong>Payback‑Baseline ≈ 4 Monate</strong>. Der Business‑Case‑Block enthält die
    <em>konkreten Beträge</em> aus der aktuellen Annahme (Invest&nbsp;↔&nbsp;Zeiteffekt).
  </p>

  <h3>Compliance (DSGVO / EU AI Act)</h3>
  <ul>
    <li><strong>Datenschutzbeauftragter:</strong> {{BRIEFING_JSON.datenschutzbeauftragter | yesno:"vorhanden,prüfen","nicht angegeben,entscheiden"}} · <strong>DPIA/Folgenabschätzung:</strong> {{BRIEFING_JSON.folgenabschaetzung | yesno:"ja,Trigger definieren","nein,bei Bedarf anstoßen"}}</li>
    <li><strong>Löschung &amp; Retention:</strong> {{BRIEFING_JSON.loeschregeln | yesno:"Regeln vorhanden – regelmäßig prüfen","Regeln definieren"}} · <strong>Meldewege:</strong> {{BRIEFING_JSON.meldewege | fallback:"klären"}}</li>
    <li><strong>EU AI Act Einordnung:</strong> überwiegend <em>minimal/limitiert</em>; Transparenz, Monitoring und menschliche Aufsicht sicherstellen.</li>
  </ul>

  <h3>Pfad zum Go‑Live (12 Wochen)</h3>
  <p>W1–2: Discovery &amp; Setup · W3–4: 2 Piloten messen · W5–8: Skalieren &amp; absichern · W9–12: Go‑Live‑Gate &amp; Case‑Beleg.</p>
</section>
