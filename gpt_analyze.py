import json
from openai import OpenAI
client = OpenAI()

# 🔥 Tools & Förderungen laden
with open("tools_und_foerderungen.json") as f:
    tools_data = json.load(f)

def analyze_with_gpt(data):
    """
    Sendet die Felder an GPT und bekommt eine detaillierte, professionelle Standortanalyse zurück.
    """
    print("👉 Eingehende Daten für GPT:", json.dumps(data, indent=2))

    # Neuer, wirtschaftlich, rechtlich und strategisch optimierter Prompt:
    prompt = f"""
Sie sind ein TÜV-zertifizierter, wirtschaftlich orientierter KI- und Digitalstrategie-Berater für kleine und mittlere Unternehmen (KMU), Selbstständige und Freiberufler in Deutschland.

Analysieren Sie die folgende, strukturierte Unternehmens-Selbstauskunft umfassend, individuell und maximal praxisnah. Ihr Ziel ist es, dem Unternehmen einen 7-10-seitigen Executive-Briefing-Report (mindestens 5000 Wörter) zu erstellen – in verständlicher, motivierender Sie-Form.

**Schwerpunkte und Vorgaben:**

1. **Score & Badge-Legende:** Erklären Sie zu Beginn des Berichts alle Scores, Badges und Risikoeinstufungen, damit der Leser sie sofort versteht. Vergleichen Sie den Score des Unternehmens mit dem aktuellen Durchschnitt der jeweiligen Branche und Unternehmensgröße (Schätzung erlaubt).

2. **Executive Summary:** Fassen Sie den Ist-Zustand, die wichtigsten Risiken und größten Chancen in max. 300 Wörtern zusammen.

3. **Unternehmens- und Branchenanalyse:** Analysieren Sie das Geschäftsmodell, die Zielgruppen und die individuelle Stellung im Markt (inkl. Benchmark: „Wie steht Ihr Unternehmen im Vergleich zum Branchendurchschnitt?“).

4. **Digitalisierungs- & KI-Readiness:** Beschreiben und bewerten Sie den Stand der Digitalisierung und die Bereitschaft zur KI-Integration im Detail. Nennen Sie Beispiele und zeigen Sie Optimierungspotenziale auf.

5. **Wettbewerbs- und Innovationsvergleich:** Beurteilen Sie, wie das Unternehmen im Vergleich zu anderen in der Branche dasteht (z. B. durch Skalen, Rankings oder einfache Aussagen wie „im oberen Drittel“). Geben Sie Tipps, um in die Top-Liga der Branche zu kommen.

6. **Compliance- & Risikoanalyse (DSGVO/AI Act):** Analysieren Sie, wie gut das Unternehmen in Sachen Datenschutz, DSGVO und KI-Gesetz aufgestellt ist. Geben Sie eine Ampelbewertung (Rot/Gelb/Grün) und erklären Sie, wo akuter Handlungsbedarf besteht. Nennen Sie konkrete, sofort umsetzbare Maßnahmen.

7. **Chancen & Innovationspotenziale:** Entwickeln Sie mindestens drei spezifische, individuell zugeschnittene Ideen, wie das Unternehmen KI gewinnbringend einsetzen kann (inkl. mindestens einem White-Label-/Produkt- oder Service-Ansatz).

8. **DAN-Vision:** Skizzieren Sie eine visionäre, mutige und disruptive Entwicklung ("Was wäre, wenn Sie KI maximal kreativ und transformativ einsetzen?"). Zeigen Sie auf, wie das Unternehmen sich mit KI komplett neu erfinden oder zum Branchen-Gamechanger werden könnte. Nutzen Sie Ihre volle Kreativität!

9. **Detaillierte Roadmap & Handlungsempfehlungen:** Erstellen Sie einen Schritt-für-Schritt-Plan (quartalsweise oder in Etappen), um Digitalisierung und KI im Unternehmen rechtssicher, effizient und förderfähig einzuführen.

10. **Fördermittel-Check & Finanzierungsoptionen:** Prüfen Sie, welche aktuellen Förderprogramme (z. B. Digital Jetzt, go-digital, BAFA, EU-Förderung) zum Unternehmensprofil passen könnten. Geben Sie eine Einschätzung, wie hoch die Förderquote realistisch ist und listen Sie mindestens zwei konkrete nächste Schritte zur Antragstellung auf.

11. **Tool-Tipps, Best Practices & Fehlerquellen:** Listen Sie geeignete Tools, Partner und Förderstellen tabellarisch auf. Nennen Sie typische Fehler, die Unternehmen der Branche bei KI/Digitalisierung machen – und wie man sie vermeidet.

12. **Abschluss & Motivation:** Fassen Sie das Potenzial zusammen, motivieren Sie den Leser und bieten Sie einen Ausblick ("Ihr individueller KI-Vorsprung – so nutzen Sie ihn jetzt!").

**Rahmenbedingungen:**
- Jeder Abschnitt mindestens 300 Wörter, gern mehr.
- Klare Überschriften/H2-Struktur für jedes Kapitel.
- Verwenden Sie keine Floskeln, sondern geben Sie klare, handlungsorientierte Empfehlungen und Beispiele.
- Schreiben Sie stets verständlich, professionell und motivierend.
- Geben Sie bei jedem Score/Benchmark einen direkten Kontext ("Sie liegen X% über/unter dem Branchendurchschnitt").
- Fügen Sie, wo sinnvoll, Tabellen oder Listen ein.

Antworten Sie ausschließlich im folgenden JSON-Format:
{{
  "score_legend": "...",
  "compliance_score": ...,
  "badge_level": "...",
  "ds_gvo_level": ...,
  "ai_act_level": ...,
  "risk_traffic_light": "...",
  "executive_summary": "...",
  "branchen_und_unternehmensanalyse": "...",
  "readiness_analysis": "...",
  "compliance_analysis": "...",
  "use_case_analysis": "...",
  "branche_trend": "...",
  "wettbewerbsvergleich": "...",
  "foerdermittel_check": "...",
  "roadmap": "...",
  "next_steps": [...],
  "toolstipps": [...],
  "foerdertipps": [...],
  "risiko_und_haftung": "...",
  "dan_vision": "...",
  "abschluss": "..."
}}

Unternehmensdaten:
{json.dumps(data, indent=2)}

Zusätzlich findest du hier eine Liste bekannter Tools und Förderprogramme, die Sie in die Empfehlungen einfließen lassen können:
{json.dumps(tools_data, indent=2)}
    """

    completion = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Du bist ein KI-Berater."},
            {"role": "user", "content": prompt}
        ]
    )

    content = completion.choices[0].message.content
    print("✅ GPT Antwort:", content)

    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("GPT hat kein gültiges JSON geliefert.")

    return result
