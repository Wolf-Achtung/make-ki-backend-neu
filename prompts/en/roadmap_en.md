<!-- PURPOSE: 12‑week roadmap for solo practice, aligned to {{ hauptleistung }} and top use cases. -->
<!-- OUTPUT: HTML only. No manufacturing/automotive steps. -->

<ol>
  <li><strong>W1–2: Setup &amp; discovery</strong>
    <ul>
      <li>Process map (acquisition → delivery → aftercare), pick 2 pilot flows.</li>
      <li>EU‑ready baseline (IDs, access, logging scope, deletion concept).</li>
      <li>Define prompt building blocks (offer, intake, report sections).</li>
    </ul>
  </li>
  <li><strong>W3–4: Pilots</strong>
    <ul>
      <li>Pilot 1: {{ (ki_usecases|first) if ki_usecases else "process automation" }} – test end‑to‑end (input → output).</li>
      <li>Pilot 2: Knowledge library + retrieval (FAQ/snippets).</li>
      <li>Measurement live: 3 KPIs per pilot captured.</li>
    </ul>
  </li>
  <li><strong>W5–8: Scale &amp; harden</strong>
    <ul>
      <li>Extend automation to adjacent steps (e.g., templates → client version).</li>
      <li>Create compliance artefacts (DPA/SCC check, DPIA trigger, deletion rules).</li>
      <li>Refine prompt library; versioning + changelogs.</li>
    </ul>
  </li>
  <li><strong>W9–12: Go‑live &amp; marketing</strong>
    <ul>
      <li>Go‑live gate with checklists (risk/compliance/operations).</li>
      <li>Marketing: 1 case + 2 snippets + landing elements for {{ zielgruppen|join(", ") if zielgruppen else "SMBs" }}.</li>
      <li>Retro; plan next priorities (keep payback &lt;= 4 months).</li>
    </ul>
  </li>
</ol>
