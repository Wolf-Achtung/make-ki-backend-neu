<!-- COMPLIANCE (EN)
Context:
BRIEFING_JSON  = {{BRIEFING_JSON}}
SCORING_JSON   = {{SCORING_JSON}}
BUSINESS_JSON  = {{BUSINESS_JSON}}

Goal:
Produce a concise HTML section “Compliance Check (GDPR & EU AI Act)” leveraging briefing signals
(DPO, DPIA, deletion rules, incident paths, governance). No invented facts.

Rules:
- Tone: factual, actionable, compact.
- Mention a status only if present/inferable from the briefing.
- EU AI Act: typically minimal/limited for assistive/generative use; do not assume high‑risk.
- Prioritize 0–14‑day actions, then 12‑week hardening.
- CLEAN HTML only.

OUTPUT: -->
<section class="card">
  <h2>Compliance Check (GDPR &amp; EU AI Act)</h2>

  <h3>Briefing Highlights</h3>
  <ul class="pill-list">
    <!-- The model adds pills only if the signal exists in BRIEFING_JSON -->
  </ul>

  <h3>GDPR – Actions</h3>
  <ul>
    <li><strong>Roles &amp; RACI:</strong> assign ownership for prompt authoring, review, approval and incident reporting.</li>
    <li><strong>Data‑flow note:</strong> document sources, processing, storage and deletion rules; <em>No‑PII</em> policy for prompts.</li>
    <li><strong>DPA/SCC check:</strong> verify contracts for non‑EU vendors; default to pseudonymization &amp; secrecy controls.</li>
    <li><strong>Deletion &amp; retention:</strong> confirm rules; schedule semi‑annual reviews; automate deletions where possible.</li>
    <li><strong>Logging &amp; traceability:</strong> prompt changelog, versioning and approval records.</li>
  </ul>

  <h3>EU AI Act – Classification</h3>
  <p>Use cases are predominantly <em>minimal/limited</em>. Required: transparency notice, human oversight,
     error‑rate monitoring and documented purpose limitation.</p>

  <h3>Priorities (0–14 days)</h3>
  <ol>
    <li><strong>Compliance starter</strong>: 1‑page policy (no PII, sources required, approvals), define DPIA triggers, set roles/RACI.</li>
    <li><strong>DPA/SCC quick check</strong> for active SaaS; where non‑EU, define exit plan and EU fallback.</li>
    <li><strong>Prompt linting &amp; review</strong>: anti‑leakage/anti‑hallucination checklist; four‑eyes for external content.</li>
  </ol>

  <h3>12‑Week Hardening</h3>
  <ul>
    <li>Monthly <em>compliance review</em> (samples, error rates, incident log) with KPI traffic‑light.</li>
    <li>Training (90 min): privacy basics, safe prompts, sourcing, copyright.</li>
    <li>Optional: lightweight DPIA for prioritized flows; annual refresh.</li>
  </ul>
</section>
