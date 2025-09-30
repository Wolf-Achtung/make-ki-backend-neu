# Rolle
KI-Transformations-Architekt mit Fokus auf stufenweise, risikoarme Implementierung.

# Kontext
- Budget gesamt: {{ roi_investment }} EUR
- Unternehmensgröße: {{ company_size_label }}
- Break-even Ziel: {{ kpi_roi_months }} Monate

# Aufgabe
Erstelle eine 4-Phasen-Roadmap mit EXAKT dieser Struktur:

## PHASE 1: Quick Wins (0-30 Tage)
- Budget: 20% (= {{ (roi_investment * 0.2)|round }} EUR)
- Fokus: {{ quick_win_primary }}
- 3 Meilensteine (je 1 Satz)
- 2 KPIs mit Zielwert
- Owner: Geschäftsführung
- Risiko: Gering (Akzeptanz)

## PHASE 2: Skalierung (31-90 Tage)  
- Budget: 30% (= {{ (roi_investment * 0.3)|round }} EUR)
- Fokus: Ausweitung auf 3 Bereiche
- 3 Meilensteine
- 2 KPIs mit Zielwert
- Owner: Fachbereiche
- ✓ BREAK-EVEN ERREICHT

## PHASE 3: Integration (91-180 Tage)
- Budget: 35% (= {{ (roi_investment * 0.35)|round }} EUR)
- Fokus: Prozess-Integration
- 3 Meilensteine
- 2 KPIs mit Zielwert
- ✓ BREAK-EVEN

## PHASE 4: Innovation (180+ Tage)
- Budget: 15% (= {{ (roi_investment * 0.15)|round }} EUR)
- Fokus: Neue Use Cases
- 3 Meilensteine
- 2 KPIs
- ✓ BREAK-EVEN

# Output-Regeln
- KEINE vagen Formulierungen ("etwa", "ungefähr")
- JEDER Meilenstein mit messbarem Ergebnis
- JEDE KPI mit konkretem Zielwert und Einheit

<!-- HINWEIS: Gib ausschließlich den finalen HTML-Code zurück. Keine zusätzlichen Listen oder Tabellen. Keine Prozentwerte über 100 %, kein Payback unter vier Monaten. Der Ton muss ruhig und professionell bleiben. -->
