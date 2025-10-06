<!-- Datei: prompts/tools_de.md -->
<!-- OUTPUT: Nur HTML-Fragment (ul/li, p, span). -->

<p><strong>Empfohlene Werkzeuge (angepasst an Branche &amp; Größe)</strong></p>
<ul>
  {{ for tool in TOOLS_JSON }}
    <li>
      <a href="{{ tool.homepage_url }}">{{ tool.name }}</a> – {{ tool.one_liner }}
      <span class="pill">Aufwand {{ tool.integration_effort_1to5 }}/5</span>
      <span class="pill">Preis {{ tool.pricing_tier }}</span>
      <span class="pill">DSGVO/AI-Act: {{ tool.gdpr_ai_act | upper }}</span>
    </li>
  {{ endfor }}
</ul>
<p class="muted">Hinweis: Aufwand 1 = Plug&amp;Play, 5 = Projekt. „Preis“: € bis €€€€.</p>
