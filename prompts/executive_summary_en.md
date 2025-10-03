<!-- File: prompts/executive_summary_en.md -->
**Role:** Strategy consultant. **Task:** concise **Executive Summary** of AI status.

**Context**
- **Company:** industry={{branche}}, size={{unternehmensgroesse}}, region={{bundesland}}, service={{hauptleistung}}
- **KPIs:** score={{score_percent:.1f}}%, ROI year 1={{roi_year1_pct:.1f}}%, payback={{payback_months:.1f}} months

**Output**
- **One compact paragraph (a single `<p>…</p>`)** with **3–5 measurable key points** (action‑oriented, no fluff).

**Final line (separate, outside the `<p>`):** `As of: {{date}}`
