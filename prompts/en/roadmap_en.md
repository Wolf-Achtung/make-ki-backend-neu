<!-- PURPOSE: 12‑week roadmap for a solo practice, aligned to {{ hauptleistung }} and top use cases. -->
<!-- OUTPUT: HTML only. Do not include manufacturing/automotive steps. -->

<ol>
  <li><strong>Weeks 1–2: Setup &amp; discovery</strong>
    <ul>
      <li>Map the end‑to‑end process (acquisition → delivery → aftercare) and choose two pilot flows.</li>
      <li>Establish an EU‑compliant baseline (identities, access control, logging scope, deletion concept).</li>
      <li>Draft your initial prompt building blocks (offer, intake, report sections).</li>
    </ul>
  </li>
  <li><strong>Weeks 3–4: Pilots</strong>
    <ul>
      <li>Pilot 1: {{ (ki_usecases|first) if ki_usecases else "process automation" }} – run an end‑to‑end test from input to outcome.</li>
      <li>Pilot 2: Build a knowledge library with retrieval (FAQ/snippets).</li>
      <li>Start measuring: capture three KPIs for each pilot.</li>
    </ul>
  </li>
  <li><strong>Weeks 5–8: Scale &amp; harden</strong>
    <ul>
      <li>Extend automation to adjacent steps (e.g. templated content → client version).</li>
      <li>Prepare compliance artefacts (DPA/SCC checks, DPIA triggers, deletion rules).</li>
      <li>Refine your prompt library with proper versioning and changelogs.</li>
    </ul>
  </li>
  <li><strong>Weeks 9–12: Go‑live &amp; marketing</strong>
    <ul>
      <li>Perform a go‑live gate using checklists (risk/compliance/operations).</li>
      <li>Marketing: craft one case study and two snippets plus landing elements tailored to {{ zielgruppen|join(", ") if zielgruppen else "SMBs" }}.</li>
      <li>Hold a retrospective and plan the next priorities, ensuring the payback remains within four months.</li>
    </ul>
  </li>
</ol>