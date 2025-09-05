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