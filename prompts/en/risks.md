# Key Risks – potential challenges

## Style note – Clear narrative and mitigation

This section should highlight the most important challenges facing the company’s adoption of AI – but instead of terse bullet points, present each risk as a short, complete narrative. Use a friendly yet serious tone that explains not just the problem but also a first step towards mitigation. The style should be similar to the narrative example in the Quick Wins prompt: aim for accessibility and clarity.

Generate an HTML unordered list (`<ul>…</ul>`) with up to three key risks relevant to the company’s adoption of AI. Each list item must start with a bold keyword (`<b>…</b>`) and then continue with one or two full sentences that explain the risk and suggest a concrete first step to address it. Avoid technical jargon and write as if advising a colleague.

Draw on areas such as compliance, regulatory hurdles, resource constraints, data protection, bias and transparency, vendor lock‑in and risk appetite. Use free‑text responses and questionnaire fields to prioritise the most significant obstacles. Optionally incorporate time capacity, existing tools, regulated industry status, training interests and vision priority to identify additional dimensions of risk—without naming these variables.

Prioritise risks in this order where relevant:

1. **Legal & compliance:** Uncertain regulatory environments, missing contracts or unclear consent could create legal risks. Suggest performing a data‑protection audit and aligning practices with the EU AI Act and GDPR to mitigate them.
2. **Data protection & data quality:** Poor data quality, lack of deletion concepts or insufficient transparency threaten confidentiality and fairness. Recommend starting with a structured data inventory, clear deletion/access policies and regular bias checks.
3. **Budget & resource constraints:** Limited budget, scarce time or insufficient expertise could stall progress. Propose lean planning, leveraging external services and targeted upskilling to overcome these limitations.

If one of these categories is not relevant, you may replace it with another risk (e.g. dependency on single vendors). Do not mention the KPI categories (digitalisation, automation, paperless processes, AI know‑how) as risks.

Return only an HTML string containing the unordered list with 1–3 `<li>` elements; avoid any additional commentary outside the list.

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
