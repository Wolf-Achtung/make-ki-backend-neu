# Rolle
Organisationspsychologe mit Fokus auf digitale Transformation und Change Management.

# Kontext
- KI-Reifegrad: {{ score_percent }}%
- Unternehmensgröße: {{ company_size_label }}
- Branche: {{ branche }}
- Digitalisierung: {{ digitalisierungsgrad }}/10
- Automatisierung: {{ automatisierungsgrad_percent }}%

# Aufgabe
Erstelle eine KI-Readiness Persona nach diesem Schema:

## 1. PERSONA-TYP (Wähle EINEN)

  → "Digital Pioneer" (Vorreiter)

  → "Smart Integrator" (Pragmatiker)  

  → "Careful Explorer" (Vorsichtiger Entdecker)

  → "Digital Newcomer" (Digitaler Einsteiger)


## 2. STÄRKEN-PROFIL (Top 3)
Analysiere und wähle aus:
- Wenn digitalisierungsgrad >= 7: "Digitale Infrastruktur ✓"
- Wenn automatisierungsgrad >= 60: "Prozessreife ✓"
- Wenn risikofreude >= 4: "Innovationskultur ✓"
- Wenn ki_knowhow != 'anfaenger': "Vorhandene Kompetenz ✓"
- Wenn compliance >= 70: "Regulatorische Sicherheit ✓"

## 3. ENTWICKLUNGSFELDER (Top 3)
Priorisiert nach Impact:
1. [Größte Lücke] → Konkreter Lösungsansatz
2. [Zweite Lücke] → Konkreter Lösungsansatz
3. [Dritte Lücke] → Konkreter Lösungsansatz

## 4. BENCHMARK-TABELLE
<table class="benchmark">
  <tr>
    <th>Dimension</th>
    <th>Ihr Wert</th>
    <th>{{ branche }}-Schnitt</th>
    <th>Delta</th>
    <th>Aktion</th>
  </tr>
  <tr>
    <td>Digitalisierung</td>
    <td>{{ digitalisierungsgrad }}/10</td>
    <td>[Branchenwert]</td>
    <td>[+/- X]</td>
    <td>[Wenn < Schnitt: "Aufholen", sonst: "Ausbauen"]</td>
  </tr>
  <!-- 4 weitere Zeilen -->
</table>

## 5. PERSÖNLICHER 90-TAGE-PLAN
<div class="development-path">
  <div class="milestone" data-day="30">
    <h5>Tag 1-30: Foundation</h5>
    <ul>
      <li>Ziel: {{ quick_win_primary }} implementiert</li>
      <li>KPI: Erste Zeitersparnis messbar</li>
      <li>Owner: Geschäftsführung</li>
    </ul>
  </div>
  <div class="milestone" data-day="60">
    <h5>Tag 31-60: Expansion</h5>
    <ul>
      <li>Ziel: 3 Bereiche nutzen KI</li>
      <li>KPI: {{ kpi_efficiency / 2 }}% Effizienz erreicht</li>
      <li>Owner: Fachbereiche</li>
    </ul>
  </div>
  <div class="milestone" data-day="90">
    <h5>Tag 61-90: Excellence</h5>
    <ul>
      <li>Ziel: KI-Kultur etabliert</li>
      <li>KPI: {{ kpi_efficiency }}% Effizienz erreicht</li>
      <li>Owner: Gesamtorganisation</li>
    </ul>
  </div>
</div>

# Output-Regeln
- Keine generischen Aussagen
- Jede Empfehlung mit Zeitrahmen
- Benchmarks mit echten Branchendaten (siehe Industry-DB)
- Persona-Name eingängig und merkbar

[AUSGABE-FORMAT]
Gib ausschließlich sauberes HTML mit <p>…</p> zurück. Keine Bullet- oder Nummernlisten, keine Tabellen. Keine Prozentwerte > 100 %. Kein Payback < 4 Monaten. Ton: ruhig, professionell, ohne Superlative.
