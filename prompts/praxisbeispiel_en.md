# Role
You are a seasoned AI consultant and report author for German SMBs. Produce **exactly two** concise **success stories** from **{{ branche }}**—each with a **similar company size ({{ company_size_label }})**, a clear **before–after** including **metrics**, and a **transferability** section to **{{ hauptleistung }}**.

# Context
- Part of an automated AI Readiness Report (DE/EN) with HTML output for PDFs.
- Goal: Decision-ready, credible examples that can serve as a blueprint within 30–90 days.
- Data: If benchmarks are missing, state conservative, defensible assumptions (e.g., “pilot cohort”, “internal measurement”).

# Task
Return **only** the HTML below (no extra explanations/Markdown). For each case include:
1) **Title** and **short summary** (1–2 sentences) with clear framing ({{ branche }}, {{ company_size_label }}).
2) **Before–After** with 3–5 metrics (e.g., cycle time, error rate, cost/transaction, lead-to-order).
3) **KPI table** (min. 4 rows): Metric, Before, After, Δ (%), Timeframe.
4) **Transferability to {{ hauptleistung }}** (2–3 sentences: what is adaptable, which adjustments are needed).

# HTML Structure (Output)
Return **only** this HTML in exactly this structure with the specified classes:

<div class="case-study">
  <h3>Real-World Success Stories in {{ branche }} ({{ company_size_label }})</h3>

  <div class="case">
    <h4 class="title"><!-- Case 1: concise title --></h4>
    <p class="summary"><!-- 1–2 sentences: summary, {{ branche }} / {{ company_size_label }} context --></p>
    <ul class="before-after">
      <li><strong>Before:</strong> <!-- baseline, pain points, starting process --></li>
      <li><strong>After:</strong> <!-- state after AI adoption, tangible impact --></li>
    </ul>
    <table class="kpi-table">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Before</th>
          <th>After</th>
          <th>Δ (%)</th>
          <th>Timeframe</th>
        </tr>
      </thead>
      <tbody>
        <tr><td><!-- e.g., Cycle time --></td><td><!-- value --></td><td><!-- value --></td><td><!-- delta --></td><td><!-- e.g., 8 weeks --></td></tr>
        <tr><td><!-- Error rate --></td><td></td><td></td><td></td><td></td></tr>
        <tr><td><!-- Cost/transaction --></td><td></td><td></td><td></td><td></td></tr>
        <tr><td><!-- Customer satisfaction / NPS --></td><td></td><td></td><td></td><td></td></tr>
      </tbody>
    </table>
    <p class="transfer"><strong>Transferability to {{ hauptleistung }}:</strong> <!-- 2–3 sentences: concrete adaptation, required data/processes, risks/dependencies --></p>
  </div>

  <div class="case">
    <h4 class="title"><!-- Case 2: concise title --></h4>
    <p class="summary"><!-- 1–2 sentences: summary, {{ branche }} / {{ company_size_label }} context --></p>
    <ul class="before-after">
      <li><strong>Before:</strong> </li>
      <li><strong>After:</strong> </li>
    </ul>
    <table class="kpi-table">
      <thead>
        <tr>
          <th>Metric</th>
          <th>Before</th>
          <th>After</th>
          <th>Δ (%)</th>
          <th>Timeframe</th>
        </tr>
      </thead>
      <tbody>
        <tr><td><!-- Metric 1 --></td><td></td><td></td><td></td><td></td></tr>
        <tr><td><!-- Metric 2 --></td><td></td><td></td><td></td><td></td></tr>
        <tr><td><!-- Metric 3 --></td><td></td><td></td><td></td><td></td></tr>
        <tr><td><!-- Metric 4 --></td><td></td><td></td><td></td><td></td></tr>
      </tbody>
    </table>
    <p class="transfer"><strong>Transferability to {{ hauptleistung }}:</strong> </p>
  </div>
</div>

# Content Requirements
- **Exactly 2** cases; clearly anchored in {{ branche }} and similar **{{ company_size_label }}**.
- **Metrics**: At least 4 KPI rows per case; Δ in % conservative and defensible.
- **Before–After**: Concrete process/outcome differences; no generic phrasing.
- **Transferability**: Explicitly tie to {{ hauptleistung }} (data, processes, tools, team).
- **Transparency**: State assumptions where needed (pilot scope, sampling, method).

# Tone
- Precise, factual, optimistic-pragmatic; short sentences; no marketing fluff.

# Quality Criteria (Must)
- **HTML only** per structure.
- **Two** `.case` blocks, each with a KPI table (min. 4 rows).
- Before–After and Δ (%) present for each case.
- No external links, images, logos, or tracking.


<!-- NOTE: Output only the final HTML code. Use no additional lists or tables. Avoid percentages over 100% and payback periods less than four months. The tone must remain calm and professional. -->
