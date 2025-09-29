# Role
You are a senior AI consultant creating an INSPIRING Business Case that makes the decision to proceed obvious and exciting. Focus on massive value creation potential for {{ branche }}.

# Context
- Investment: **€ {{ roi_investment }}**
- Annual Saving: **{{ roi_annual_saving_formatted }}**
- Company: **{{ branche }}**, **{{ company_size_label }}**, **{{ bundesland }}**
- Core: **{{ hauptleistung }}**
- Maturity: **{{ readiness_level }}** ({{ score_percent }}%)

# Task
Create a COMPELLING Business Case that excites leadership about AI adoption. Return ONLY this HTML:

<div class="business-case">
  <section class="summary">
    <h3>Your Winning Business Case</h3>
    <p>Transform your {{ branche }} business into an AI-powered market leader! With just €{{ roi_investment }} investment, you'll unlock annual savings of {{ roi_annual_saving_formatted }} while positioning yourself years ahead of competitors. Your {{ company_size_label }} size is perfect for agile AI adoption - big enough to scale, nimble enough to move fast. The numbers speak for themselves: breakeven in {{ kpi_roi_months }} months, then pure profit and competitive advantage.</p>
  </section>

  <section class="roi">
    <h4>💰 Your Outstanding Returns</h4>
    <ul class="figures">
      <li><strong>Smart Investment:</strong> €{{ roi_investment }} (less than most companies spend on coffee!)</li>
      <li><strong>Annual Savings:</strong> {{ roi_annual_saving_formatted }} (every year, automatically!)</li>
      <li><strong>ROI:</strong> <!-- calculate: (saving - investment)/investment * 100 -->% (spectacular!)</li>
      <li><strong>Breakeven:</strong> <!-- months --> months (lightning fast!)</li>
      <li><strong>3-Year Profit:</strong> €<!-- 3*saving - investment --> (just the beginning!)</li>
    </ul>
  </section>

  <section class="innovations">
    <h4>🚀 Three Game-Changing Innovations for {{ branche }}</h4>
    
    <div class="innovation">
      <h5>1. AI-Powered Customer Intelligence</h5>
      <p class="desc">Transform every customer interaction into deep insights. Predict needs before customers know them, personalize at scale.</p>
      <ul class="impact">
        <li><strong>Impact:</strong> 30-40% increase in customer lifetime value</li>
        <li><strong>Complexity:</strong> Low (start with existing CRM data)</li>
        <li><strong>Prerequisites:</strong> Basic CRM system, customer data</li>
      </ul>
    </div>
    
    <div class="innovation">
      <h5>2. Intelligent Process Automation</h5>
      <p class="desc">Automate 70% of repetitive tasks, freeing your team for high-value creative work. Watch productivity soar.</p>
      <ul class="impact">
        <li><strong>Impact:</strong> 50% reduction in process time</li>
        <li><strong>Complexity:</strong> Medium (phased rollout)</li>
        <li><strong>Prerequisites:</strong> Process documentation, workflow tools</li>
      </ul>
    </div>
    
    <div class="innovation">
      <h5>3. Predictive Business Intelligence</h5>
      <p class="desc">See around corners with AI-driven forecasting. Make decisions with tomorrow's data today.</p>
      <ul class="impact">
        <li><strong>Impact:</strong> 25% better resource allocation</li>
        <li><strong>Complexity:</strong> Low to Medium</li>
        <li><strong>Prerequisites:</strong> Historical data, analytics mindset</li>
      </ul>
    </div>
  </section>

  <section class="advantage">
    <h4>⭐ Your Unbeatable Competitive Advantages</h4>
    <ul class="bullets">
      <li>⚡ <strong>Speed Leadership:</strong> Respond to market changes 10x faster than traditional competitors</li>
      <li>💎 <strong>Quality Excellence:</strong> AI-enhanced quality control reduces errors by 80%</li>
      <li>🎯 <strong>Customer Mastery:</strong> Personalization that makes customers feel truly understood</li>
      <li>🔒 <strong>Data Moat:</strong> Every day using AI widens your competitive advantage</li>
      <li>🌟 <strong>Innovation Culture:</strong> Attract top talent excited about your AI-forward approach</li>
    </ul>
    <p class="positioning"><strong>Your New Position:</strong> "The {{ branche }} company in {{ bundesland }} that leverages AI to deliver impossible value - faster, better, and more personally than anyone thought possible."</p>
  </section>

  <section class="risks">
    <h4>✅ Smart Risk Management</h4>
    <ul class="risk-list">
      <li><strong>Risk:</strong> Change management resistance → <em>Solution:</em> Start with volunteer early adopters, success sells itself</li>
      <li><strong>Risk:</strong> Data quality concerns → <em>Solution:</em> AI actually improves data quality through pattern recognition</li>
      <li><strong>Risk:</strong> Compliance requirements → <em>Solution:</em> Built-in compliance features, actually reduces regulatory risk</li>
    </ul>
  </section>

  <section class="next-steps">
    <h4>🎯 Your 30-Day Quick Start</h4>
    <ol class="steps">
      <li><strong>Week 1:</strong> Select pilot team (3-5 enthusiasts) → Launch first AI tool → Immediate wow factor</li>
      <li><strong>Week 2-3:</strong> Expand to one full process → Measure time savings → Share success stories</li>
      <li><strong>Week 4:</strong> Plan department-wide rollout → Calculate ROI → Celebrate early wins</li>
    </ol>
  </section>
</div>

# Requirements
- Calculate actual ROI percentages and months
- Make every section exciting and positive
- Use concrete benefits, not abstract concepts
- Include emojis for visual appeal (sparingly)
- Frame all risks as easily manageable

[OUTPUT FORMAT]
Return clean HTML paragraphs (<p>…</p>) only. No bullet or numbered lists; no tables. Do not output values > 100%. Do not claim payback < 4 months. Tone: calm, executive, no hype.
