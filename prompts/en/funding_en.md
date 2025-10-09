<!-- Output: HTML fragment only. Uses FUNDING_JSON (merged whitelist + live). -->
<section class="card">
  <h2>Relevant Funding (curated)</h2>
  <table class="bm">
    <thead>
      <tr><th>Programme</th><th>Agency</th><th>Rate/Budget</th><th>As of</th></tr>
    </thead>
    <tbody>
      {{ for item in FUNDING_JSON }}
        <tr>
          <td><a href="{{ item.url }}">{{ item.title }}</a></td>
          <td>{{ item.source }}</td>
          <td>{{ item.rate }} {{ if item.cap_eur }}· up to {{ item.cap_eur }} €{{ endif }}</td>
          <td>{{ item.date }}</td>
        </tr>
      {{ endfor }}
    </tbody>
  </table>
  <div class="muted" style="margin-top:8px">
    Tip: Check deadlines and eligibility; for non-EU vendors ensure DPA/SCC & EU fallback.
  </div>
</section>
