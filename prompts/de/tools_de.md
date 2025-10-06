<!-- Datei: prompts/tools_de.md -->
<!-- PURPOSE: Tools-Empfehlungen (DE) auf Basis lokaler Daten mit erweitertem Schema -->
<!-- OUTPUT: Nur HTML-Fragment (ul/li, p, span). Keine <html>, kein DOCTYPE. -->

<p><strong>Empfohlene Werkzeuge (angepasst an Branche & Größe)</strong></p>
<ul>
  <!-- Erwartet: Backend ersetzt {{TOOLS_JSON}} durch JSON-Liste mit Feldern aus tools.csv -->
  <!-- Beispiel-Rendering: Name (Link) – One-liner – Chips für Aufwand/Preis/Compliance -->
  {{ for tool in TOOLS_JSON }}
    <li>
      <a href="{{ tool.homepage_url }}">{{ tool.name }}</a> – {{ tool.one_liner }}
      <span class="pill">Aufwand {{ tool.integration_effort_1to5 }}/5</span>
      <span class="pill">Preis {{ tool.pricing_tier }}</span>
      <span class="pill">DSGVO/AI-Act: {{ tool.gdpr_ai_act | upper }}</span>
    </li>
  {{ endfor }}
</ul>

<p class="muted">Hinweis: Aufwand 1 = Plug&Play, 5 = Projekt. „Preis“: € bis €€€€.</p>
