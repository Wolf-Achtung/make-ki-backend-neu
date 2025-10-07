<!-- File: prompts/en/executive_summary_en.md -->
<!-- PURPOSE: Executive Summary (EN) -->
<!-- OUTPUT: HTML only, no code fences or markdown placeholders. -->

<!--
Instructions:
- Start with a two-line headline: Sentence 1 summarises current AI readiness and main lever. Sentence 2 names two key actions and mentions the expected payback period.
- Then write a comprehensive advisory executive summary with <h3>, <p>, <ul>.
- Use clear, motivating language without marketing buzzwords.
-->

<p><strong>Key Findings</strong><br>
1. In {{ briefing.branche_label }}, your current AI readiness stands at {{ scoring.score_total }} %, primarily driven by {{ briefing.hauptleistung }} and the focus on {{ briefing.pull_kpis.top_use_case or 'your key use case' }}.<br>
2. Top priorities: {{ briefing.pull_kpis.zeitbudget or 'setting a clear focus' }} and targeted automation; realistic ROI payback is around {{ kpi_roi_months }} months.
</p>

<h3>Strategic Assessment</h3>
<p>Your organisation in the <strong>{{ briefing.branche_label }}</strong> sector has achieved an AI readiness score of <strong>{{ scoring.score_total }} %</strong> (Badge: {{ scoring.score_badge }}). Your core service <strong>{{ briefing.hauptleistung }}</strong> and stated goals indicate that the main potential lies in {{ briefing.pull_kpis.top_use_case or 'your prioritised use cases' }}.</p>

<h3>Action Areas &amp; Priorities</h3>
<p>From the questionnaire, we derive the following priorities:</p>
<ul>
  <li><strong>Boost efficiency:</strong> Automate steps with high manual effort (e.g. documentation, scheduling). Prioritise AI tools with low integration effort.</li>
  <li><strong>Compliance &amp; governance:</strong> Strengthen data protection (GDPR/EU AI Act) by establishing clear responsibilities, documentation, and training; choose tools labelled “yes” in <em>gdpr_ai_act</em>.</li>
  <li><strong>Skills &amp; culture:</strong> Build employee AI capabilities through workshops and pilots; encourage an open innovation culture.</li>
</ul>

<h3>Expected Benefits &amp; Economics</h3>
<p>An investment of <strong>{{ roi_investment | round(2) }} €</strong> can generate annual savings of <strong>{{ roi_annual_saving | round(2) }} €</strong> with a payback period of <strong>{{ kpi_roi_months }} months</strong>. The three-year ROI potential is around <strong>{{ roi_three_year }} €</strong> depending on execution.</p>

<h3>Risks &amp; Maturity</h3>
<p>Key risks involve data quality, change management, and compliance. Develop a clear roadmap with deadlines and responsibilities. Our risk matrix (see “Risks” section) provides concrete mitigation actions.</p>

<p><em>Note:</em> This summary is based on your responses and current benchmarks. It serves as a guide, with further details in the following chapters (Quick Wins, Roadmap, Risks, Compliance, Tools, etc.).</p>
