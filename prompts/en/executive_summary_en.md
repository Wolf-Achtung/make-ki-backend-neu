<!-- EXECUTIVE SUMMARY (EN)
Context (DO NOT render, for reasoning only):
BRIEFING_JSON = {{BRIEFING_JSON}}
SCORING_JSON  = {{SCORING_JSON}}
BENCHMARKS_JSON = {{BENCHMARKS_JSON}}
TOOLS_JSON = {{TOOLS_JSON}}
FUNDING_JSON = {{FUNDING_JSON}}

Goal:
Produce an advisory HTML “Executive Summary” section for decision makers.
Return CLEAN HTML ONLY (no Markdown, no code fences, no <html>/<body>).

Rules:
- Use ONLY numbers/labels from the JSON above. No invented values.
- Rounding: integers for %, deltas as “+/-X pp”.
- Tone: clear, professional, motivational; avoid hype.
- Company/industry from BRIEFING_JSON; KPIs/deltas from SCORING_JSON.kpis.
- ROI: mention baseline payback (≈ 4 months) and REFER to the Business Case section for amounts.
- Compliance: concise DSGVO/EU AI Act notes tailored to briefing signals (DPO, DPIA, deletion rules, incident paths, governance).
- Length: ~250–380 words.
- Output structure EXACTLY as below.

OUTPUT (HTML only): -->
<section class="card executive-summary">

  <!-- 1) Two keylines (EXACTLY TWO) -->
  <div class="lede">
    <p class="keyline"><strong>Keyline 1:</strong>
      KI‑readiness score is <strong>{{SCORING_JSON.score | fallback: "SCORING_JSON.score_total"}}</strong>% (badge:
      <strong>{{SCORING_JSON.badge}}</strong>); main levers are <em>Automation</em> and <em>Compliance</em> by Δ vs. benchmarks.
    </p>
    <p class="keyline"><strong>Keyline 2:</strong>
      With 1–2 prioritized automations along the core service, a <strong>payback ≤ 4 months</strong> is realistic
      if roles, review and governance are defined upfront.
    </p>
  </div>

  <!-- 2) Strategic context -->
  <h3>Strategic Context</h3>
  <p>
    For <strong>{{BRIEFING_JSON.branche_label}}</strong> (size: {{BRIEFING_JSON.unternehmensgroesse_label}}), the profile shows
    strengths where Δ is positive. For the <em>core service</em> (“{{BRIEFING_JSON.hauptleistung}}”),
    value comes from faster creation, QA and delivery of standardized outputs.
  </p>
  <ul class="pill-list">
    <li><span class="pill">Digitalization: {{SCORING_JSON.kpis.digitalisierung.value}}% (Δ {{SCORING_JSON.kpis.digitalisierung.delta | signed}} pp)</span></li>
    <li><span class="pill">Automation: {{SCORING_JSON.kpis.automatisierung.value}}% (Δ {{SCORING_JSON.kpis.automatisierung.delta | signed}} pp)</span></li>
    <li><span class="pill">Compliance: {{SCORING_JSON.kpis.compliance.value}}% (Δ {{SCORING_JSON.kpis.compliance.delta | signed}} pp)</span></li>
    <li><span class="pill">Process Maturity: {{SCORING_JSON.kpis.prozessreife.value}}% (Δ {{SCORING_JSON.kpis.prozessreife.delta | signed}} pp)</span></li>
    <li><span class="pill">Innovation: {{SCORING_JSON.kpis.innovation.value}}% (Δ {{SCORING_JSON.kpis.innovation.delta | signed}} pp)</span></li>
  </ul>

  <!-- 3) Priorities 0–14 days -->
  <h3>Priorities (0–14 days)</h3>
  <ol>
    <li><strong>Sharpen the top use case</strong> ({{BRIEFING_JSON.pull_kpis.top_use_case | fallback: "—"}}): scope, data sources, success KPIs.</li>
    <li><strong>Mini pilot along the core service</strong>: a slim E2E flow (input → analysis → output) incl. review checklist.</li>
    <li><strong>Compliance starter pack</strong>: DPIA triggers, roles/RACI, deletion rules, AVV/SCC status; short No‑PII guideline.</li>
  </ol>

  <!-- 4) ROI & Payback -->
  <h3>ROI & Payback</h3>
  <p>
    Orientation: <strong>baseline payback ≈ 4 months</strong>. The Business Case section in the report contains
    the <em>exact amounts and ratios</em> for the current assumption set (investment ↔ time savings).
  </p>

  <!-- 5) Compliance (GDPR / EU AI Act) -->
  <h3>Compliance (GDPR / EU AI Act)</h3>
  <ul>
    <li><strong>DPO:</strong> {{BRIEFING_JSON.datenschutzbeauftragter | yesno:"present,review","not specified,decide"}} ·
        <strong>DPIA:</strong> {{BRIEFING_JSON.folgenabschaetzung | yesno:"yes,define triggers","no,trigger when needed"}}</li>
    <li><strong>Deletion/Retention:</strong> {{BRIEFING_JSON.loeschregeln | yesno:"rules exist – review regularly","define rules"}} ·
        <strong>Incident paths:</strong> {{BRIEFING_JSON.meldewege | fallback:"clarify"}}</li>
    <li><strong>EU AI Act classification:</strong> mainly <em>minimal/limited</em> (assistive/generative); ensure transparency,
        monitoring and human in the loop.</li>
  </ul>

  <!-- 6) 12‑week path -->
  <h3>Path to Go‑Live (12 weeks)</h3>
  <p>
    Weeks 1–2: discovery & setup · Weeks 3–4: 2 pilots with measurement · Weeks 5–8: scale & harden (policies, versioning) ·
    Weeks 9–12: go‑live gate & case evidence.
  </p>
</section>
