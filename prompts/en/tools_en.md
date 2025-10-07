<!-- TOOLS (EN)
Context (DO NOT render):
BRIEFING_JSON = {{BRIEFING_JSON}}
TOOLS_JSON    = {{TOOLS_JSON}}

Goal:
Produce an HTML block “Recommended Tools (fit for industry & size)” based on TOOLS_JSON.

Rules:
- Use ONLY items from TOOLS_JSON. No external sources.
- Ordering: (1) gdpr_ai_act: yes → partial → unknown, (2) vendor_region: EU/DE → Other/US, (3) integration_effort_1to5 ascending.
- Show up to 6–8 tools.
- Each tool as one <li> with name (linked), one‑liner and pills: effort, price, GDPR/AI‑Act badge, region/residency.
- If a field is missing, omit that pill; never invent values.
- Append a Non‑EU notice (AVV/SCC, pseudonymization, no secrets/PII, logging, RBAC) and a 3‑step integration plan.
- Return CLEAN HTML ONLY.

OUTPUT (HTML only): -->
<section class="card">
  <h2>Recommended Tools (fit for industry &amp; size)</h2>
  <ul class="tool-list">
    <!-- Iterate over TOOLS_JSON in the specified order and render exactly ONE <li> per tool:
    <li>
      <a href="https://example.com">Tool Name</a> – concise value statement
      <span class="pill">Effort 2/5</span>
      <span class="pill">Price €€</span>
      <span class="pill">GDPR/AI‑Act: COMPLIANT|PARTIAL|UNKNOWN</span>
      <span class="pill">Region EU/DE; Residency {{data_residency}}</span>
    </li>
    -->
  </ul>

  <div class="muted" style="margin-top:8px">
    Note (Non‑EU tools): use only with AVV/SCC, pseudonymization, no secrets/PII; verify logging &amp; RBAC; define an EU fallback.
  </div>

  <h3 style="margin-top:12px">3‑Step Integration</h3>
  <ol>
    <li><strong>Pilot</strong> (1–2 flows): narrow dataset, success KPIs, review checklist.</li>
    <li><strong>Hardening</strong>: AVV/SCC check, deletion rules, prompt linting &amp; versioning.</li>
    <li><strong>Rollout</strong>: training, roles/RACI, monitoring KPIs (e.g., turnaround time, error rate).</li>
  </ol>
</section>
