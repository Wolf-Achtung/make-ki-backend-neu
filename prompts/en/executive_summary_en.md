<section class="card executive-summary">
  <div class="lede">
    <p class="keyline"><strong>Keyline 1:</strong>
      KI‑readiness is <strong>{{SCORING_JSON.score | fallback: "SCORING_JSON.score_total"}}</strong>% (badge
      <strong>{{SCORING_JSON.badge}}</strong>); main levers: <em>Automation</em> &amp; <em>Compliance</em> by Δ vs. benchmarks.
    </p>
    <p class="keyline"><strong>Keyline 2:</strong>
      With 1–2 prioritized automations along the core service, a <strong>payback ≤ 4 months</strong> is realistic.
    </p>
  </div>
  <h3>Strategic Context</h3>
  <p>Industry <strong>{{BRIEFING_JSON.branche_label}}</strong>, size {{BRIEFING_JSON.unternehmensgroesse_label}} – value via faster creation, QA and delivery of standardized outputs.</p>
  <ul class="pill-list">
    <li><span class="pill">Digitalization: {{SCORING_JSON.kpis.digitalisierung.value}}% (Δ {{SCORING_JSON.kpis.digitalisierung.delta | signed}} pp)</span></li>
    <li><span class="pill">Automation: {{SCORING_JSON.kpis.automatisierung.value}}% (Δ {{SCORING_JSON.kpis.automatisierung.delta | signed}} pp)</span></li>
    <li><span class="pill">Compliance: {{SCORING_JSON.kpis.compliance.value}}% (Δ {{SCORING_JSON.kpis.compliance.delta | signed}} pp)</span></li>
    <li><span class="pill">Process Maturity: {{SCORING_JSON.kpis.prozessreife.value}}% (Δ {{SCORING_JSON.kpis.prozessreife.delta | signed}} pp)</span></li>
    <li><span class="pill">Innovation: {{SCORING_JSON.kpis.innovation.value}}% (Δ {{SCORING_JSON.kpis.innovation.delta | signed}} pp)</span></li>
  </ul>
  <h3>Priorities (0–14 days)</h3>
  <ol>
    <li><strong>Sharpen top use case</strong> – scope, data sources, 3 success KPIs.</li>
    <li><strong>Mini pilot</strong> end‑to‑end (input → analysis → output) incl. review checklist.</li>
    <li><strong>Compliance starter pack</strong> – DPIA triggers, roles/RACI, deletion rules, DPA/SCC; short No‑PII guideline.</li>
  </ol>
  <h3>ROI &amp; Payback</h3>
  <p>Baseline payback ≈ 4 months. Exact amounts in the Business Case section.</p>
  <h3>Compliance (GDPR / EU AI Act)</h3>
  <ul>
    <li><strong>DPO:</strong> {{BRIEFING_JSON.datenschutzbeauftragter | yesno:"present,review","not specified,decide"}} · <strong>DPIA:</strong> {{BRIEFING_JSON.folgenabschaetzung | yesno:"yes,define triggers","no,trigger when needed"}}</li>
    <li><strong>Deletion/Retention:</strong> {{BRIEFING_JSON.loeschregeln | yesno:"rules exist – review regularly","define rules"}} · <strong>Incident paths:</strong> {{BRIEFING_JSON.meldewege | fallback:"clarify"}}</li>
    <li><strong>EU AI Act:</strong> mostly minimal/limited; ensure transparency, monitoring, human oversight.</li>
  </ul>
  <h3>Path to Go‑Live (12 weeks)</h3>
  <p>W1‑2 discovery · W3‑4 2 pilots · W5‑8 scale & harden · W9‑12 go‑live gate & evidence.</p>
</section>
