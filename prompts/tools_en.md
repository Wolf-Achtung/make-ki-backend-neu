<!-- Datei: prompts/tools_en.md -->
<!-- PURPOSE: Tools recommendations (EN) using local data with extended schema -->
<!-- OUTPUT: HTML fragment only (ul/li, p, span). No <html> or DOCTYPE. -->

<p><strong>Recommended tools (matched to industry & size)</strong></p>
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
