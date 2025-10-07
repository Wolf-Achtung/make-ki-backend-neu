<!-- Datei: prompts/foerderprogramme_de.md -->
<!-- OUTPUT: Nur HTML-Fragment. Nutzt FUNDING_JSON (lokal oder live) -->

<p><strong>Relevante Förderprogramme</strong></p>
<ul>
  {{ for item in FUNDING_JSON }}
    <li>
      <a href="{{ item.url }}">{{ item.title }}</a>
      <span class="pill">{{ item.region }}</span>
      {{ if item.amount_hint }}<span class="pill">{{ item.amount_hint }}</span>{{ endif }}
    </li>
  {{ endfor }}
</ul>
<p class="muted">Tipp: Prüfen Sie Fristen und Voraussetzungen; kombinieren Sie Beratung, Qualifizierung und Implementierung.</p>
