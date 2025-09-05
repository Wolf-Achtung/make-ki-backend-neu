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