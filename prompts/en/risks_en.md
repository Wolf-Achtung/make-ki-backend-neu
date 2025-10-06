<!-- PURPOSE: Short risk matrix for solo consulting. Score = P*I (1–5). -->
<!-- OUTPUT: HTML table. No dates. -->

<table>
  <thead>
    <tr><th>#</th><th>Risk</th><th>Area</th><th>P</th><th>I</th><th>Score</th><th>Mitigation</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td>Misclassification of client data</td><td>Compliance</td><td>3</td><td>4</td><td>12</td><td>Define DPIA triggers, clarify roles &amp; logging, standardise pseudonymisation.</td></tr>
    <tr><td>2</td><td>Prompt leakage / confidential info in prompts</td><td>Security</td><td>3</td><td>4</td><td>12</td><td>Implement prompt linting, secret scanning and no‑PII training.</td></tr>
    <tr><td>3</td><td>Hallucinations in offers/reports</td><td>Quality</td><td>2</td><td>4</td><td>8</td><td>Require sources, use review checklists and out‑of‑scope blockers.</td></tr>
    <tr><td>4</td><td>Vendor lock‑in (non‑EU tool)</td><td>Vendor</td><td>2</td><td>4</td><td>8</td><td>Check DPA/SCC, define exit plan and EU fallback.</td></tr>
    <tr><td>5</td><td>Unclear authorship/IP rights</td><td>Legal</td><td>2</td><td>3</td><td>6</td><td>Clarify usage rights and establish internal policies &amp; training.</td></tr>
  </tbody>
</table>