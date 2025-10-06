<!-- Datei: prompts/tools_en.md -->
<!-- OUTPUT: HTML fragment only. -->

<p><strong>Recommended tools (matched to industry &amp; size)</strong></p>
<ul>
  {{ for tool in TOOLS_JSON }}
    <li>
      <a href="{{ tool.homepage_url }}">{{ tool.name }}</a> – {{ tool.one_liner }}
      <span class="pill">Effort {{ tool.integration_effort_1to5 }}/5</span>
      <span class="pill">Price {{ tool.pricing_tier }}</span>
      <span class="pill">GDPR/AI-Act: {{ tool.gdpr_ai_act | upper }}</span>
    </li>
  {{ endfor }}
</ul>
<p class="muted">Note: Effort 1 = plug-and-play, 5 = project. “Price”: € to €€€€.</p>
