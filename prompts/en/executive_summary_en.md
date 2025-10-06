# GUARD
- Answer in English only.
- Return an HTML fragment only (no <html>, <head>, <body>).
- No placeholders/templates/braces in output. No code fences.
- Allowed tags: <h4>, <h5>, <p>, <ul>, <ol>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <em>, <strong>, <code>.

# CONTEXT
- BRIEFING (JSON): {{BRIEFING_JSON}}
- SCORE (JSON): {{SCORING_JSON}}
- BENCHMARKS (JSON): {{BENCHMARKS_JSON}}

# PINS
- Always factor in industry, company size and core offering, plus all free‑text fields.
- Use DE/EN key fallbacks (see mapping above) if fields differ.

# TASK
Create a concise <h4>Executive Summary</h4> with:
- <h5>Key Takeaways</h5> (exactly 5 bullets; business‑outcome focus).
- <h5>Next 0–14 days</h5> (3–4 actionable steps).
- Reflect opportunities/risks tailored to industry, size and core offering.
