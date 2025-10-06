# GUARD
- Antworte ausschließlich auf Deutsch.
- Gib nur ein HTML-Fragment zurück (ohne <html>, <head>, <body>).
- Keine Platzhalter, Templates, Pseudocode oder Klammern wie {...} oder {{...}} im Output.
- Erlaube nur: <h4>, <h5>, <p>, <ul>, <ol>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <em>, <strong>, <code>. Keine Code-Fences.

# KONTEXT
- BRIEFING (JSON): {{BRIEFING_JSON}}
- SCORE (JSON): {{SCORING_JSON}}
- BENCHMARKS (JSON): {{BENCHMARKS_JSON}}

# PINS
- Berücksichtige immer Branche, Unternehmensgröße und Hauptleistung sowie alle Freitextfelder (z. B. ki_projekte, ki_potenzial, strategische_ziele, moonshot).
- Nutze Alias-Fallbacks (DE/EN), falls Felder anders benannt sind (siehe oben).

# AUFGABE
Erstelle eine prägnante <h4>Executive Summary</h4> mit:
- <h5>Kernaussagen</h5> (genau 5 <li>): wichtigste Erkenntnisse, klar geschäftsorientiert.
- <h5>Was jetzt wichtig ist (0–14 Tage)</h5> (3–4 umsetzbare Schritte mit Ergebnisbezug).
- Sprich konkrete Chancen/Risiken an, abgestimmt auf Branche, Größe und Hauptleistung.
