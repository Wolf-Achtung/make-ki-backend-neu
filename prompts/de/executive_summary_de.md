<!-- PURPOSE: Kompakte, umsetzbare Executive Summary nur für Beratung & Dienstleistungen (Solo, DE). -->
<!-- INPUT CONTEXT: Branche/Größe/Region/Hauptleistung/Ziele/Use-Cases/Zielgruppen kommen aus System-Prefix & Backend. -->
<!-- OUTPUT GUARDS: Gib NUR semantisches HTML zurück: <p>, <ul>, <ol>, <li>, <strong>, <em>, <a>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <h3>, <h4>, <br>. -->
<!-- VERBIETEN: KEINE Code-Fences (```), KEIN <!DOCTYPE>, KEINE <html>/<head>/<body>/<meta>/<style>. -->
<!-- DOMAIN PINS: Keine Beispiele aus Produktion/Automotive/Healthcare/Finance/Bau/Industrie. Nur Beratung & Dienstleistungen (Solo). -->
<!-- DATES: KEIN Datum einfügen (der Renderer setzt "Stand:" automatisch). -->
<!-- ROI BASELINE: Payback ~4 Monate (aus Backend). Nicht widersprechen, keine eigenen Summen erfinden. -->

<h3>Kernaussagen</h3>
<ul>
  <li><strong>Strategische Lage:</strong> Fokus auf {{ hauptleistung }} mit klarer Positionierung in Beratung &amp; Dienstleistungen (Solo, {{ bundesland_code }}).</li>
  <li><strong>Wichtigste Hebel:</strong> Priorisierter Use‑Case: {{ (ki_usecases|first) if ki_usecases else "Prozessautomatisierung" }}; Datenbasis: {{ datenquellen|join(", ") if datenquellen else "Kunden-/Projektdaten" }}.</li>
  <li><strong>Erwarteter Nutzen:</strong> Effizienzgewinne in Akquise/Delivery/Wissensmanagement; qualitative Vorteile: Geschwindigkeit, Konsistenz, Nachvollziehbarkeit.</li>
  <li><strong>Wirtschaftlichkeit:</strong> Payback‑Ziel ~4 Monate (Baseline). Investitionen priorisieren, die <em>direkten</em> Umsatz-/Zeitnutzen erzeugen.</li>
  <li><strong>Risiko &amp; Reife:</strong> DSGVO/AI‑Act‑Pfad vorhanden; Solo‑taugliche Governance (Rollenklarheit, Logging‑Scope, Löschregeln) ausbauen.</li>
</ul>

<h4>Was jetzt wichtig ist (0–14 Tage)</h4>
<ul>
  <li><strong>Discovery kurz &amp; hart:</strong> 5–7 Kernprozesse mappen, 2 Pilot‑Flows auswählen (Lead‑Qualifizierung, Angebotsentwurf o. Ä.).</li>
  <li><strong>Tooling schlank:</strong> EU‑taugliche Basis (z. B. Nextcloud/Matomo/Jitsi/Odoo‑on‑prem möglich) prüfen; Non‑EU nur mit AVV/SCC &amp; Pseudonymisierung.</li>
  <li><strong>Messbar machen:</strong> 3 KPIs definieren (z. B. Angebots‑Durchlaufzeit, Akquise‑Konversionsrate, Beratungsstunden/Projekt).</li>
</ul>
