<!-- PURPOSE: Short risk matrix for solo consulting. Score = P*I, 1..5. -->
<!-- OUTPUT: HTML table. No dates. -->

<table>
  <thead>
    <tr><th>#</th><th>Risk</th><th>Area</th><th>P</th><th>I</th><th>Score</th><th>Mitigation</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td>Misclassification of client data</td><td>Compliance</td><td>3</td><td>4</td><td>12</td><td>DPIA triggers, define roles/logging, pseudonymization by default.</td></tr>
    <tr><td>2</td><td>Prompt leakage / confidential info in prompts</td><td>Security</td><td>3</td><td>4</td><td>12</td><td>Prompt linting, secret scanning, no‑PII rules.</td></tr>
    <tr><td>3</td><td>Hallucinations in offers/reports</td><td>Quality</td><td>2</td><td>4</td><td>8</td><td>Sources required, review checklist, out‑of‑scope blocker.</td></tr>
    <tr><td>4</td><td>Vendor lock‑in (non‑EU tool)</td><td>Vendor</td><td>2</td><td>4</td><td>8</td><td>DPA/SCC, exit plan, EU fallback defined.</td></tr>
    <tr><td>5</td><td>Unclear authorship/IP rights</td><td>Legal</td><td>2</td><td>3</td><td>6</td><td>Check usage rights; internal policy + training.</td></tr>
  </tbody>
</table>
