import json
from openai import OpenAI

client = OpenAI()

# Tools & Förderungen aus JSON laden
with open("tools_und_foerderungen.json", "r", encoding="utf-8") as f:
    db = json.load(f)

def build_prompt(data):
    # Tools & Förderungen für GPT als Klartext
    tools_list = ", ".join([t["name"] for t in db["tools"]])
    foerder_list = ", ".join([f["name"] for f in db["foerderungen"]])

    prompt = f"""
Sie sind ein TÜV-zertifizierter KI- und Datenschutzberater für kleine und mittlere Unternehmen, Selbstständige und Freiberufler in Deutschland und der EU.

### Unternehmensdaten
- Unternehmen: {data.get('unternehmen')}
- Ansprechpartner: {data.get('name')}
- E-Mail: {data.get('email')}
- Branche: {data.get('branche')}
- Geplante Maßnahme: {data.get('massnahme')}
- Bereich: {data.get('bereich')}
- Mitarbeiterzahl: {data.get('mitarbeiterzahl')}
- PLZ: {data.get('plz')}

### Antworten auf Fragen zur Datenschutz- und KI-Readiness:
1. Haben Sie technische Maßnahmen (Firewall, Verschlüsselung etc.) umgesetzt? {data.get('frage1')}
2. Gibt es regelmäßige Schulungen zu Datenschutz, KI und rechtlichen Vorgaben? {data.get('frage2')}
3. Haben Sie einen Datenschutzbeauftragten benannt? {data.get('frage3')}
4. Führen Sie Risikoanalysen oder Datenschutz-Folgenabschätzungen durch? {data.get('frage4')}
5. Gibt es Prozesse zur Datenlöschung oder Anonymisierung? {data.get('frage5')}
6. Wissen Mitarbeiter, wie bei Datenschutzverletzungen zu handeln ist? {data.get('frage6')}
7. Werden Betroffenenrechte (Auskunft, Löschung) aktiv umgesetzt? {data.get('frage7')}
8. Gibt es eine Dokumentation der Datenverarbeitungsprozesse? {data.get('frage8')}
9. Existieren Meldepflichten und klar geregelte Abläufe bei Datenschutzvorfällen? {data.get('frage9')}
10. Führen Sie regelmäßige interne Audits zu Datenschutz und KI durch? {data.get('frage10')}

### Folgende Tools & Förderungen stehen prinzipiell zur Verfügung:
Tools: {tools_list}
Förderprogramme: {foerder_list}

---

### Bitte erstellen Sie ausschließlich ein gültiges JSON-Objekt mit folgendem Aufbau:

{{
  "compliance_score": ganze Zahl von 0 bis 10 (10 bedeutet vollständig datenschutz- & KI-ready),
  "badge_level": "Bronze" | "Silber" | "Gold" | "Platin",
  "readiness_analysis": "branchenspezifische Einschätzung, was das Unternehmen behindert und braucht",
  "compliance_analysis": "detaillierte Datenschutz- und Compliance-Bewertung in Sie-Form, inkl. Dringlichkeit",
  "use_case_analysis": "konkrete Empfehlung, wie KI sinnvoll & datenschutzkonform genutzt werden kann",
  "branche_trend": "aktueller Trend in dieser Branche",
  "vision": "individuelle motivierende Zukunftsperspektive inkl. Hinweis auf TÜV-zertifizierte Zusammenarbeit",
  "toolstipps": ["Tool 1", "Tool 2"],
  "foerdertipps": ["Förderprogramm 1", "Förderprogramm 2"],
  "executive_summary": "konkrete Handlungsempfehlungen in Bulletpoints für die nächsten 3, 6, 12 Monate",
  "risiko_haftung": "klare Einschätzung der Risiken & Haftung bei DSGVO- und AI-Act-Verstößen"
}}

### Sprache & Stil
- Formulieren Sie alles professionell, in der Sie-Form, ohne brancheninternen Jargon.
- Keine Links, nur Namen von Tools/Förderprogrammen.
- Keine Floskeln, sondern operativ nützliche Ansätze.
- Geben Sie ausschließlich ein korrektes JSON-Objekt zurück, ohne Kommentare oder erklärenden Text.
"""
    return prompt

def analyze_with_gpt(data):
    text_response = ""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": build_prompt(data)}
            ]
        )
        text_response = response.choices[0].message.content

        # JSON-Teil herausfiltern
        json_start = text_response.find('{')
        json_end = text_response.rfind('}') + 1
        json_str = text_response[json_start:json_end]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {
                "error": "Konnte JSON nicht parsen",
                "raw": text_response
            }

    except Exception as e:
        return {
            "error": f"Fehler beim GPT-Aufruf: {str(e)}",
            "raw": text_response
        }
