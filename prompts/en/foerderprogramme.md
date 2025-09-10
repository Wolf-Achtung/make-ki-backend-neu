# Funding programmes for digitalisation & AI (as of {{ datum }})

List the 3–5 most relevant funding programmes available for the {{ branche }} sector in the region {{ bundesland }} and for company size {{ unternehmensgroesse }}. Consider past funding experience ({{ bisherige_foerdermittel }}) and current interest in additional funding ({{ interesse_foerderung }}). Use programmes from {{ foerderprogramme_list }} and supplement them with recent web‑search results ({{ websearch_links_foerder }}) if appropriate.

Present the programmes in an HTML table with four columns:

<table>
  <tr>
    <th>Name</th>
    <th>Target group</th>
    <th>Funding amount</th>
    <th>Link</th>
  </tr>
  <!-- list up to five programmes -->
</table>

Guidelines:

- Select 3–5 programmes that best match {{ branche }}, {{ bundesland }} and {{ unternehmensgroesse }}. If no suitable programmes are found, output only the empty table followed by the note “No suitable funding programmes found for the selected criteria.”
- Summarise the funding amount concisely (e.g. “up to 50%” or “max. €10 000”). Sort programmes by relevance (sector > region > company size).
- Take into account previous funding and interest in further programmes to personalise your selection.
- Do not mention tools or other measures here; these are covered in separate chapters.

The output must be a pure HTML snippet: either the table with 0–5 data rows or, if no programmes fit, the empty table and the note. Do not add comments or extra explanations.

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
