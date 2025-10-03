<!-- File: prompts/risks_en.md -->
**Task:** Build a **Top‑5 risk matrix** with **Probability (1–5)**, **Impact (1–5)**, **Score = P×I**, **Mitigation**.

**Include:** **EU AI Act/DSA/CRA/Data Act**, **bias/drift**, **ops/security**.

**Output format**
- **HTML table only** with `<thead>`/`<tbody>` and columns:  
  `# | Risk | Area | P | I | Score | Mitigation`.
- Areas: Compliance, Tech, Data, Operations, Reputation.

**Notes**
- Support mitigations using **{{NEWS_HTML}}** or provided sources.
- No external links unless sourced.

**Final line:** `As of: {{date}}`
