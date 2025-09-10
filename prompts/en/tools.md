# AI tools & software for {{ branche }} (as of {{ datum }})

Provide a clear overview of the most relevant AI tools for {{ branche }}, taking into account the main service ({{ hauptleistung }}), company size ({{ unternehmensgroesse }}) and IT infrastructure ({{ it_infrastruktur }}). Use the industry‑specific tool list ({{ tools_list }}) and complement it with current web‑search links ({{ websearch_links_tools }}) where useful. Choose only solutions that align with typical use cases in {{ branche }} and the strategic goals.

Return the tools in an HTML table with five columns:

<table>
  <tr>
    <th>Name</th>
    <th>Use case</th>
    <th>Data region</th>
    <th>Cost</th>
    <th>Link</th>
  </tr>
  <!-- up to 5–7 rows, fewer if fewer suitable tools are available -->
</table>

Guidelines:

- Choose a maximum of 5–7 tools; if fewer are appropriate, list only those. If no suitable tools are found, output only the note “No relevant tools found.”
- For each solution, state the main use case in 1–2 sentences, the data region (e.g. EU, USA/EU, or “variable”), an approximate price range (like “from €29/month”, “free”, “from €100/month”) and a link to the vendor’s website.
- Consider regulatory requirements (especially if {{ bundesland }} imposes stricter rules) and data‑protection preferences; favour EU or DE hosting where relevant.
- Do not repeat tools from other chapters and avoid general tips.

The output must be a pure HTML snippet containing the table above, or, if no tools are found, only the note. Do not include code fences or extra explanations.

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
