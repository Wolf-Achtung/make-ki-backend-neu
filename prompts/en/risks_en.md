Produce a **risk matrix** (5 rows) as an HTML fragment.

**Columns (exact order):**
- Risk
- Area
- Likelihood (1–5)
- Impact (1–5)
- Mitigation (concrete action)
- Owner (role/function)
- Due (e.g., 30/90 days)

**Notes:**
- Context: SME/Germany; typical risks: prompt leakage, hallucinations, vendor lock‑in, PII/GDPR, quality defects.
- Output must be a **compact, semantic** `<table>` with `<thead>`/`<tbody>`; no fluff/explanations.
- Numbers only 1–5 (no percentages).