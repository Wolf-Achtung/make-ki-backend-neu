<!-- PURPOSE: Concise, actionable Executive Summary for Consulting & Professional Services (Solo, EN). -->
<!-- INPUT CONTEXT: Industry/size/region/main service/goals/use-cases/segments come from system prefix & backend. -->
<!-- OUTPUT GUARDS: Return ONLY semantic HTML: <p>, <ul>, <ol>, <li>, <strong>, <em>, <a>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <h3>, <h4>, <br>. -->
<!-- FORBIDDEN: NO code fences (```), NO <!DOCTYPE>, NO <html>/<head>/<body>/<meta>/<style>. -->
<!-- DOMAIN PINS: Do NOT use examples from Manufacturing/Automotive/Healthcare/Finance/Construction/Industrial. Stay within Consulting & Professional Services (Solo). -->
<!-- DATES: Do NOT print dates (renderer adds "As of:" stamp). -->
<!-- ROI BASELINE: Payback ~4 months (provided by backend). Do not contradict or invent totals. -->

<h3>Summary</h3>
<ul>
  <li><strong>Strategic focus:</strong> The core is {{ hauptleistung }} within Consulting &amp; Professional Services (Solo, {{ bundesland_code }}). Your positioning is clear and differentiated.</li>
  <li><strong>Main lever:</strong> Key use case: {{ (ki_usecases|first) if ki_usecases else "process automation" }}. Data source: {{ datenquellen|join(", ") if datenquellen else "client and project data" }}.</li>
  <li><strong>Expected benefits:</strong> Significant efficiency gains in acquisition, offer drafting and delivery with transparent, consistent outputs.</li>
  <li><strong>Economics:</strong> Target payback is around 4 months. Prioritise initiatives that deliver immediate revenue or time savings.</li>
  <li><strong>Risk &amp; maturity:</strong> GDPR and AI‑Act compliance is essentially in place. Expand a solo‑grade governance (roles, logging scope, deletion rules).</li>
</ul>

<h4>Next 14 days</h4>
<ul>
  <li><strong>Process mapping:</strong> Identify 5–7 core processes and select 2 pilot flows (e.g. lead qualification, offer drafting).</li>
  <li><strong>Tool stack:</strong> Evaluate an EU‑compliant toolset (e.g. Nextcloud, Matomo, Jitsi, Odoo on‑prem). Use non‑EU providers only with DPA/SCC and pseudonymisation.</li>
  <li><strong>Measurement:</strong> Define 3 KPIs (e.g. offer turnaround, conversion rate, consulting hours per project) and start tracking immediately.</li>
</ul>