<!-- File: prompts/foerderprogramme_en.md -->
**Task:** Summarise funding programmes for **{{bundesland}} / {{unternehmensgroesse}} / {{branche}}**.

**Sources**
- **{{FUNDING_HTML}}** (CSV/portal) and **{{EU_CALLS_HTML}}** (EU portal) only.

**Output**
- **3 groups:** “Grants”, “Advisory”, “Loans/ERDF”.
- **Per programme:** one‑line description, **rate/max**, **deadline**, **link** (from the sources only).
- **Format:** **HTML table** with columns `Programme | Category | Rate/Max | Deadline | Link`.

**Close with** 3 notes on **combinability** and **deadlines**.  
**Final line:** `As of: {{date}}`
