# Quick Wins – immediate actions

Generate an HTML unordered list (`<ul>…</ul>`) with up to three quick wins. Each line should begin with a bold keyword (`<b>…</b>`) and describe a specific measure that can realistically be implemented within the next 0–3 months. Keep each line to one sentence and clearly state the benefit.

Use the free‑text fields (vision, biggest potential, moonshot, application area, strategic goals) and industry context to tailor suggestions. Optionally consider weekly time capacity, existing tools, regulated industry status, training interests and vision priority to align quick wins with resources, compliance and learning needs—without naming those variables. The lower the time capacity (e.g. ≤ 5 hours per week) the smaller and quicker the quick win should be; with more time available (e.g. 5–15 hours) the actions may be slightly more involved.

Guidelines:

- **Data inventory:** If data quality is low or unclear, a structured data inventory or data clean‑up should be the first quick win.
 - **Automation & scripts:** When there is interest in automation or a lack of time, a small automation – for example using general no‑code tools – can be a quick win.  Do not name specific products (like Zapier or n8n); describe the solution in general terms.
- **Governance light:** For solo businesses or small teams, drafting a one‑page AI policy can be a meaningful quick win.
- **Pilot & feedback:** If the greatest potential includes GPT‑based services or an AI portal, a lean MVP pilot with initial customers or partners can be a valuable quick win.
- Choose up to three quick wins; avoid repeating items from the recommendations or the action plan.

If insufficient context is available, list the few quick wins that are possible. If no meaningful suggestions can be derived, output the following list: `<ul><li>No quick wins available. Additional information is needed for specific suggestions.</li></ul>`.

Return only an HTML block containing the unordered list with 1–3 `<li>` elements, or the above error message.

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
