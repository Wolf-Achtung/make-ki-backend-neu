# Recommendations – Top 5

Generate an HTML ordered list (`<ol>…</ol>`) with the five most important recommendations for the company. Each recommendation should start with a bold action verb and, in one sentence, describe the goal, expected **benefit** and required effort.  Use plain, accessible language and avoid buzzwords.  Conclude each sentence with the **benefit/effort** ratio in brackets (e.g. `(H/M)` for high benefit and medium effort).

Combine strategic initiatives (focusing, strengthening the data foundation, establishing governance, piloting & scaling, empowering & networking) with tangible steps derived from vision, strategic goals, biggest potential, moonshot and benchmarks. Avoid repeating items from the quick wins or the action plan.

Tailor the recommendations to company size (solo, small team, SME), time capacity, regulatory requirements, existing tools, training interests and vision priority—without explicitly naming those variables. Solo businesses need cost‑effective, modular measures; larger SMEs can pursue more complex efforts.

Suggested structure (to adapt as needed):

1. **Focus:** Clarify vision and strategy, set priorities and formulate a roadmap that concretises the greatest potential (e.g. GPT‑based services or an AI portal). `(H/M)`
2. **Strengthen data foundation:** Conduct a data inventory, establish central data sources (CRM/ERP) and improve data quality to build a robust basis for AI applications. `(M/M)`
3. **Establish governance:** Implement a lean AI‑governance framework, including data‑protection checks, fairness reviews and compliance processes; for solo companies, a brief “AI policy light” may suffice. `(M/M)`
4. **Pilot & scale:** Prototype a priority use case (e.g. a GPT‑based service MVP), test with selected partners and scale if successful, using quick feedback loops. `(M/M)`
5. **Enable & connect:** Educate your team and stakeholders through training, workshops or external coaching, build networks and partnerships, and address training interests (e.g. automation & scripts). `(L/L)`

Order your actual recommendations by strategic relevance and overall benefit; if tied, choose the lower‑effort action first. The output must be a pure HTML `<ol>` with five `<li>` elements.

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
