<!-- File: prompts/recommendations_en.md -->
**Task:** Provide **3 prioritised recommendations (ROI‑based)** using:
- **{{business_case_json}}** (structured figures)
- **{{NEWS_HTML}}** (relevant, citable sources)

**Rules**
- Use only statements supported by the above sources; no fabrication.
- Mention ROI/payback **only** if present in the business case (else “n/a”).
- Prioritise by **Impact × Feasibility** (high → low).

**Output format (exactly)**
1. **Markdown table** with columns: `# | Recommendation | First step (0–14 days) | KPI | Dependencies | ROI/Payback`.
2. One sentence below: “Rationale for prioritisation”.

**Final line:** `As of: {{date}}`
