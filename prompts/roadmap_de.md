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
- {% if kpi_roi_months <= 90 %}✓ BREAK-EVEN ERREICHT{% endif %}

## PHASE 3: Integration (91-180 Tage)
- Budget: 35% (= {{ (roi_investment * 0.35)|round }} EUR)
- Fokus: Prozess-Integration
- 3 Meilensteine
- 2 KPIs mit Zielwert
- {% if kpi_roi_months > 90 and kpi_roi_months <= 180 %}✓ BREAK-EVEN{% endif %}

## PHASE 4: Innovation (180+ Tage)
- Budget: 15% (= {{ (roi_investment * 0.15)|round }} EUR)
- Fokus: Neue Use Cases
- 3 Meilensteine
- 2 KPIs
- {% if kpi_roi_months > 180 %}✓ BREAK-EVEN{% endif %}

# Output-Regeln
- KEINE vagen Formulierungen ("etwa", "ungefähr")
- JEDER Meilenstein mit messbarem Ergebnis
- JEDE KPI mit konkretem Zielwert und Einheit