You write a concise **Executive Summary** for an AI Status Report.
**Output:** HTML **fragment only** (no `<html>/<head>/<body>`). Allowed tags: `<p>`, `<ul>`, `<li>`, `<strong>`, `<em>`.

Context:
- Briefing: {{BRIEFING_JSON}}
- Scoring: {{SCORING_JSON}}
- Business Case: {{BUSINESS_JSON}}

Deliver two highlights:
1) Readiness score (number + badge) and the **two biggest levers** (KPI deltas vs benchmark).
2) Payback statement (months from the business case, conservative).

Format:
<p><strong>Keyline 1:</strong> …</p>
<p><strong>Keyline 2:</strong> …</p>
