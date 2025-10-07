<!-- COMPLIANCE (DE)
Kontext (nur für das Modell, NICHT rendern):
BRIEFING_JSON  = {{BRIEFING_JSON}}
SCORING_JSON   = {{SCORING_JSON}}
BUSINESS_JSON  = {{BUSINESS_JSON}}

Ziel:
Erzeuge einen klar gegliederten HTML-Block „Compliance‑Check (DSGVO & EU AI Act)“,
der die Briefing-Signale nutzt (DPO, DPIA, Löschung, Meldewege, Governance) und
praxisnahe Maßnahmen priorisiert. Keine erfundenen Angaben.

Regeln:
- Sprache: sachlich, knapp, handlungsorientiert.
- Status nur dann nennen, wenn Signal im Briefing vorhanden/ableitbar.
- EU‑AI‑Act: i. d. R. Minimal/Limited (Assistenz, Generierung). Keine Hochrisiko‑Einstufung ohne Anhaltspunkte.
- 0–14‑Tage‑Aktionen zuerst, dann 12‑Wochen‑Verstetigung.
- Keine Marketingfloskeln, nur umsetzbare Punkte.
- AUSSCHLIESSLICH HTML zurückgeben.

Ausgabeformat: -->
<section class="card">
  <h2>Compliance‑Check (DSGVO &amp; EU AI Act)</h2>

  <h3>Schwerpunkte nach Briefing</h3>
  <ul class="pill-list">
    <!-- Jede Pill nur, wenn das Signal existiert -->
    <!-- Beispiele (das Modell füllt anhand von BRIEFING_JSON): -->
    <!-- <li><span class="pill">Datenschutzbeauftragter: vorhanden</span></li> -->
    <!-- <li><span class="pill">DPIA/Folgenabschätzung: ja</span></li> -->
    <!-- <li><span class="pill">Löschung/Retention: Regeln vorhanden</span></li> -->
    <!-- <li><span class="pill">Meldewege: teilweise</span></li> -->
    <!-- <li><span class="pill">Governance: ja</span></li> -->
  </ul>

  <h3>DSGVO – Maßnahmen</h3>
  <ul>
    <li><strong>Rollen &amp; RACI:</strong> Verantwortlichkeiten für Prompt‑Entwicklung, Review, Freigabe und Incident‑Meldung festlegen (inkl. Stellvertreter).</li>
    <li><strong>Datenfluss‑Dokumentation:</strong> Datenquellen, Verarbeitungen, Speicherorte und Löschfristen kurz dokumentieren; <em>No‑PII‑Regel</em> für Prompts.</li>
    <li><strong>AVV/SCC‑Checkliste:</strong> Für Nicht‑EU‑Anbieter Verträge prüfen/ergänzen; Pseudonymisierung &amp; Geheimnisschutz als Default.</li>
    <li><strong>Löschung &amp; Retention:</strong> Regeln bestätigen und halbjährlich reviewen; automatisierte Löschjobs, soweit möglich.</li>
    <li><strong>Logging &amp; Nachvollziehbarkeit:</strong> Prompt‑Changelog, Versionsstände und Freigabe‑Protokolle führen.</li>
  </ul>

  <h3>EU AI Act – Einordnung</h3>
  <p>Die typischen Vorhaben fallen überwiegend in <em>minimal</em> bis <em>limitiert</em> (Assistenz/Generierung).
     Anforderungen: Transparenzhinweis, menschliche Aufsicht, Monitoring von Fehlerraten, dokumentierte Zweckbindung.</p>

  <h3>Prioritäten (0–14 Tage)</h3>
  <ol>
    <li><strong>Compliance‑Starter</strong>: 1‑seitige Policy (No‑PII, Quellenpflicht, Freigaben), DPIA‑Trigger definieren, Rollen/RACI aufsetzen.</li>
    <li><strong>AVV/SCC‑Kurzprüfung</strong> für genutzte SaaS‑Anbieter; wenn Non‑EU: Exit‑Plan und EU‑Fallback skizzieren.</li>
    <li><strong>Prompt‑Linting &amp; Review</strong>: Checkliste gegen Prompt‑Leakage/Halluzination; Vier‑Augen‑Freigabe für externe Inhalte.</li>
  </ol>

  <h3>Verstetigung (12 Wochen)</h3>
  <ul>
    <li>Monatliches <em>Compliance‑Review</em> (Stichproben, Fehlerraten, Incident‑Log); KPI‑Ampel im Team‑Board.</li>
    <li>Schulung (90 Min.): Datenschutz‑Basics, sichere Prompts, Quellenpflicht, Urheberrecht.</li>
    <li>Optional: schlanke DPIA für die priorisierten Flows; jährliche Aktualisierung.</li>
  </ul>
</section>
