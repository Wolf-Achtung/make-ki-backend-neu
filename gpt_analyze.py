import os
import json
import pandas as pd
import re
from openai import OpenAI
from datetime import datetime

EU_RISK_TABLE = """
<div class="eu-risk-table" style="margin-bottom:1.2em;">
  <b>Risikokategorien gemäß EU AI Act:</b>
  <table>
    <tr><th>Kategorie</th><th>Beschreibung</th></tr>
    <tr><td>Verboten</td><td>KI-Systeme mit Sozialem Scoring, manipulativer oder verdeckter Steuerung</td></tr>
    <tr><td>Hochrisiko</td><td>KI in kritischen Infrastrukturen, Gesundheit, Justiz, HR, Sicherheit, etc.</td></tr>
    <tr><td>Begrenztes Risiko</td><td>z. B. Chatbots, Empfehlungssysteme (mit Transparenzpflichten)</td></tr>
    <tr><td>Minimales Risiko</td><td>z. B. Spamfilter, Games</td></tr>
  </table>
</div>
"""

# Simple helper to convert checklist Markdown to basic HTML lists. This avoids a heavy markdown dependency.
def checklist_markdown_to_html(md_text: str) -> str:
    """
    Convert a simple checklist Markdown (with '- [ ]' or '- ') into a HTML unordered list.
    Headings starting with '#' will be converted into <h3> tags. Lines that do not start
    with a list marker or heading are ignored. This helper is intentionally simple and
    tailored to our checklist files.
    """
    html_lines = []
    lines = md_text.splitlines()
    ul_open = False
    for line in lines:
        striped = line.strip()
        if not striped:
            continue
        # Headings
        if striped.startswith("#"):
            if ul_open:
                html_lines.append("</ul>")
                ul_open = False
            # remove leading hashes
            heading = striped.lstrip('#').strip()
            html_lines.append(f"<h3>{heading}</h3>")
            continue
        # Bullet items
        if striped.startswith("- [ ]"):
            item = striped[5:].strip()
        elif striped.startswith("- "):
            item = striped[2:].strip()
        else:
            # ignore other lines
            continue
        if not ul_open:
            html_lines.append("<ul>")
            ul_open = True
        html_lines.append(f"<li>{item}</li>")
    if ul_open:
        html_lines.append("</ul>")
    return "\n".join(html_lines)

client = OpenAI()

# --- 1. Branchenspezifisches Prompt-Loader ---

def load_prompt(branche, abschnitt, context_vars=None):
    with open("prompts/prompt_prefix.md", encoding="utf-8") as f:
        prefix = f.read()
    path = os.path.join("prompts", branche, f"{abschnitt}.md")
    if not os.path.exists(path):
        path = os.path.join("prompts", "default", f"{abschnitt}.md")
    with open(path, encoding="utf-8") as f:
        main_prompt = f.read()
    with open("prompts/prompt_suffix.md", encoding="utf-8") as f:
        suffix = f.read()
    vars = context_vars.copy() if context_vars else {}
    vars.setdefault("datum", datetime.now().strftime("%d.%m.%Y"))
    prompt = f"{prefix}\n\n{main_prompt}\n\n{suffix}"
    prompt = prompt.format(**vars)
    return prompt

# --- 2. Benchmark-Loader ---
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
    bench_txt = ""
    if benchmark:
        bench_txt = "\nBranchen-Benchmark:\n" + "\n".join(
            f"- {row.get('Kategorie', '')}: {row.get('Wert_Durchschnitt', '')} ({row.get('Kurzbeschreibung', '')})"
            for row in benchmark
        )

    # Kombiniere Tools und Förderprogramme für die Variable tools_und_foerderungen.
    kombi_tools_foerder = ""
    if tools_text and foerder_text:
        kombi_tools_foerder = f"{tools_text}\n{foerder_text}"
    elif tools_text:
        kombi_tools_foerder = tools_text
    elif foerder_text:
        kombi_tools_foerder = foerder_text

    prompt_vars = {
        "branche": branche,
        "hauptleistung": data.get("hauptleistung", ""),
        "unternehmensgroesse": groesse,
        "selbststaendig": data.get("selbststaendig", ""),
        "daten": json.dumps(data, indent=2, ensure_ascii=False),
        "checklisten": checklisten or "",
        "benchmark": bench_txt,
        # separate Tools und Förderlisten für legacy Prompts
        "tools": tools_text or "",
        # kombiniertes Feld enthält sowohl Tool- als auch Förderprogramme
        "tools_und_foerderungen": kombi_tools_foerder or "",
        "foerderungen": foerder_text or "",
        "praxisbeispiele": "",
        "score_percent": data.get("score_percent", ""),
        "hinweis_html_tabellen": (
            "Wichtig: Wenn strukturierte Inhalte wie Tabellen nötig sind, geben Sie diese ausschließlich "
            "in validem HTML-Format (<table>, <tr>, <td>) aus – kein Markdown oder Codeblock."
        ),
        **data
    }

    prompt = load_prompt(branche, abschnitt, prompt_vars)
    return prompt

# --- 6. Tools & Förderungen für Prompt ---
def get_tools_und_foerderungen(data):
    groesse = data.get("unternehmensgroesse", "").lower()
    branche = data.get("branche", "").lower()
    tools_text = "Keine spezifischen Tools gefunden."
    foerder_text = "Keine Förderprogramme gefunden."

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
def gpt_block(data, abschnitt, branche, groesse, checklisten=None, benchmark=None, prior_results=None):
    tools_text, foerder_text = get_tools_und_foerderungen(data)
    prompt = build_prompt(
        data, abschnitt, branche, groesse, checklisten, benchmark, tools_text, foerder_text
    )
    if prior_results:
        prompt += "\n\n[Vorherige Analyse-Ergebnisse als Kontext]:\n"
        prompt += json.dumps(prior_results, indent=2, ensure_ascii=False)
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

# --- 8. Modularer Analyse-Flow ---
def analyze_full_report(data):
    branche = data.get("branche", "default").strip().lower()
    groesse = data.get("unternehmensgroesse", "kmu").strip().lower()

    benchmark = load_benchmark(branche)
    check_readiness = read_markdown_file("check_ki_readiness.md")
    check_compliance = read_markdown_file("check_compliance_eu_ai_act.md")
    check_inno = read_markdown_file("check_innovationspotenzial.md")
    check_datenschutz = read_markdown_file("check_datenschutz.md")
    check_roadmap = read_markdown_file("check_umsetzungsplan_ki.md")
    praxisbeispiele_md = read_markdown_file("praxisbeispiele.md")

    # Definiere die Reihenfolge der GPT-Abschnitte. Zusammenfassungen werden für alle Unternehmensgrößen generiert, um die PDF-Templates bedienen zu können.
    abschnittsreihenfolge = [
        ("score_percent", None),
        ("executive_summary", check_readiness),
        ("gesamtstrategie", check_readiness),
        ("summary_klein", check_readiness),
        ("summary_kmu", check_readiness),
        ("summary_solo", check_readiness),
        ("innovation", check_inno),
        ("compliance", check_compliance),
        ("datenschutz", check_datenschutz),
        ("roadmap", check_roadmap),
        ("praxisbeispiele", praxisbeispiele_md),
        ("moonshot_vision", ""),
        ("eu_ai_act", check_compliance),
    ]

    results = {}
    prior_results = {}
for abschnitt, checklisten in abschnittsreihenfolge:
    try:
        if abschnitt == "score_percent":
            percent = calc_score_percent(data)
            results["score_percent"] = percent
            prior_results["score_percent"] = percent
            data["score_percent"] = percent
            print(f"### DEBUG: score_percent berechnet: {percent}")
            continue
        text = gpt_block(
            data, abschnitt, branche, groesse, checklisten, benchmark, prior_results
        )
        text = fix_encoding(text)
        if abschnitt == "compliance":
            results[abschnitt] = EU_RISK_TABLE + "\n" + text
        else:
            results[abschnitt] = text
        prior_results[abschnitt] = results[abschnitt]
    except Exception as e:
        print(f"Fehler in Abschnitt {abschnitt}: {e}")
        results[abschnitt] = f"[Fehler: {e}]"
        prior_results[abschnitt] = f"[Fehler: {e}]"


    # Tools und Förderprogramme separat ermitteln und in die Ergebnisse einfügen. Diese werden nicht von GPT generiert, um stabile und aktuelle Inhalte zu gewährleisten.
    tools_text, foerder_text = get_tools_und_foerderungen(data)
    results["tools"] = tools_text or "Keine spezifischen Tools gefunden."
    results["foerderprogramme"] = foerder_text or "Keine Förderprogramme gefunden."

    # --- Checklisten-Integration, Gold-Standard ---
# Strukturiert: Jede Checkliste als eigene Box mit Überschrift und Checkboxen

checklist_map = [
    ("KI‑Readiness‑Check", "check_ki_readiness.md"),
    ("Compliance‑Check (EU AI Act & DSGVO)", "check_compliance_eu_ai_act.md"),
    ("Innovationspotenzial‑Check", "check_innovationspotenzial.md"),
    ("Datenschutz‑Check", "check_datenschutz.md"),
    ("Fördermittel‑Check", "check_foerdermittel.md"),
    ("KI‑Umsetzungsplan", "check_umsetzungsplan_ki.md"),
]

checklists_html = ""
for title, cl_file in checklist_map:
    md = read_markdown_file(cl_file)
    if md and md.strip():
        html = checklist_markdown_to_html(md)
        checklists_html += f'<div class="checklist-box"><h3>{title}</h3>{html}</div>\n'

results["checklisten"] = checklists_html.strip() if checklists_html.strip() else ""

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
    print("### DEBUG: calc_score_percent(data) wird ausgeführt ###")
    score = 0
    max_score = 35

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
    print(f"### DEBUG: calc_score_percent AUFGERUFEN mit: {data}")
    print(f"### DEBUG: score_percent gesetzt: {percent}")
    return percent

def fix_encoding(text):
    return (
        text.replace("�", "-")
            .replace("–", "-")
            .replace("“", "\"")
            .replace("”", "\"")
            .replace("’", "'")
    )
