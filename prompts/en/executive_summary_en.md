<!-- PURPOSE: Concise, actionable Executive Summary for Consulting & Professional Services (Solo, EN). -->
<!-- INPUT CONTEXT: Industry/size/region/main service/goals/use-cases/segments come from system prefix & backend. -->
<!-- OUTPUT GUARDS: Return ONLY semantic HTML: <p>, <ul>, <ol>, <li>, <strong>, <em>, <a>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <h3>, <h4>, <br>. -->
<!-- FORBIDDEN: NO code fences (```), NO <!DOCTYPE>, NO <html>/<head>/<body>/<meta>/<style>. -->
<!-- DOMAIN PINS: Do NOT use examples from Manufacturing/Automotive/Healthcare/Finance/Construction/Industrial. Stay within Consulting & Professional Services (Solo). -->
<!-- DATES: Do NOT print dates (renderer adds "As of:" stamp). -->
<!-- ROI BASELINE: Payback ~4 months (provided by backend). Do not contradict or invent totals. -->

<h3>Key Takeaways</h3>
<ul>
  <li><strong>Strategic position:</strong> Focus on {{ hauptleistung }} within Consulting &amp; Professional Services (Solo, {{ bundesland_code }}).</li>
  <li><strong>Main lever:</strong> Prioritized use case: {{ (ki_usecases|first) if ki_usecases else "process automation" }}; data base: {{ datenquellen|join(", ") if datenquellen else "client/project data" }}.</li>
  <li><strong>Expected impact:</strong> Faster acquisition &amp; delivery, consistent outputs, better explainability.</li>
  <li><strong>Economics:</strong> Target payback ~4 months (baseline). Prioritize initiatives with <em>direct</em> revenue/time impact.</li>
  <li><strong>Risk &amp; maturity:</strong> GDPR/AI‑Act path exists; extend solo‑grade governance (roles, logging scope, deletion rules).</li>
</ul>

<h4>What to do next (0–14 days)</h4>
<ul>
  <li><strong>Hard discovery:</strong> Map 5–7 core processes, select 2 pilot flows (lead qualification, offer drafting, etc.).</li>
  <li><strong>Lean tooling:</strong> EU‑ready base (e.g., Nextcloud/Matomo/Jitsi/Odoo on‑prem possible); Non‑EU only with DPA/SCC &amp; pseudonymization.</li>
  <li><strong>Make it measurable:</strong> Define 3 KPIs (e.g., offer turnaround, acquisition conversion, consulting hours per project).</li>
</ul>
