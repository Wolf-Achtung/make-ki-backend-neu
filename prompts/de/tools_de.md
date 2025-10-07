<!-- TOOLS (DE)
Kontext (NICHT rendern):
BRIEFING_JSON = {{BRIEFING_JSON}}
TOOLS_JSON    = {{TOOLS_JSON}}

Ziel:
Erzeuge einen HTML‑Block “Empfohlene Werkzeuge (angepasst an Branche & Größe)” auf Basis von TOOLS_JSON.

Regeln:
- Nutze NUR die Einträge aus TOOLS_JSON (Array von Tools). Keine Fremdquellen.
- Sortierung: (1) gdpr_ai_act: yes → partial → unknown, (2) vendor_region: EU/DE → Other/US, (3) integration_effort_1to5 aufsteigend.
- Max. 6–8 Tools anzeigen.
- Jedes Tool als <li> mit Name (verlinkt), One‑liner und Pills: Aufwand, Preis, GDPR/AI‑Act‑Badge, Region/Residency.
- Falls ein Feld fehlt, lasse die entsprechende Pill weg, erfinde nichts.
- Hinweisblock zu Non‑EU‑Tools anfügen (AVV/SCC, Pseudonymisierung, keine Geheimnisse/PII, Logging, RBAC).
- Kurzer 3‑Schritte‑Integrationsplan am Ende.
- Gib AUSSCHLIESSLICH HTML zurück.

Ausgabeformat (nur HTML): -->
<section class="card">
  <h2>Empfohlene Werkzeuge (angepasst an Branche &amp; Größe)</h2>
  <ul class="tool-list">
    <!-- Iteriere über TOOLS_JSON nach obiger Sortierung und rendere je Tool genau EINE <li>-Zeile: -->
    <!-- BEISPIELSTRUKTUR (Platzhalter, logikbasiert aus TOOLS_JSON befüllen):
    <li>
      <a href="https://example.com">Toolname</a> – kurzer Nutzen‑Satz
      <span class="pill">Aufwand 2/5</span>
      <span class="pill">Preis €€</span>
      <span class="pill">GDPR/AI‑Act: KONFORM|TEILWEISE|UNKLAR</span>
      <span class="pill">Region EU/DE; Residency {{data_residency}}</span>
    </li>
    -->
  </ul>

  <div class="muted" style="margin-top:8px">
    Hinweis (Non‑EU‑Tools): Einsatz nur mit AVV/SCC, Pseudonymisierung, ohne Geheimnisse/PII; Logging &amp; Rollenrechte prüfen; EU‑Fallback definieren.
  </div>

  <h3 style="margin-top:12px">Integration in 3 Schritten</h3>
  <ol>
    <li><strong>Pilot</strong> (1–2 Flows): kleiner Datenausschnitt, Erfolgskriterien, Review‑Checklist.</li>
    <li><strong>Absicherung</strong>: AVV/SCC‑Check, Löschregeln, Prompt‑Linting &amp; Versionskontrolle.</li>
    <li><strong>Rollout</strong>: Schulung, Rollen/RACI, Monitoring‑KPIs (z. B. Durchlaufzeit, Fehlerquote).</li>
  </ol>
</section>
