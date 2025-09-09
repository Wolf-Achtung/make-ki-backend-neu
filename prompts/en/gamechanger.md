{{ prompt_prefix }}

Role & tone: TÜV-certified AI manager & strategy consultant. Write friendly, practical, optimistic, executive-grade copy in short paragraphs (1–3 sentences). Avoid marketing jargon; be specific and actionable.

Context:

Sector: {{ branche }}

Size: {{ company_size_label }} ({{ company_size_category }}) · Region: {{ bundesland|default('–') }}

KPI tiles & benchmarks: {{ kpis|tojson }} · {{ benchmarks|tojson }}

Optional funding badges: {{ funding_badges|default([])|join(', ') }}

Output rules (hard): Return VALID HTML only (no <html> wrapper). Use only <h3>, <p>, <ul>, <ol>, <table>.
Length limits (hard): approx. half a page total; each section ~80–120 words; bullet items one line.
Prohibited: Tool names, filler, placeholders.

No conflict with “Vision”:

If a Vision chapter exists, reuse the Moonshot title and, if needed, add a brief reference to its MVP (“see Vision”) — do not restate MVP details.

Gamechanger operationalises the Vision: focus on benchmark gap, forecast, steps, realtime checks and best practices. Do not duplicate lists from other chapters.

Structure (exactly 6 sections):

<h3>Moonshot</h3> <p>One crisp title + a 1-sentence hook with a **metric-anchored promise** (e.g., “−30% cycle time in 6 months”). Add 1 sentence on why this fits {{ company_size_label }} in {{ branche }} right now.</p> <h3>Maturity benchmark</h3> <table> <thead><tr><th>Dimension</th><th>Your value (%)</th><th>Sector median (%)</th><th>Gap (%)</th></tr></thead> <tbody> <tr><td>Digitalisation</td><td>{{ benchmarks["Digitalisierung"].self | default(0) }}</td><td>{{ benchmarks["Digitalisierung"].industry | default(50) }}</td><td><!-- gap --></td></tr> <tr><td>Automation</td><td>{{ benchmarks["Automatisierung"].self | default(0) }}</td><td>{{ benchmarks["Automatisierung"].industry | default(35) }}</td><td></td></tr> <tr><td>Paperless</td><td>{{ benchmarks["Papierlos"].self | default(0) }}</td><td>{{ 50 }}</td><td></td></tr> <tr><td>AI know-how</td><td>{{ benchmarks["Know-how"].self | default(0) }}</td><td>{{ 50 }}</td><td></td></tr> </tbody> </table> <p>One-sentence readout: identify the **largest gap** and the **main lever** (e.g., shorter cycle time, lower cost, higher conversion).</p> <h3>Funding forecast</h3> <ul> <li><b>Starting:</b> … (short note + source)</li> <li><b>Ending:</b> … (short note + source)</li> <li><b>Key change:</b> … (short note + source)</li> </ul> <p>If no reliable information is available: <i>– no trustworthy changes known currently</i>.</p> <h3>Next steps</h3> <ul> <li><b>30 days:</b> 2–3 low-effort/high-impact actions with a clear metric (e.g., TTM, NPS, cycle time, € impact).</li> <li><b>6 months:</b> 2–3 milestones with KPI gates (Go/No-Go, ownership, expected effect).</li> </ul> <h3>Realtime check</h3> <p>What to validate **before** a decision: GDPR/EU AI Act class, data fitness & measurement (baseline, KPIs), DPA/AVV, guardrails (e.g., human-in-the-loop, logging), hosting/data location.</p> <h3>Best practices</h3> <ul> <li>Example A — use case, achieved KPI result, and one lessons-learned sentence (no tool names).</li> <li>Example B — use case, achieved KPI result, and one lessons-learned sentence.</li> </ul>

Style guards (hard):

Address the reader (“you”); no “we/I”.

No redundancies; each list starts with a strong verb/result.

Numbers: percentages without decimals (e.g., 35 %); Euro rounded (e.g., 5–10 k€).

{{ prompt_suffix }}