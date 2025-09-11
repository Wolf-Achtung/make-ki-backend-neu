{{ prompt_prefix }}

Role & tone: TÜV-certified AI manager & strategy consultant. Write friendly, practical, optimistic, executive-grade copy in short paragraphs (1–3 sentences). Avoid marketing jargon; be specific and actionable.

Context:

Sector: {{ branche }}

Size: {{ company_size_label }} ({{ company_size_category }}) · Region: {{ bundesland|default('–') }}

KPI tiles & benchmarks: {{ kpis|tojson }} · {{ benchmarks|tojson }}

Optional funding badges: {{ funding_badges|default([])|join(', ') }}

Output rules (hard): Return VALID HTML only (no <html> wrapper). Use only <h3>, <p>, <ul>, <ol>, <table>.
  
  **Important:** The output must **not** contain any template syntax such as `{{ ... }}`. Instead, write actual numbers or neutral default values (e.g., 50 %) in place of placeholders.
Length limits (hard): approx. half a page total; each section ~80–120 words; bullet items one line.
Prohibited: Tool names, filler, placeholders.

No conflict with “Vision”:

If a Vision chapter exists, reuse the initiative title and, if needed, add a brief reference to its MVP (“see Vision”) — do not restate MVP details.

Gamechanger operationalises the Vision: focus on benchmark gap, forecast, steps, realtime checks and best practices. Do not duplicate lists from other chapters.

Structure (exactly 6 sections):

<h3>Long-term Initiative</h3> <p>One crisp title + a 1-sentence hook with a **metric-anchored promise** (e.g., “−30% cycle time in 6 months”). Add 1 sentence on why this fits {{ company_size_label }} in {{ branche }} right now.</p> <h3>Maturity benchmark</h3> <table> <thead><tr><th>Dimension</th><th>Your value (%)</th><th>Sector median (%)</th><th>Gap (%)</th></tr></thead> <tbody> <tr><td>Digitalisation</td><td>{{ benchmarks["Digitalisierung"].self | default(0) }}</td><td>{{ benchmarks["Digitalisierung"].industry | default(50) }}</td><td><!-- gap --></td></tr> <tr><td>Automation</td><td>{{ benchmarks["Automatisierung"].self | default(0) }}</td><td>{{ benchmarks["Automatisierung"].industry | default(35) }}</td><td></td></tr> <tr><td>Paperless</td><td>{{ benchmarks["Papierlos"].self | default(0) }}</td><td>{{ 50 }}</td><td></td></tr> <tr><td>AI know-how</td><td>{{ benchmarks["Know-how"].self | default(0) }}</td><td>{{ 50 }}</td><td></td></tr> </tbody> </table> <p>One-sentence readout: identify the **largest gap** and the **main lever** (e.g., shorter cycle time, lower cost, higher conversion).</p> <h3>Funding forecast</h3> <ul> <li><b>Starting:</b> … (short note + source)</li> <li><b>Ending:</b> … (short note + source)</li> <li><b>Key change:</b> … (short note + source)</li> </ul> <p>If no reliable information is available: <i>– no trustworthy changes known currently</i>.</p> <h3>Next steps</h3> <ul> <li><b>30 days:</b> 2–3 low-effort/high-impact actions with a clear metric (e.g., TTM, NPS, cycle time, € impact).</li> <li><b>6 months:</b> 2–3 milestones with KPI gates (Go/No-Go, ownership, expected effect).</li> </ul> <h3>Realtime check</h3> <p>What to validate **before** a decision: GDPR/EU AI Act class, data fitness & measurement (baseline, KPIs), DPA/AVV, guardrails (e.g., human-in-the-loop, logging), hosting/data location.</p> <h3>Best practices</h3> <ul> <li>Example A — use case, achieved KPI result, and one lessons-learned sentence (no tool names).</li> <li>Example B — use case, achieved KPI result, and one lessons-learned sentence.</li> </ul>

Style guards (hard):

Address the reader (“you”); no “we/I”.

No redundancies; each list starts with a strong verb/result.

Numbers: percentages without decimals (e.g., 35 %); Euro rounded (e.g., 5–10 k€).

{{ prompt_suffix }}

## Additional Instructions for the AI Status Report (EN)

Append these guidelines to the end of your existing prompt templates to elevate the AI Status Report to gold standard. They ensure concise lists, detailed actions and a clear, actionable roadmap.

### Trim and aggregate lists

* **Quick Wins (3 items)** – List no more than three immediately actionable wins. If there are more ideas, combine them into a single summary item titled “Additional Quick Wins.”
* **Risks (3 items)** – Mention at most three risks. Extra risks should be grouped under “Additional Risks,” summarised briefly.
* **Recommendations (5 items)** – Provide up to five recommendations. Any further suggestions are combined under “Additional Recommendations.”

### Structure of the Quick Wins

Each quick win should include the following fields:

1. **Title** – a concise name for the action.
2. **Effort** – estimated time required (e.g. “45 minutes” or “1–2 days”).
3. **Tool/Link** – the tool, service or web link used; otherwise “–”.
4. **Expected impact** – one sentence describing the benefit.
5. **Start today?** – “Yes” or “No” to indicate whether it can begin immediately.

### 12‑Month Roadmap

Include 6–8 entries, each with the columns:

* **Month/Timing** – e.g. “Month 1,” “Q2,” or a specific date.
* **Task** – the core activity.
* **Owner/Role** – person or role driving the task; when unclear, use “Owner/Project Lead.”
* **Dependencies** – prerequisites or preceding steps (“none” if none).
* **Benefit/Outcome** – expected value or goal.

### Gamechanger Chapter

This chapter presents up to three innovative approaches. Besides “Long-term initiative,” “Benchmark,” “Forecast” and “Best Practice,” each block should include a **Trade‑off/Side‑Effect**. Describe in one sentence potential risks or side effects of the idea.

### Funding Logic

1. **State before federal** – Always include at least two state programmes (e.g. Berlin) and prioritise them over federal programmes.
2. **Synonyms & alias mapping** – Consider synonyms (Solo, start‑up, founding) and abbreviations (BE → Berlin) when searching.
3. **GründungsBONUS & Coaching BONUS** – When relevant for Berlin, ensure these programmes are included.

### AI Tools Table

Ensure the following columns are present: **Tool**, **Use case**, **Data location** (or Data protection) and **Cost** (or Cost category). Use a consistent cost scale (e.g. “< €100”, “€100–500”, “€500–1 000”, “> €1 000”). Add a footnote explaining the cost scale.

### Further notes

* Remove any leftover KPI lines from the Executive Summary.
* Maintain a serious, optimistic tone. Make recommendations precise, including clear owners and timeframes.
* Ensure tables and footnotes are not truncated and that page breaks are tidy.

### Gold+ Additions

* **KPI chips:** Create three KPI chips (2–5 words) summarizing measurable metrics or goals (e.g., “TTM −20%”, “Lead quality +15%”, “Error rate −30%”). Provide them as a `kpi_chips` list.
* **ROI tag:** Provide a ROI category for each recommendation (benefit/effort: High, Medium, Low).
* **Roadmap legend:** Use “Owner/Project lead” as the default assignee and “none” as default dependencies if unspecified.
* **Trade-off:** Add a one-sentence trade-off or side effect for each gamechanger block.
* **Not recommended:** Provide one or two anti‑patterns in `not_recommended_html` (an HTML list).
* **Next meeting:** Provide a `next_meeting_text` suggesting a follow-up meeting focusing on a key KPI.
