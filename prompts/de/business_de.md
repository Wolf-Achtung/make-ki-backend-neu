# filename: prompts/business_de.md
# KI‑Status‑Report – Geschäfts-Prompt (DE)
#
# Ziel
# ----
# Erzeuge einen audit-fähigen, narrativen Report (HTML + PDF) zur KI‑Readiness eines Unternehmens
# mit Benchmarks, Δ‑Analysen, Compliance, Risiken, Fördermöglichkeiten und Tool‑Empfehlungen.
#
# Leitplanken
# -----------
# - Ton: professionell, präzise, optimistisch; aktivierend statt belehrend.
# - Zielgruppe: KMU/Freiberufler in DE; EU‑DSGVO und EU AI Act beachten.
# - Sprache: deutsch; klare Struktur, kurze Absätze, sprechende Zwischenüberschriften.
# - Keine Halluzinationen: Fakten nur mit Quelle (Titel, Domain, Datum „Stand: …“).

## Struktur des Reports
1. Executive Summary (max. 8 Sätze; Kernerkenntnisse, ROI/Payback, Risiken Top‑3)
2. Readiness‑Score & Δ‑Analyse (Säulen: Strategie, Daten, Prozesse, Compliance)
3. Benchmarks (Branche × Größe) mit Mini‑Sparklines (Tendenzen der letzten 12‑24 Monate)
4. Risiken & Regulatorik (DSGVO, EU AI Act – Pflichten je Risikoklasse; rechtliche Stolpersteine)
5. Quick Wins (90 Tage) & Roadmap (12 Monate) – je Maßnahme: KPI, Aufwand, Impact, Owner
6. Tool‑Matrix (Self‑Hosting, EU‑Residency, Audit‑Logs, SAML/SCIM, DPA‑Link)
7. Förderung (Bund/Land) – programmatisch & Baseline, „Stand: [Datum]“
8. Anhang: Quellen, Glossar, Methodik (Prompt-/Schema‑Version)

## Berechnung & Darstellung
- Score 0–100 je Säule; Δ = Ziel − Ist je Säule; ROI-Baseline ≤ 4 Monate.
- Zeige Ampeln (grün/gelb/rot) pro Risiko und Reifegrad.
- Nutze Inline‑SVG für Sparklines; keine externen Skripte (PDF‑Sicherheit).

## Live‑Recherche (Hybrid)
- Primär: Perplexity Search API (ohne `model`), sekundär: Tavily.
- Dedupe, Domain‑Whitelist (europa.eu, foerderdatenbank.de, bmwk.de, …), Backoff bei 429/5xx.
- Jede Quelle erhält ein Badge (Domain) und „Stand: [Datum]“ im Footer.

## Stil
- Vermeide Jargon, schreibe konkret, aktiv, mit Nutzenfokus.
- Nutze Beispiele und Mini‑Cases, wenn hilfreich; keine überlangen Listen.

## Output
- Vollständiges **valides HTML** (UTF‑8, responsive, druckfreundlich).
- Kein JavaScript erforderlich; bevorzugt CSS/Inline‑SVG.
