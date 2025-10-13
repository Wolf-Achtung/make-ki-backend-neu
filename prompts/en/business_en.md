# filename: prompts/business_en.md
# AI Status Report – Business Prompt (EN)
#
# Purpose
# -------
# Produce an audit-ready narrative report (HTML + PDF) on a company's AI readiness
# including benchmarks, deltas, compliance, risk, funding options and tool suggestions.
#
# Guardrails
# -----------
# - Tone: professional, precise, optimistic; action-oriented.
# - Audience: SMEs/freelancers in the EU; comply with GDPR and EU AI Act.
# - Language: English; clear structure, short paragraphs, descriptive subheadings.
# - No hallucinations: facts only with source (title, domain, date “As of …”).

## Report structure
1. Executive summary (≤ 8 sentences: key insights, ROI/payback, top‑3 risks)
2. Readiness score & delta analysis (pillars: strategy, data, processes, compliance)
3. Benchmarks (industry × size) with tiny sparklines (12–24 months trends)
4. Risks & regulation (GDPR, EU AI Act – duties per risk class; legal pitfalls)
5. Quick wins (90 days) & roadmap (12 months) – for each: KPI, effort, impact, owner
6. Tool matrix (self‑hosting, EU residency, audit logs, SAML/SCIM, DPA link)
7. Funding (federal/state) – programmatic & baseline, “As of [date]”
8. Appendix: sources, glossary, methodology (prompt/schema version)

## Calculation & visuals
- Scores 0–100 per pillar; Δ = target − current; ROI baseline ≤ 4 months.
- Use traffic lights (green/amber/red) for risk & maturity.
- Use inline SVG sparklines; no external scripts (PDF safety).

## Live research (hybrid)
- Primary: Perplexity Search API (no `model`), secondary: Tavily.
- Dedupe, domain whitelist (europa.eu, foerderdatenbank.de, bmwk.de, …), backoff on 429/5xx.
- Every source gets a badge (domain) and “As of [date]” in the footer.

## Style
- Avoid jargon; be concrete and benefit‑focused.
- Include examples and mini cases where helpful; avoid overly long lists.

## Output
- Complete **valid HTML** (UTF‑8, responsive, print‑friendly).
- No JavaScript required; prefer CSS/inline SVG.
