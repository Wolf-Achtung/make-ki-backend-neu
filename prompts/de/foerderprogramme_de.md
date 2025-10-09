<!-- Datei: prompts/de/foerderprogramme_de.md -->
<!-- OUTPUT: Ausschließlich HTML-Fragment (kein <html>/<head>/<body>). Nutzt FUNDING_JSON. -->

<section class="card">
  <h2>Relevante Förderprogramme (kuratiert)</h2>
  <table class="bm">
    <thead>
      <tr>
        <th>Programm</th>
        <th>Träger</th>
        <th>Quote/Budget</th>
        <th>Stand</th>
      </tr>
    </thead>
    <tbody>
      {{ for item in FUNDING_JSON }}
        <tr>
          <td><a href="{{ item.url }}">{{ item.title }}</a></td>
          <td>{{ item.source }}</td>
          <td>{{ item.rate }} {{ if item.cap_eur }}· bis {{ item.cap_eur }} €{{ endif }}</td>
          <td>{{ item.date }}</td>
        </tr>
      {{ endfor }}
    </tbody>
  </table>
  <div class="muted" style="margin-top:8px">
    Tipp: Fristen und Förderfähigkeit prüfen; bei Non-EU-Anbietern AVV/SCC & EU-Fallback beachten.
  </div>
</section>
