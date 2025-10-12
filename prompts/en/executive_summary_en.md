### Executive Summary (EN)

Context (BRIEFING_JSON, SCORING_JSON, BENCHMARKS_JSON, TOOLS_JSON, FUNDING_JSON, BUSINESS_JSON provided as JSON).
Goal: Three crisp bullets on **top Δ vs. benchmark**, **quick wins (≤60 days)** and **payback**. 
Avoid fluff. Return clean HTML fragment with <p> and <ul>/<li>.

Deliver:
<ul>
<li><b>Top Δ:</b> one sentence summarising the largest positive/negative deviation and its business relevance.</li>
<li><b>Quick wins:</b> 2–3 immediate actions with expected outcome.</li>
<li><b>Payback:</b> one sentence with computed payback (≤ {{BUSINESS_JSON.payback_months}} months) and operational meaning.</li>
</ul>
