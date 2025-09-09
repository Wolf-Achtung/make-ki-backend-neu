Developer: {{ prompt_prefix }}

Goal: Generate the **Innovation & Gamechanger** chapter as valid HTML (excluding <html> and <body> tags).

Begin with a concise checklist (3-7 bullets) of what you will do; keep items conceptual, not implementation-level.

Context:
- Sector: {{ branche }}
- Company size: {{ company_size_label }} ({{ company_size_category }})
- Region/State: {{ bundesland|default('') }}
- Benchmarks/dimensions: {{ benchmarks|tojson }}
- KPI tiles: {{ kpis|tojson }}
- Innovation introduction (optional): {{ branchen_innovations_intro|default('') }}
- Funding badges (optional): {{ funding_badges|default([])|join(', ') }}

**Rules:**
- Only use <h3>, <p>, <ul>, <ol>, and <table> tags.
- No meta comments or placeholder text.

**Section Structure** (max. ~ page):
1. <h3>Moonshot</h3>
   - Bold sector-specific title (within <b>...</b>) and a concrete, measurable sentence (no marketing fluff).
2. <h3>Maturity benchmark</h3>
   - <table> with 4 rows (Digitalisation, Automation, Paperless, AI know-how); columns: Dimension | Your value (%) | Sector median (%) | Gap (%).
   - If benchmark or KPI data is missing, display “– insufficient data to display benchmark table.”
3. <h3>Funding forecast</h3>
   - <ul> with three items: “Starting”, “Ending”, and “Key change (short note + source)”.
   - If no reliable or available info, display “– no trustworthy changes known currently.”
4. <h3>Next steps</h3>
   - <ul>: 30 days (2–3 actions), 6 months (2–3 milestones; brief, verifiable).
   - If no actionable items, omit the <ul> and display “– no immediate next steps identified.”
5. <h3>Realtime check</h3>
   - One sentence on what to validate before decision (e.g., GDPR/EU AI Act, data basis, pilot metrics).
6. <h3>Best practices</h3>
   - Two concise, sector-specific outcome/metric examples (no tool names).
   - If no examples, display “– no best practices currently available.”

Following generation, review the output to confirm all required sections appear in the correct order. If any required numerical field (e.g., for benchmarks) is missing or invalid, use the specified fallback text. Do not include meta comments or placeholder text. After producing the HTML, validate that all data and logic rules have been followed; if not, self-correct.

{{ prompt_suffix }}

## Output Format

Return a single HTML string without <html> or <body> tags, in this exact order:

1. <h3>Moonshot</h3>
   <p><b>Sector Title</b> followed by a concrete, measurable one-sentence description.</p>
2. <h3>Maturity benchmark</h3>
   <table>
    <tr><th>Dimension</th><th>Your value (%)</th><th>Sector median (%)</th><th>Gap (%)</th></tr>
    <tr><td>Digitalisation</td><td>...</td><td>...</td><td>...</td></tr>
    <tr><td>Automation</td><td>...</td><td>...</td><td>...</td></tr>
    <tr><td>Paperless</td><td>...</td><td>...</td><td>...</td></tr>
    <tr><td>AI know-how</td><td>...</td><td>...</td><td>...</td></tr>
   </table>
   Or: <p>– insufficient data to display benchmark table.</p>
3. <h3>Funding forecast</h3>
   <ul>
    <li>Starting: ...</li>
    <li>Ending: ...</li>
    <li>Key change: ...</li>
   </ul>
   Or: <p>– no trustworthy changes known currently.</p>
4. <h3>Next steps</h3>
   <ul>
    <li>30 days: ...</li>
    <li>6 months: ...</li>
   </ul>
   Or: <p>– no immediate next steps identified.</p>
5. <h3>Realtime check</h3>
   <p>State what must be validated prior to any decision (e.g., GDPR/EU AI Act, data basis, pilot metrics).</p>
6. <h3>Best practices</h3>
   <ul>
    <li>Example 1: ...</li>
    <li>Example 2: ...</li>
   </ul>
   Or: <p>– no best practices currently available.</p>
