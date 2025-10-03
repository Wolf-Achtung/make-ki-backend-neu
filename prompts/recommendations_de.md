<!-- File: prompts/recommendations_de.md -->
**Aufgabe:** Leite **3 priorisierte Empfehlungen (ROI‑basiert)** ab aus:
- **{{business_case_json}}** (strukturierte Zahlenbasis)
- **{{NEWS_HTML}}** (relevante, zitierfähige Quellen)

**Regeln**
- Nur Aussagen nutzen, die aus den obigen Quellen ableitbar sind; keine Halluzinationen.
- ROI/Payback **nur nennen**, wenn im Business Case vorhanden (sonst „n/a“).
- Priorisierung: **Impact × Machbarkeit** (hoch → niedrig).

**Ausgabeformat (genau)**
1. **Tabelle (Markdown)** mit Spalten: `# | Empfehlung | Erster Schritt (0–14 Tage) | KPI | Abhängigkeiten | ROI/Payback`.
2. Darunter 1 Satz „Begründung der Priorisierung“.

**Schlusszeile:** `Stand: {{date}}`
