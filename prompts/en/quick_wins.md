# Quick Wins – immediate actions

## Style note – Warm, approachable language

The quick wins should feel like friendly, practical suggestions rather than terse bullet points. Use a warm, approachable tone and full sentences so that even readers without technical expertise can follow along. Take inspiration from the following example text, which shows how to talk about AI in an accessible and inviting way:

> When people talk about “artificial intelligence” today, many think of complicated technology, big corporations or future visions that have little to do with their everyday lives. But for small and medium‑sized enterprises, freelancers and the self‑employed, this is where a huge opportunity lies: AI is no longer just a tool for the “big players”. It can also help make day‑to‑day work lighter, clearer and more efficient in smaller organisations. From decades of experience as a managing director in the media industry, I know that real progress doesn’t come from buzzwords or glossy presentations, but from solutions that work in everyday life. AI can, for example, take over routine tasks, help sort information faster or open up new ways of reaching customers. Often it’s not about turning everything upside down immediately, but about starting in small steps – right where it makes life noticeably easier.

Use a similar narrative style: each quick win should begin with a bold keyword and then continue in one or two complete sentences describing what should be done, what concrete benefit it brings and how much effort it will require (e.g. “low effort”, “moderate effort”). Avoid fragmentary bullet phrases and technical jargon – write as if you’re explaining to a friend or colleague how they can get started straight away.

Generate an HTML unordered list (`<ul>…</ul>`) with up to three quick wins for the company. Each line should start with a bold keyword (`<b>…</b>`) and then in one or two full sentences describe a specific measure that can realistically be implemented within the next 0–3 months. Clearly state the benefit and use qualitative descriptions of the effort required (e.g. “low effort” or “takes a few hours”).

Use the free‑text fields (vision, biggest potential, moonshot, application area, strategic goals) and industry context to tailor suggestions. Optionally take into account weekly time capacity, existing tools, regulated industry status, training interests and vision priority to align quick wins with available resources, compliance needs and learning interests—without naming those variables. The lower the time capacity (e.g. ≤ 5 hours per week), the smaller and quicker the quick win should be; with more time available (e.g. 5–15 hours), the actions may be a little more involved.

Guidelines for possible quick wins:

- **Data inventory:** If data quality is low or unclear, the first step can be a structured data inventory or a data clean‑up. Describe the benefits of having tidy data and suggest an easy way to start.
- **Automation & scripts:** If there’s interest in automation or little time, a small automation – for example using general no‑code tools – can be a quick win. Don’t name specific products (like Zapier or n8n); instead describe the solution in general terms (e.g. “set up a simple automation to handle repetitive tasks”).
- **Governance light:** For solo businesses or small teams, drafting a one‑page AI policy (“light governance”) can be a meaningful quick win. Explain how a short policy creates clarity without overwhelming people.
- **Pilot & feedback:** If the biggest potential includes GPT‑based services or an AI portal, a lean MVP pilot with initial customers or partners can be a valuable quick win. Briefly outline the pilot and why starting small helps.
- Select up to three quick wins; don’t repeat items from the recommendations or the action plan.

If insufficient context is available, provide only the few quick wins that are possible. If no meaningful suggestions can be derived, output the following list: `<ul><li>No quick wins available. Additional information is needed for specific suggestions.</li></ul>`.

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
