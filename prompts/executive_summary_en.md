# filename: prompts/executive_summary_en.md
Context:
- Industry: {{branche}}, State: {{bundesland}}, Size: {{unternehmensgroesse}}
- Core offering: {{hauptleistung}}
- Benchmarks: {{benchmarks_json}}
- Business case: {{business_case_json}}

Task:
Write a crisp executive summary (≤180 words) including:
1) Situation & opportunity (1–2 sentences).
2) Value levers (bullets: efficiency, quality, customer, risk).
3) Metrics (Year‑1 ROI, payback months, 3‑year profit, hours saved/month) from the business case.
4) First step (actionable within 14 days).

Format:
- 3 short paragraphs + a bullet list “Next step”.
- Final line “As of: {{date}}”.
