import os
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

client = OpenAI()

# ---------------------------------------------------------
# 1. Hilfsfunktion: Benchmark für die Branche laden
# ---------------------------------------------------------
def load_benchmark(branch):
    """
    Lädt die passende Benchmark-CSV für die übergebene Branche.
    Gibt eine Liste von Dicts zurück.
    """
    # Dateinamen nach deinem Namensschema
    branch_map = {
        "Marketing & Werbung": "benchmark_marketing.csv",
        "Beratung & Dienstleistungen": "benchmark_beratung.csv",
        "IT & Software": "benchmark_it.csv",
        "Finanzen & Versicherungen": "benchmark_finanzen.csv"
    }
    fn = branch_map.get(branch, None)
    if not fn:
        return []
    path = os.path.join("data", fn)
    try:
        df = pd.read_csv(path)
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Benchmark-Loading Error: {e}")
        return []

# ---------------------------------------------------------
# 2. Hilfsfunktion: Checklisten/Markdown laden
# ---------------------------------------------------------
def read_markdown_file(filename):
    path = os.path.join("data", filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Fehler beim Lesen von {path}: {e}")
        return ""

# ---------------------------------------------------------
# 3. Prompt-Template je Analysebereich (vereinfacht, editierbar!)
# ---------------------------------------------------------
PROMPT_TEMPLATES = {
    "Executive Summary": (
        "Erstelle eine prägnante, verständliche Executive Summary zur digitalen Reife, KI-Readiness und "
        "Regulatorik auf Basis der folgenden Daten. Gehe auf besondere Stärken und Schwächen ein und vergleiche "
        "mit dem typischen Branchendurchschnitt, wenn möglich."
    ),
    "Strategie": (
        "Analysiere die Digital- und KI-Strategie dieses Unternehmens. Erkenne Chancen, Schwächen und Handlungsfelder. "
        "Beziehe die Branchenbenchmarks und typische Best Practices ein."
    ),
    "Compliance": (
        "Bewerte die Compliance-Strategie des Unternehmens (DSGVO, EU AI Act, interne Meldewege, Datenschutz etc.) "
        "und gib konkrete Empfehlungen für kritische Lücken."
    ),
    "Innovation": (
        "Analysiere das Innovationspotenzial, die bisherigen KI-Einsatzbereiche und die wichtigsten Zukunftschancen. "
        "Gib eine SWOT-Analyse und priorisiere Quick Wins."
    ),
    # ... beliebig erweiterbar für weitere Bereiche ...
}

# ---------------------------------------------------------
# 4. Promptbuilder: Pro Bereich den Kontext maßschneidern
# ---------------------------------------------------------
def build_prompt(data, topic, branch, size, checklisten=None, benchmark=None):
    base = PROMPT_TEMPLATES.get(topic, "")
    bench_txt = ""
    if benchmark:
        # Kompakte Benchmark-Tabelleninfo als String bauen:
        bench_txt = "Branchen-Benchmark:\n" + "\n".join(
            f"- {row['Kategorie']}: {row['Wert_Durchschnitt']} ({row['Kurzbeschreibung']})"
            for row in benchmark
        )
    prompt = (
        f"{base}\n"
        f"Branche: {branch}\n"
        f"Unternehmensgröße: {size}\n"
        f"Userdaten:\n{json.dumps(data, indent=2)}\n"
        f"{bench_txt}\n"
        f"Checkliste:\n{checklisten or ''}\n"
        "\nStrukturiere die Antwort in: Analyse, Benchmark-Vergleich, Empfehlungen, SWOT.\n"
        "Gib die SWOT als Liste zurück (Stärken, Schwächen, Chancen, Risiken)."
    )
    return prompt

# ---------------------------------------------------------
# 5. GPT-Aufruf (gpt-4o)
# ---------------------------------------------------------
def gpt_block(data, topic, branch, size, checklisten=None, benchmark=None):
    prompt = build_prompt(data, topic, branch, size, checklisten, benchmark)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein TÜV-zertifizierter KI-Manager, KI-Strategieberater und Datenschutz-Experte. "
                    "Du analysierst, bewertest und empfiehlst ausschließlich nach europäischen Best Practices, "
                    "unter besonderer Berücksichtigung von Mittelstand, KMU und regulatorischer Sicherheit."
                )
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        request_timeout=120
    )
    return response.choices[0].message.content.strip()

# ---------------------------------------------------------
# 6. Parallele Analyse: Alle Abschnitte in Threads ausführen
# ---------------------------------------------------------
def analyze_full_report(data):
    branch = data.get("branche", "Sonstige").strip()
    size = data.get("unternehmensgroesse", "KMU").strip()

    benchmark = load_benchmark(branch)
    check_readiness = read_markdown_file("check_ki_readiness.md")
    check_compliance = read_markdown_file("check_compliance_eu_ai_act.md")
    check_inno = read_markdown_file("check_innovationspotenzial.md")
    # ... weitere Checklisten nach Bedarf ...

    # GPT-Aufrufe parallelisieren
    with ThreadPoolExecutor() as pool:
        futures = {
            "summary": pool.submit(gpt_block, data, "Executive Summary", branch, size, check_readiness, benchmark),
            "strategie": pool.submit(gpt_block, data, "Strategie", branch, size, check_readiness, benchmark),
            "compliance": pool.submit(gpt_block, data, "Compliance", branch, size, check_compliance, benchmark),
            "innovation": pool.submit(gpt_block, data, "Innovation", branch, size, check_inno, benchmark),
            # weitere Bereiche (roadmap, förderung, etc.) analog
        }
        results = {k: f.result() for k, f in futures.items()}

    # Hier könntest du Score, SWOT-Extract usw. ergänzen
    return results

# ---------------------------------------------------------
# 7. SWOT-Extractor als Option (z.B. für Innovation)
# ---------------------------------------------------------
import re
def extract_swot(full_text):
    def find(pattern):
        m = re.search(pattern, full_text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""
    return {
        "swot_strengths": find(r"Stärken:(.*?)(?:Schwächen:|Chancen:|Risiken:|$)"),
        "swot_weaknesses": find(r"Schwächen:(.*?)(?:Chancen:|Risiken:|$)"),
        "swot_opportunities": find(r"Chancen:(.*?)(?:Risiken:|$)"),
        "swot_threats": find(r"Risiken:(.*?)(?:$)"),
    }

