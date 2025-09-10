# Compliance status & recommendations

Analyse the company’s compliance situation based on questionnaire data (e.g. data protection officer, technical safeguards, data‑protection impact assessments, reporting routes, deletion rules and knowledge of the EU AI Act). You may use an internal checklist to structure your work but do not output it.

## 1. Legal requirements & guidelines
- List the applicable legal frameworks (e.g. GDPR, ePrivacy, Digital Services Act, competition and consumer law, and any industry‑specific standards).
- Briefly note how existing company structures (e.g. data protection officer, technical measures) meet these requirements or where gaps exist.

## 2. Consent management & customer rights
- Describe consent management, CRM processes and implementation of privacy by design/default in bullet points.
- Include any reporting paths, deletion rules and internal AI expertise.

## 3. AI‑specific compliance
- List special obligations when using AI: documentation, transparency, fairness and bias analyses, impact assessments, and compliance with the EU AI Act (if relevant).

## 4. Immediate actions & strategic steps
- Provide 3–4 priority actions (e.g. data‑protection check, drafting a data‑processing agreement, establishing an AI governance framework, staff training, supplier audits, introducing a data‑protection management system).
- Adapt these actions to company size and main service, drawing on the questionnaire data.

## 5. Weaknesses & solutions
- Identify 2–3 current weaknesses (e.g. unclear data flows, missing deletion concepts, insufficient documentation).
- For each weakness, suggest a concrete first step towards remediation.

**Example Table:**

| Weakness                 | Solution proposal                                |
|-------------------------|--------------------------------------------------|
| Missing deletion rules  | Develop and implement a clear deletion concept   |
| Inadequate documentation| Create up‑to‑date process documentation          |

**Notes:**
- Use only the information provided in the questionnaire.
- Do not output placeholders or abbreviations like “n/a”; omit points with no data.
- Avoid generic checklists.
- Do not include tools, funding programmes or action‑plan measures here; they belong in other sections.

**Formatting:**
- Deliver your response as a structured Markdown document with five numbered main sections (## 1.–## 5.).
- Use short bullet lists in each section.
- In section 5, you may use a table or a list to present weaknesses and solutions.
- Omit sections or bullets if no data is available.

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

This chapter presents up to three innovative approaches. Besides “Moonshot,” “Benchmark,” “Forecast” and “Best Practice,” each block should include a **Trade‑off/Side‑Effect**. Describe in one sentence potential risks or side effects of the idea.

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
