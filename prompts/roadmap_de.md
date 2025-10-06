<!-- PURPOSE: 12‑Wochen‑Roadmap für Solo‑Praxis, abgestimmt auf {{ hauptleistung }} und Top‑Use‑Cases. -->
<!-- OUTPUT: Nur HTML. Keine Schritte aus Produktion/Automotive verwenden. -->

<ol>
  <li><strong>Woche 1–2: Setup &amp; Discovery</strong>
    <ul>
      <li>Erstellen Sie eine Prozesslandkarte (Akquise → Delivery → Aftercare) und wählen Sie zwei Pilot‑Flows aus.</li>
      <li>Richten Sie eine EU‑konforme Basis ein (Identitäten, Zugriff, Logging‑Umfang, Löschkonzept).</li>
      <li>Definieren Sie erste Prompt‑Bausteine (Angebot, Intake, Report‑Sektionen).</li>
    </ul>
  </li>
  <li><strong>Woche 3–4: Piloten</strong>
    <ul>
      <li>Pilot 1: {{ (ki_usecases|first) if ki_usecases else "Prozessautomatisierung" }} – testen Sie End‑to‑End (Eingabe bis Ergebnis).</li>
      <li>Pilot 2: Wissensbibliothek mit Retrieval (FAQ/Snippets) aufbauen.</li>
      <li>Beginn der Messung: drei KPIs pro Pilot erfassen.</li>
    </ul>
  </li>
  <li><strong>Woche 5–8: Skalieren &amp; absichern</strong>
    <ul>
      <li>Automatisierung auf angrenzende Schritte ausweiten (z. B. Templates → Kundenversion).</li>
      <li>Compliance‑Artefakte erstellen (AVV/SCC‑Check, DPIA‑Trigger, Löschregeln).</li>
      <li>Prompt‑Bibliothek verfeinern; Versionierung und Changelogs etablieren.</li>
    </ul>
  </li>
  <li><strong>Woche 9–12: Go‑Live &amp; Marketing</strong>
    <ul>
      <li>Durchlaufen Sie ein Go‑Live‑Gate mit Checklisten (Risiken/Compliance/Operations).</li>
      <li>Marketing: Erstellen Sie eine Fallstudie und zwei Snippets sowie Landing‑Elemente für {{ zielgruppen|join(", ") if zielgruppen else "KMU" }}.</li>
      <li>Führen Sie eine Retro durch und planen Sie die nächsten Prioritäten, wobei das Payback innerhalb von vier Monaten bleiben sollte.</li>
    </ul>
  </li>
</ol>