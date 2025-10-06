<!-- PURPOSE: Kurze Risikomatrix für Solo‑Beratung. Score = P*I (1–5). -->
<!-- OUTPUT: HTML‑Tabelle. Keine Datumsfelder. -->

<table>
  <thead>
    <tr><th>#</th><th>Risiko</th><th>Bereich</th><th>P</th><th>I</th><th>Score</th><th>Mitigation</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td>Fehlklassifizierung von Kundendaten</td><td>Compliance</td><td>3</td><td>4</td><td>12</td><td>DPIA‑Trigger definieren, Rollen und Logging klar regeln, Pseudonymisierung als Standard etablieren.</td></tr>
    <tr><td>2</td><td>Prompt‑Leakage / vertrauliche Infos im Prompt</td><td>Sicherheit</td><td>3</td><td>4</td><td>12</td><td>Prompt‑Linting einführen, Secret‑Scanner nutzen und No‑PII‑Regeln schulen.</td></tr>
    <tr><td>3</td><td>Halluzinationen in Angeboten/Reports</td><td>Qualität</td><td>2</td><td>4</td><td>8</td><td>Quellenpflicht, Review‑Checklisten und Out‑of‑Scope‑Blocker implementieren.</td></tr>
    <tr><td>4</td><td>Vendor‑Lock‑in (Non‑EU‑Tool)</td><td>Lieferant</td><td>2</td><td>4</td><td>8</td><td>AVV/SCC prüfen, Exit‑Plan und EU‑Fallback definieren.</td></tr>
    <tr><td>5</td><td>Rechtsunsicherheit bei Urheberschaft</td><td>Recht</td><td>2</td><td>3</td><td>6</td><td>Nutzungsrechte klären, interne Richtlinien und Schulungen etablieren.</td></tr>
  </tbody>
</table>