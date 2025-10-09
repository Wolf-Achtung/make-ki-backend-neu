<!-- Datei: prompts/de/tools_de.md -->
<!-- OUTPUT: Ausschließlich HTML-Fragment. Nutzt TOOLS_JSON (lokal oder live). -->

<section class="card">
  <h2>Empfohlene Werkzeuge (angepasst an Branche &amp; Größe)</h2>
  <ul>
    {{ for t in TOOLS_JSON }}
      <li>
        <a href="{{ t.url }}">{{ t.title or t.name }}</a>
        <span class="muted">— {{ t.source or t.domain }}</span>
      </li>
    {{ endfor }}
  </ul>
  <div class="muted" style="margin-top:8px">
    Hinweis (Non-EU-Tools): Einsatz nur mit AVV/SCC, Pseudonymisierung, ohne Geheimnisse/PII; RBAC &amp; Logging prüfen; EU-Fallback definieren.
  </div>
  <h3 style="margin-top:12px">Integration in 3 Schritten</h3>
  <ol>
    <li><strong>Pilot</strong> (1–2 Flows): Datenausschnitt, Erfolgskriterien, Review-Checklist.</li>
    <li><strong>Absicherung</strong>: AVV/SCC-Check, Löschregeln, Prompt-Linting &amp; Versionierung.</li>
    <li><strong>Rollout</strong>: Schulung, Rollen/RACI, Monitoring-KPIs.</li>
  </ol>
</section>
