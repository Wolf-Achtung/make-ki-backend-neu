import os
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
import re

client = OpenAI()

# ---------------------------------------------------------
# 1. Prompt-Loader: Holt branchenspezifisches oder Default-Prompt
# ---------------------------------------------------------
def load_prompt(branche, abschnitt):
    bn = branche.lower().replace("&", "und").replace(" ", "")
    path = os.path.join("prompts", bn, f"{abschnitt}.md")
    if not os.path.exists(path):
        path = os.path.join("prompts", "default", f"{abschnitt}.md")
    with open(path, encoding="utf-8") as f:
        return f.read()

# ---------------------------------------------------------
# 2. Benchmark-Loader: Holt die richtige Benchmark-Tabelle
# ---------------------------------------------------------
def load_benchmark(branche):
    branch_map = {
        "Marketing & Werbung": "benchmark_marketing.csv",
        "Beratung & Dienstleistungen": "benchmark_beratung.csv",
        "IT & Software": "benchmark_it.csv",
        "Finanzen & Versicherungen": "benchmark_finanzen.csv",
        "Handel & E-Commerce": "benchmark_handel.csv",
        "Bildung": "benchmark_bildung.csv",
        "Verwaltung": "benchmark_verwaltung.csv",
    }
    fn = branch_map.get(branche, None)
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
# 3. Markdown-/Checklisten-Loader
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
# 4. Tools & Förderungen-Loader (JSON)
# ---------------------------------------------------------
def load_tools_und_foerderungen():
    path = "tools_und_foerderungen.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Fehler beim Lesen von {path}: {e}")
        return {"tools": {}, "foerderungen": {}}

TOOLS_FOERDER = load_tools_und_foerderungen()

# ---------------------------------------------------------
# 5. Prompt-Builder (setzt alles zusammen)
# ---------------------------------------------------------
def build_prompt(data, abschnitt, branche, groesse, checklisten=None, benchmark=None, tools_text="", foerder_text=""):
    prompt_raw = load_prompt(branche, abschnitt)
    bench_txt = ""
    if benchmark:
        bench_txt = "\nBranchen-Benchmark:\n" + "\n".join(
            f"- {row.get('Kategorie', '')}: {row.get('Wert_Durchschnitt', '')} ({row.get('Kurzbeschreibung', '')})"
            for row in benchmark
        )
    prompt = prompt_raw.format(
        branche=branche,
        unternehmensgroesse=groesse,
        daten=json.dumps(data, indent=2),
        checklisten=checklisten or "",
        benchmark=bench_txt,
        tools=tools_text,
        foerderungen=foerder_text,
    )
    return prompt

# ---------------------------------------------------------
# 6. Tools & Förderungen für Prompt aufbereiten
# ---------------------------------------------------------
def get_tools_und_foerderungen(data):
    groesse = data.get("unternehmensgroesse", "").lower()
    # Tools nach Größe (vereinfacht, je nach Struktur in deiner JSON ggf. anpassen!)
    if "1" in groesse or "solo" in groesse or "klein" in groesse:
        tools_list = TOOLS_FOERDER.get("tools", {}).get("kleinere", [])
    else:
        tools_list = TOOLS_FOERDER.get("tools", {}).get("groessere", [])
    tools_text = "\n".join([f"- [{t['name']}]({t['link']})" for t in tools_list]) if tools_list else "Keine spezifischen Tools gefunden."

    # Förderprogramme (kannst du nach Bundesland/Branche aufteilen, hier einfach national)
    foerder_list = TOOLS_FOERDER.get("foerderungen", {}).get("national", [])
    foerder_text = "\n".join([f"- [{f['name']}]({f['link']})" for f in foerder_list]) if foerder_list else "Keine Förderprogramme gefunden."
    return tools_text, foerder_text

# ---------------------------------------------------------
# 7. GPT-Aufruf (gpt-4o)
# ---------------------------------------------------------
def gpt_block(data, abschnitt, branche, groesse, checklisten=None, benchmark=None):
    tools_text, foerder_text = get_tools_und_foerderungen(data)
    prompt = build_prompt(data, abschnitt, branche, groesse, checklisten, benchmark, tools_text, foerder_text)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist ein TÜV-zertifizierter KI-Manager, KI-Strategieberater und Datenschutz-Experte. "
                    "Deine Empfehlungen sind stets aktuell, rechtssicher und praxisorientiert für den Mittelstand, "
                    "unter besonderer Berücksichtigung von DSGVO, EU AI Act und Markt-Benchmarks."
                )
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()

# ---------------------------------------------------------
# 8. Parallele Analyse für alle Abschnitte
# ---------------------------------------------------------
def analyze_full_report(data):
    branche = data.get("branche", "Sonstige").strip()
    groesse = data.get("unternehmensgroesse", "KMU").strip()

    benchmark = load_benchmark(branche)
    check_readiness = read_markdown_file("check_ki_readiness.md")
    check_compliance = read_markdown_file("check_compliance_eu_ai_act.md")
    check_inno = read_markdown_file("check_innovationspotenzial.md")
    check_datenschutz = read_markdown_file("check_datenschutz.md")
    check_roadmap = read_markdown_file("check_umsetzungsplan_ki.md")
    praxisbeispiele = read_markdown_file("praxisbeispiele.md")
    tools = read_markdown_file("tools.md")
    # ... weitere Checklisten nach Bedarf ...

    abschnitte = [
        ("ExecutiveSummary", check_readiness),
        ("Strategie", check_readiness),
        ("Compliance", check_compliance),
        ("Innovation", check_inno),
        ("Datenschutz", check_datenschutz),
        ("Roadmap", check_roadmap),
        ("Praxisbeispiele", praxisbeispiele),
        ("Tools", tools),
    ]

    with ThreadPoolExecutor() as pool:
        futures = {
            abschnitt: pool.submit(
                gpt_block, data, abschnitt, branche, groesse, checklisten, benchmark
            )
            for abschnitt, checklisten in abschnitte
        }
        results = {k: f.result() for k, f in futures.items()}

    return results

# ---------------------------------------------------------
# 9. SWOT-Extractor (optional)
# ---------------------------------------------------------
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
