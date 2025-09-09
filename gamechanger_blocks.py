# gamechanger_blocks.py

from innovation_intro import INNOVATION_INTRO
from typing import List

def build_gamechanger_blocks(data: dict, features: dict) -> str:
    """
    Generate formatted HTML blocks for the Innovation & Gamechanger section.

    Each enabled feature yields a self‑contained HTML snippet (h3/ul/p) so that the
    report template can render these items clearly.  If no features are
    enabled the returned string will be empty, allowing the template to
    omit the entire section.

    Parameters
    ----------
    data : dict
        The questionnaire data.  Used to select a branch‑specific
        introduction for best practice examples.
    features : dict
        A dictionary of feature flags indicating which blocks to include.

    Returns
    -------
    str
        A concatenated HTML string containing all selected blocks.
    """
    blocks: List[str] = []
    # Moonshot: one headline and a sentence prompting a visionary idea
    if features.get("moonshot"):
        blocks.append("<h3>Moonshot</h3><p>Formuliere eine visionäre, branchenspezifische Empfehlung (1 Titel + 1 Satz) für die nächsten 3 Jahre.</p>")
    # Maturity Benchmark: instructs to provide a table comparing company and industry
    if features.get("maturity_benchmark"):
        blocks.append("<h3>Reifegrad-Benchmark</h3><p>Stelle den KI-Reifegrad vs. Branchen-Median in einer kompakten Tabelle dar (4 Zeilen).</p>")
    # Förder Forecast: bullet list of programmes starting/ending/changed
    if features.get("foerder_forecast"):
        blocks.append("<h3>Förder-Forecast</h3><ul><li>Programme, die starten</li><li>Programme, die enden</li><li>Wesentliche Änderungen (Kurzsatz + Quelle)</li></ul>")
    # Next Steps: bullet list for 30 days and 6 months actions
    if features.get("next_steps"):
        blocks.append("<h3>Nächste Schritte</h3><ul><li>30 Tage: 2–3 Maßnahmen</li><li>6 Monate: 2–3 Meilensteine</li></ul>")
    # Realtime Check: simple paragraph instructing to verify current availability
    if features.get("realtime_check"):
        blocks.append("<h3>Realtime-Check</h3><p>Prüfe für jedes empfohlene Förderprogramm/Tool die Verfügbarkeit zum Stichtag {{ datum }} (kurzer Vermerk).</p>")
    # Best Practice examples: branch intro followed by two bullet examples
    if features.get("best_practice"):
        branche = data.get("branche", "").lower()
        intro = INNOVATION_INTRO.get(branche, "")
        # Escape curly braces in intro if any, as it's inserted as raw HTML
        intro_html = intro
        blocks.append(f"<h3>Best-Practices</h3><p>{intro_html}</p><ul><li>Use-Case A – Ergebnis/Kennzahl</li><li>Use-Case B – Ergebnis/Kennzahl</li></ul>")
    return "\n\n".join(blocks)
