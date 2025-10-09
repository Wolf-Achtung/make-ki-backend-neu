<!-- Output: HTML fragment only. Uses TOOLS_JSON (live or local). -->
<section class="card">
  <h2>Recommended Tools (aligned with industry & size)</h2>
  <ul>
    {{ for t in TOOLS_JSON }}
      <li>
        <a href="{{ t.url }}">{{ t.title or t.name }}</a>
        <span class="muted">— {{ t.source or t.domain }}</span>
      </li>
    {{ endfor }}
  </ul>
  <div class="muted" style="margin-top:8px">
    Note (non-EU vendors): Use only with DPA/SCC, pseudonymisation, no secrets/PII; verify RBAC & logging; define an EU fallback.
  </div>
  <h3 style="margin-top:12px">3-Step Integration</h3>
  <ol>
    <li><strong>Pilot</strong> (1–2 flows): data slice, success criteria, review checklist.</li>
    <li><strong>Hardening</strong>: DPA/SCC check, deletion rules, prompt linting & versioning.</li>
    <li><strong>Roll-out</strong>: training, RACI, monitoring KPIs.</li>
  </ol>
</section>
