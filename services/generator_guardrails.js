
/**
 * Guardrails for report generation (Strict Mode).
 * - Whitelist-only for tools and funding.
 * - No placeholders, anecdotes, or vendor-invented names.
 * - Sections are omitted if required inputs are missing.
 */
export function enforceStrictMode({ sections, inputs, toolWhitelist, fundingWhitelist, logger = console }) {
  const out = {};
  const required = (arr) => arr.every(k => inputs[k] && String(inputs[k]).trim() !== "");

  // Helper: detect placeholder patterns
  const looksLikePlaceholder = (s) => {
    if (!s) return true;
    const t = String(s).toLowerCase();
    return (
      t.includes("mehr erfahren") ||
      t.includes("lorem ipsum") ||
      /%/.test(t) && /max\.\s*€?/.test(t) ||   // e.g. "% / €" artefacts
      t.includes("fehler: ungültige oder fehlende eingabedaten") ||
      /unternehmens[w-]*o?zean/.test(t)       // metaphoric "Ozean" story
    );
  };

  // 1) Executive summary – require at least 2 opportunities + 2 risks
  if (sections.summary) {
    const ok = Array.isArray(sections.summary.opportunities) && sections.summary.opportunities.length >= 2 &&
              Array.isArray(sections.summary.risks) && sections.summary.risks.length >= 2;
    if (ok && !sections.summary.opportunities.some(looksLikePlaceholder) && !sections.summary.risks.some(looksLikePlaceholder)) {
      out.summary = sections.summary;
    } else {
      logger.warn("Summary omitted (strict mode).");
    }
  }

  // 2) Quick Wins – only from static partials or vetted list
  if (sections.quickWins && sections.quickWins.kind === "static") {
    out.quickWins = sections.quickWins;
  } else {
    logger.warn("Quick Wins must be static; omitted.");
  }

  // 3) Tools – filter against whitelist
  if (Array.isArray(sections.tools)) {
    const wl = new Map(toolWhitelist.map(t => [t.name.toLowerCase(), t]));
    const filtered = sections.tools.map(t => wl.get(String(t.name || "").toLowerCase())).filter(Boolean);
    if (filtered.length) out.tools = filtered;
  }

  // 4) Roadmap – ensure bullets exist
  if (sections.roadmap && ["q90","q180","q365"].every(k => Array.isArray(sections.roadmap[k]) && sections.roadmap[k].length >= 2)) {
    out.roadmap = sections.roadmap;
  }

  // 5) EU AI Act – must come from static snippet
  if (sections.euAiAct && sections.euAiAct.kind === "static") {
    out.euAiAct = sections.euAiAct;
  }

  // 6) Funding – whitelist filter + status present
  if (Array.isArray(sections.funding)) {
    const wl = new Map(fundingWhitelist.map(f => [f.name.toLowerCase(), f]));
    const filtered = [];
    for (const f of sections.funding) {
      const ref = wl.get(String(f.name || "").toLowerCase());
      if (ref && ref.status && !looksLikePlaceholder(ref.status)) filtered.push(ref);
    }
    if (filtered.length) out.funding = filtered;
  }

  // 7) Vision – only if required inputs present and no placeholders
  if (sections.vision && required(["ki_geschaeftsmodell_vision"])) {
    const { headline, actions } = sections.vision;
    const ok = headline && !looksLikePlaceholder(headline) &&
               Array.isArray(actions) && actions.length >= 2 && !actions.some(looksLikePlaceholder);
    if (ok) out.vision = sections.vision;
  }

  return out;
}
