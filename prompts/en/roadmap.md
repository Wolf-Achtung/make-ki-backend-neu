# Action plan – Digitalisation & AI in {{ branche }} (focus on {{ hauptleistung }})

Develop a realistic plan for the next twelve months, divided into three phases: **0–3 months**, **3–6 months** and **6–12 months**. Output exactly three HTML `<li>` elements inside a `<ul>`, one for each phase. Each entry starts with the period in bold and then lists 2–3 priority measures separated by semicolons.

When planning, consider:

* strategic goals ({{ projektziel }}) and priority use cases ({{ ki_usecases }})
* company size ({{ unternehmensgroesse }}) and investment budget ({{ investitionsbudget }})
* digitalisation and automation levels, the share of paperless processes and existing AI deployments ({{ ki_einsatz | join(', ') }})
* internal AI know‑how and risk appetite
* additional factors like time capacity, existing tools, regulated industry status, training interests and vision priority—without naming these variables.

Example measures (to be adapted):

- **0–3 months:** Start a data inventory; finalise the questionnaire and test an LLM prototype; launch a mini landing page for lead generation.
- **3–6 months:** Develop an MVP portal and onboard first pilot clients; automate the highest‑priority process (e.g. ticketing); submit funding applications and secure partners.
- **6–12 months:** Scale up a white‑label consulting tool; build governance structures; expand to new markets and grow training offerings.

Use these as inspiration and tailor them to the main service, company size and resources. Avoid generic advice and repetition. If a measure has been listed in quick wins or recommendations, choose a different focus.

The output should consist solely of an HTML unordered list (`<ul>…</ul>`) with three `<li>` elements corresponding to the three time horizons. Do not include tables or JSON blocks.

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
