<!-- PURPOSE: 12‑Wochen‑Roadmap, Solo‑fit, eng auf {{ hauptleistung }} und priorisierte Use‑Cases ausgerichtet. -->
<!-- OUTPUT: Nur HTML. Keine fachfremden Produktions-/Automotive‑Schritte. -->

<ol>
  <li><strong>W1–2: Setup &amp; Discovery</strong>
    <ul>
      <li>Prozess‑Mapping (Akquise → Delivery → Aftercare), 2 Pilot‑Flows auswählen.</li>
      <li>Tool‑Baseline EU‑tauglich (IDs, Zugriffe, Logging‑Scope, Löschkonzept).</li>
      <li>Prompt‑Bausteine definieren (Angebot, Intake, Report‑Abschnitte).</li>
    </ul>
  </li>
  <li><strong>W3–4: Piloten</strong>
    <ul>
      <li>Pilot 1: {{ (ki_usecases|first) if ki_usecases else "Prozessautomatisierung" }} – End‑to‑End testen (Input → Output).</li>
      <li>Pilot 2: Wissensbibliothek + Retrieval (FAQ/Snippets).</li>
      <li>Messkonzept aktiv: 3 KPIs je Pilot protokollieren.</li>
    </ul>
  </li>
  <li><strong>W5–8: Skalieren &amp; Absichern</strong>
    <ul>
      <li>Automatisierung auf angrenzende Schritte erweitern (z. B. Vorlagen → Kundenfassung).</li>
      <li>Compliance‑Artefakte erzeugen (AVV/SCC‑Check, DPIA‑Trigger, Löschregeln).</li>
      <li>Feintuning Prompt‑Library; Versionierung + Changelogs.</li>
    </ul>
  </li>
  <li><strong>W9–12: Go‑Live &amp; Vermarktung</strong>
    <ul>
      <li>Go‑Live‑Gate mit Checklisten (Risiko/Compliance/Operatives).</li>
      <li>Marketing: 1 Case + 2 Snippets + Landing‑Elemente für {{ zielgruppen|join(", ") if zielgruppen else "KMU" }}.</li>
      <li>Retrospektive, nächste Prioritäten planen (Payback &lt;= 4 Monate halten).</li>
    </ul>
  </li>
</ol>
