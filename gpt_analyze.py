import os
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
import re

client = OpenAI()

# --- 1. Branchenspezifisches Prompt-Loader ---
def load_prompt(branche, abschnitt):
    path = os.path.join("prompts", branche, f"{abschnitt}.md")
    if not os.path.exists(path):
        path = os.path.join("prompts", "default", f"{abschnitt}.md")
    with open(path, encoding="utf-8") as f:
        return f.read()

# --- 2. Benchmark-Loader (Value-Keys!) ---
def load_benchmark(branche):
    fn = f"benchmark_{branche}.csv"
    path = os.path.join("data", fn)
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path)
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Benchmark-Loading Error: {e}")
        return []

# --- 3. Markdown-/Checklisten-Loader ---
def read_markdown_file(filename):
    path = os.path.join("data", filename)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Fehler beim Lesen von {path}: {e}")
        return ""

# --- 4. Tools & Förderungen-Loader (JSON) ---
def load_tools_und_foerderungen():
    path = "tools_und_foerderungen.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Fehler beim Lesen von {path}: {e}")
        return {}

TOOLS_FOERDER = load_tools_und_foerderungen()

# --- 5. Prompt-Builder ---
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

# --- 6. Tools & Förderungen für Prompt ---
def get_tools_und_foerderungen(data):
    groesse = data.get("unternehmensgroesse", "").lower()
    branche = data.get("branche", "").lower()
    tools_text = "Keine spezifischen Tools gefunden."
    foerder_text = "Keine Förderprogramme gefunden."

    # ---- TOOLS LOGIK ----
    tools_data = TOOLS_FOERDER.get(branche, {}) or TOOLS_FOERDER.get("default", {})
    tools_list = []
    if isinstance(tools_data, dict):
        if groesse in tools_data:
            tools_list.extend(tools_data[groesse])
        if "solo" in tools_data and groesse != "solo":
            tools_list.extend(tools_data["solo"])
        if branche != "default" and TOOLS_FOERDER.get("default", {}).get(groesse):
            tools_list.extend(TOOLS_FOERDER["default"][groesse])
    if tools_list:
        tools_text = "\n".join([f"- [{t['name']}]({t['link']})" for t in tools_list])

    # ---- FÖRDERUNGEN LOGIK ----
    foerderungen = TOOLS_FOERDER.get("foerderungen", {})
    foerder_list = []

    if branche in foerderungen and isinstance(foerderungen[branche], dict):
        for key, value in foerderungen[branche].items():
            if isinstance(value, list):
                foerder_list.extend(value)

    if branche in foerderungen and isinstance(foerderungen[branche], dict):
        national_branch = foerderungen[branche].get("national", [])
        if isinstance(national_branch, list):
            foerder_list.extend(national_branch)

    if "default" in foerderungen and "national" in foerderungen["default"]:
        default_national = foerderungen["default"]["national"]
        if isinstance(default_national, list):
            foerder_list.extend(default_national)

    if "national" in foerderungen and isinstance(foerderungen["national"], list):
        foerder_list.extend(foerderungen["national"])
    elif "national" in foerderungen and isinstance(foerderungen["national"], dict):
        for v in foerderungen["national"].values():
            if isinstance(v, list):
                foerder_list.extend(v)

    unique = {}
    for f in foerder_list:
        key = (f.get("name", ""), f.get("link", ""))
        if key not in unique:
            unique[key] = f
    foerder_list = list(unique.values())

    if foerder_list:
        foerder_text = "\n".join([f"- [{f['name']}]({f['link']})" for f in foerder_list])

    return tools_text, foerder_text

# --- 7. GPT-Block ---
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

# --- 8. Analyse für alle Abschnitte ---
def analyze_full_report(data):
    print("### DEBUG: analyze_full_report AUFGERUFEN ###")
    branche = data.get("branche", "default").strip()
    groesse = data.get("unternehmensgroesse", "kmu").strip()

    benchmark = load_benchmark(branche)
    check_readiness = read_markdown_file("check_ki_readiness.md")
    check_compliance = read_markdown_file("check_compliance_eu_ai_act.md")
    check_inno = read_markdown_file("check_innovationspotenzial.md")
    check_datenschutz = read_markdown_file("check_datenschutz.md")
    check_roadmap = read_markdown_file("check_umsetzungsplan_ki.md")
    praxisbeispiele = read_markdown_file("praxisbeispiele.md")
    tools = read_markdown_file("tools.md")

    abschnitte = [
        ("executive_summary", check_readiness),
        ("gesamtstrategie", check_readiness),
        ("compliance", check_compliance),
        ("innovation", check_inno),
        ("datenschutz", check_datenschutz),
        ("roadmap", check_roadmap),
        ("praxisbeispiele", praxisbeispiele),
        ("tools", tools),
        ("foerderprogramme", ""),  # ggf. individuell befüllt
        ("moonshot_vision", ""),
        ("eu_ai_act", check_compliance),
    ]

    with ThreadPoolExecutor() as pool:
        futures = {
            abschnitt: pool.submit(
                gpt_block, data, abschnitt, branche, groesse, checklisten, benchmark
            )
            for abschnitt, checklisten in abschnitte
        }
        results = {k: f.result() for k, f in futures.items()}

    # Score-Berechnung debuggen!
    print("### DEBUG: calc_score_percent(data) wird ausgeführt ###")
    results["score_percent"] = calc_score_percent(data)
    print("### DEBUG: score_percent gesetzt:", results["score_percent"])
    return results

# --- 9. SWOT-Extractor ---
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

# --- 10. KI-Readiness Score Minimalberechnung ---
def calc_score_percent(data):
    print("### DEBUG: calc_score_percent AUFGERUFEN mit:", data)
    score = 0
    max_score = 35  # Summe aller Teilpunkte

    try:
        score += int(data.get("digitalisierungsgrad", 1))
    except Exception:
        score += 1

    autogr = data.get("automatisierungsgrad", "")
    auto_map = {
        "sehr_niedrig": 0,
        "eher_niedrig": 1,
        "mittel": 3,
        "eher_hoch": 4,
        "sehr_hoch": 5
    }
    score += auto_map.get(autogr, 0)

    papierlos = data.get("prozesse_papierlos", "0-20")
    pap_map = {
        "0-20": 1,
        "21-50": 2,
        "51-80": 4,
        "81-100": 5
    }
    score += pap_map.get(papierlos, 0)

    ki_knowhow = data.get("ki_knowhow", "keine")
    know_map = {
        "keine": 0,
        "grundkenntnisse": 1,
        "mittel": 3,
        "fortgeschritten": 4,
        "expertenwissen": 5
    }
    score += know_map.get(ki_knowhow, 0)

    try:
        score += int(data.get("risikofreude", 1))
    except Exception:
        score += 1

    percent = int((score / max_score) * 100)
    print("### DEBUG: score_percent berechnet:", percent)
    return percent
