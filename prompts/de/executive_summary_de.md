<!-- PURPOSE: Kompakte, umsetzbare Executive Summary nur für Beratung & Dienstleistungen (Solo, DE). -->
<!-- INPUT CONTEXT: Branche/Größe/Region/Hauptleistung/Ziele/Use-Cases/Zielgruppen kommen aus System-Prefix & Backend. -->
<!-- OUTPUT GUARDS: Gib NUR semantisches HTML zurück: <p>, <ul>, <ol>, <li>, <strong>, <em>, <a>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <h3>, <h4>, <br>. -->
<!-- VERBOTEN: KEINE Code-Fences (```), KEIN <!DOCTYPE>, KEINE <html>/<head>/<body>/<meta>/<style>. -->
<!-- DOMAIN PINS: Keine Beispiele aus Produktion/Automotive/Healthcare/Finance/Bau/Industrie. Nur Beratung & Dienstleistungen (Solo). -->
<!-- DATES: KEIN Datum einfügen (der Renderer setzt "Stand:" automatisch). -->
<!-- ROI BASELINE: Payback ~4 Monate (aus Backend). Nicht widersprechen, keine eigenen Summen erfinden. -->

<h3>Zusammenfassung</h3>
<ul>
  <li><strong>Strategische Ausrichtung:</strong> Der Schwerpunkt liegt auf {{ hauptleistung }} in Beratung &amp; Dienstleistungen (Solo, {{ bundesland_code }}). Ihre Positionierung ist klar und differenziert.</li>
  <li><strong>Haupthebel:</strong> Wichtigster Use‑Case: {{ (ki_usecases|first) if ki_usecases else "Prozessautomatisierung" }}. Datenquelle: {{ datenquellen|join(", ") if datenquellen else "Kunden- und Projektdaten" }}.</li>
  <li><strong>Erwarteter Nutzen:</strong> Deutliche Effizienzsteigerungen in Akquise, Angebotserstellung und Delivery sowie nachvollziehbare, konsistente Ergebnisse.</li>
  <li><strong>Wirtschaftlichkeit:</strong> Ziel ist ein Payback nach rund 4 Monaten. Priorisieren Sie Maßnahmen mit unmittelbarem Umsatz‑ bzw. Zeitgewinn.</li>
  <li><strong>Risiken &amp; Reifegrad:</strong> DSGVO- und AI‑Act‑Konformität ist grundlegend vorhanden. Bauen Sie eine solo‑taugliche Governance weiter aus (Rollen, Logging‑Umfang, Löschkonzept).</li>
</ul>

<h4>To‑dos für die nächsten 14 Tage</h4>
<ul>
  <li><strong>Prozessaufnahme:</strong> Identifizieren Sie 5–7 Kernprozesse und wählen Sie 2 Pilot‑Flows (z. B. Lead‑Qualifizierung, Angebotsentwurf).</li>
  <li><strong>Tool‑Set:</strong> Prüfen Sie eine EU‑konforme Basisausstattung (z. B. Nextcloud, Matomo, Jitsi, Odoo on‑prem). Non‑EU‑Tools nur mit AVV/SCC und Pseudonymisierung einsetzen.</li>
  <li><strong>Messbarkeit:</strong> Definieren Sie 3 KPIs (z. B. Angebotsdurchlaufzeit, Konversionsrate, Beratungsstunden pro Projekt) und beginnen Sie direkt mit dem Tracking.</li>
</ul>