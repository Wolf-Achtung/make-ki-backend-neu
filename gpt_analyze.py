# gpt_analyze.py — Teil 1/4
import os
import re
import json
import base64
import zipfile
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional, List

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openai import OpenAI

client = OpenAI()

# ---------- optionale Domain-Bausteine ----------
try:
    from gamechanger_blocks import build_gamechanger_blocks
    from gamechanger_features import GAMECHANGER_FEATURES
    from innovation_intro import INNOVATION_INTRO
except Exception:
    build_gamechanger_blocks = lambda data, feats: []
    GAMECHANGER_FEATURES = {}
    INNOVATION_INTRO = {}

try:
    from websearch_utils import serpapi_search
except Exception:
    serpapi_search = lambda query, num_results=5: []

# ---------- ZIP-Autounpack (Prompts/Kontexte/Daten) ----------
def ensure_unzipped(zip_name: str, dest_dir: str):
    try:
        if os.path.exists(zip_name) and not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            with zipfile.ZipFile(zip_name, "r") as zf:
                zf.extractall(dest_dir)
    except Exception:
        pass

ensure_unzipped("prompts.zip", "prompts_unzip")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")

# ---------- kleine Helfer ----------
def _as_int(x):
    try:
        return int(str(x).strip())
    except Exception:
        return None

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").lower().strip()
    return "de" if l.startswith("de") else "en"

def fix_encoding(text: str) -> str:
    return (text or "").replace("�", "-").replace("–", "-").replace("“", '"').replace("”", '"').replace("’", "'")

def strip_code_fences(text: str) -> str:
    """
    Entfernt ```-Fences & Backticks, damit Templates nicht 'leere PDFs' produzieren.
    """
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")

def ensure_html(text: str, lang: str = "de") -> str:
    """
    Wenn kein HTML erkennbar, eine einfache HTML-Struktur aus Markdown-ähnlichem Text erzeugen.
    """
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t
    lines = [ln.rstrip() for ln in t.splitlines() if ln.strip()]
    html = []
    in_ul = False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append("<li>" + re.sub(r"^[-•*]\s+", "", ln).strip() + "</li>")
            continue
        if re.match(r"^#{1,3}\s+", ln):
            level = min(3, max(1, len(ln) - len(ln.lstrip("#"))))
            txt = ln[level:].strip()
            html.append(f"<h{level}>{txt}</h{level}>")
            continue
        if in_ul:
            html.append("</ul>")
            in_ul = False
        html.append("<p>" + ln + "</p>")
    if in_ul:
        html.append("</ul>")
    return "\n".join(html)

def is_self_employed(data: dict) -> bool:
    keys_text = ["beschaeftigungsform", "beschäftigungsform", "arbeitsform", "rolle", "role", "occupation", "unternehmensform", "company_type"]
    txt = " ".join(str(data.get(k, "") or "") for k in keys_text).lower()
    if any(s in txt for s in ["selbst", "freelanc", "solo", "self-employ"]):
        return True
    for k in ["mitarbeiter", "mitarbeiterzahl", "anzahl_mitarbeiter", "employees", "employee_count", "team_size"]:
        n = _as_int(data.get(k))
        if n is not None and n <= 1:
            return True
    return False

def load_yaml(path: str):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
# gpt_analyze.py — Teil 2/4

def build_context(data: dict, branche: str, lang: str = "de") -> dict:
    """
    Lädt Branchenkontext (YAML) + verschmilzt mit Formdaten. Ergänzt hilfreiche Felder.
    """
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path) if os.path.exists(context_path) else {}

    context.update(data or {})
    context["lang"] = lang
    context["branche"] = branche
    context.setdefault("copyright_year", datetime.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")
    context.setdefault("company_size", _as_int(data.get("mitarbeiterzahl") or data.get("employees") or 1) or 1)
    context["is_self_employed"] = is_self_employed(data)

    # häufige Schlüssel als Aliase
    context["hauptleistung"] = context.get("hauptleistung") or context.get("main_service") or context.get("hauptprodukt") or ""
    context["projektziel"] = context.get("projektziel") or context.get("ziel") or ""
    return context

def add_innovation_features(context, branche, data):
    context["branchen_innovations_intro"] = INNOVATION_INTRO.get(branche, "")
    try:
        context["gamechanger_blocks"] = build_gamechanger_blocks(data, GAMECHANGER_FEATURES)
    except Exception:
        context["gamechanger_blocks"] = []
    return context

def add_websearch_links(context, branche, projektziel):
    """
    Optional: SERP-Links für Förderungen & Tools. Keine Pflicht für den Report,
    aber als Referenz/Belege hilfreich.
    """
    year = datetime.now().year
    try:
        context["websearch_links_foerder"] = serpapi_search(
            f"aktuelle Förderprogramme {branche} {projektziel} Deutschland {year}", num_results=5
        )
        context["websearch_links_tools"] = serpapi_search(
            f"aktuelle KI-Tools {branche} Deutschland {year}", num_results=5
        )
    except Exception:
        context["websearch_links_foerder"] = []
        context["websearch_links_tools"] = []
    return context

def render_prompt(template_text: str, context: dict) -> str:
    """
    {{ key }} & {{ list_key | join(', ') }} in Prompt-Templates ersetzen.
    """
    def replace_join(m):
        key = m.group(1)
        sep = m.group(2)
        val = context.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template_text)

    def replace_simple(m):
        key = m.group(1)
        val = context.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, rendered)
    return rendered

def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
    """
    Baut das Kapitelprompt und erzwingt kurze, präzise HTML-Ausgaben.
    """
    search_paths = [
        f"prompts/{lang}/{chapter}.md",
        f"prompts_unzip/{lang}/{chapter}.md",
        f"{lang}/{chapter}.md",
        f"de_unzip/de/{chapter}.md",
        f"en_unzip/en/{chapter}.md",
    ]
    prompt_text = None
    for p in search_paths:
        if os.path.exists(p):
            try:
                prompt_text = load_text(p); break
            except Exception:
                continue
    if prompt_text is None:
        prompt_text = f"[NO PROMPT FOUND for {chapter}/{lang}]"

    prompt = render_prompt(prompt_text, context)
    is_de = (lang == "de")

    base_rules_de = (
        "Gib die Antwort ausschließlich als gültiges HTML ohne <html>-Wrapper zurück. "
        "Nutze nur <h3>, <p>, <ul>, <ol>, <table>. Keine Meta-Kommentare. Schreibe klar und prägnant."
    )
    base_rules_en = (
        "Return VALID HTML only (no <html> wrapper). Use only <h3>, <p>, <ul>, <ol>, <table>. "
        "No meta talk. Be concise and precise."
    )
    style = ("\n\n---\n" + (base_rules_de if is_de else base_rules_en) +
             "\n- Verwende kurze Sätze, vermeide Wiederholungen." if is_de else
             "\n- Use short sentences; avoid repetition.")

    # Kapitel-spezifische Constraints
    if chapter == "executive_summary":
        style += ("\n- Gliedere in: <h3>Was tun?</h3> <ul>…</ul> <h3>Warum?</h3> <p>…</p> "
                  "<h3>Nächste 3 Schritte</h3> <ol>…</ol>" if is_de else
                  "\n- Structure: <h3>What to do?</h3><ul>…</ul><h3>Why?</h3><p>…</p>"
                  "<h3>Next 3 steps</h3><ol>…</ol>")
        style += ("\n- Maximal 5 Bullet-Points pro Liste." if is_de else "\n- Max 5 bullets per list.")

    if chapter == "vision":
        style += ("\n- Form: 1 kühne Idee mit Titel + 1 Satz; 1 MVP (2–4 Wochen, grobe Kosten); "
                  "3 KPIs in <ul>." if is_de else
                  "\n- Form: 1 bold idea (title + one-liner); 1 MVP (2–4 weeks, rough cost); "
                  "3 KPIs in <ul>.")
        style += ("\n- Vermeide Allgemeinplätze; passe auf Branche und Größe an." if is_de else
                  "\n- No genericities; adapt to industry and size.")

    if chapter in ("tools",):
        style += ("\n- Gib eine Tabelle <table> mit Spalten: Name | Usecase | Kosten | Link zurück." if is_de else
                  "\n- Return a <table> with columns: Name | Use case | Cost | Link.")
        style += ("\n- Maximal 7 Zeilen; nur EU/DSGVO-taugliche Tools nennen." if is_de else
                  "\n- Max 7 rows; prefer GDPR/EU-friendly tools.")

    if chapter in ("foerderprogramme", "foerderung", "funding"):
        style += ("\n- Tabelle <table>: Name | Zielgruppe | Förderhöhe | Link. Maximal 5 Zeilen." if is_de else
                  "\n- Table <table>: Name | Target group | Amount | Link. Max 5 rows.")

    # Solo-Selbstständig-Vorgabe
    if context.get("is_self_employed"):
        style += ("\n- Solo-Selbstständig: Empfehlungen skalierbar halten; Förderungen für Einzelunternehmen priorisieren." if is_de else
                  "\n- Solo self-employed: keep recommendations scalable; prioritize funding suitable for individuals.")

    return prompt + style


def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float] = None) -> str:
    """
    Dünne Wrapper für OpenAI Chat Completion. Modell per ENV steuerbar.
    """
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

def gpt_generate_section(data, branche, chapter, lang="de"):
    """
    Baut den Kapitel-Context, holt Prompt & ruft das LLM. Liefert HTML (als Text).
    """
    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    context = build_context(data, branche, lang)
    context = add_innovation_features(context, branche, data)
    context = add_websearch_links(context, branche, context.get("projektziel", ""))

    # Checkliste-Fallback
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                md = f.read()
            ctx_list = [f"<li>{ln[2:].strip()}</li>" for ln in md.splitlines() if ln.strip().startswith("- ")]
            context["checklisten"] = "<ul>" + "\n".join(ctx_list) + "</ul>" if ctx_list else ""
        else:
            context["checklisten"] = ""

    prompt = build_masterprompt(chapter, context, lang)
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model

    section_text = _chat_complete(
        messages=[
            {
                "role": "system",
                "content": (
                    "Du bist TÜV-zertifizierter KI-Manager, KI-Strategieberater, Datenschutz- und Fördermittel-Experte. "
                    "Liefere präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
                    if lang == "de"
                    else "You are a TÜV-certified AI manager and strategy consultant. "
                         "Deliver precise, actionable, up-to-date, sector-relevant content as HTML."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        model_name=model_name,
        temperature=None,
    )
    return section_text

def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    # Konsequente Normalisierung gegen leere/kaputte PDFs
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(strip_code_fences(fix_encoding(html)), lang)
# gpt_analyze.py — Teil 3/4

def build_chart_payload(data: dict, score_percent: int, lang: str = "de") -> dict:
    def as_int(v, d=0):
        try:
            return int(v)
        except Exception:
            return d

    auto_map = {
        "sehr_niedrig": 1, "eher_niedrig": 2, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5,
        "very_low": 1, "rather_low": 2, "medium": 3, "rather_high": 4, "very_high": 5
    }
    pap_map = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5}
    know_map = {
        "keine": 1, "grundkenntnisse": 2, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5,
        "none": 1, "basic": 2, "medium": 3, "advanced": 4, "expert": 5
    }
    dq_map = {"hoch": 5, "mittel": 3, "niedrig": 1, "high": 5, "medium": 3, "low": 1}
    roadmap_map = {"ja": 5, "in_planung": 3, "nein": 1, "yes": 5, "planning": 3, "no": 1}
    gov_map = {"ja": 5, "teilweise": 3, "nein": 1, "yes": 5, "partial": 3, "no": 1}
    inov_map = {
        "sehr_offen": 5, "eher_offen": 4, "neutral": 3, "eher_zurueckhaltend": 2, "sehr_zurückhaltend": 1,
        "very_open": 5, "rather_open": 4, "neutral": 3, "rather_reluctant": 2, "very_reluctant": 1
    }

    dataset = [
        as_int(data.get("digitalisierungsgrad", 1), 1),
        auto_map.get(str(data.get("automatisierungsgrad", "")).lower(), 1),
        pap_map.get(str(data.get("prozesse_papierlos", "0-20")).lower(), 1),
        know_map.get(str(data.get("ki_knowhow", data.get("ai_knowhow", "keine"))).lower(), 1),
        as_int(data.get("risikofreude", data.get("risk_appetite", 1)), 1),
        dq_map.get(str(data.get("datenqualitaet", data.get("data_quality", ""))).lower(), 0),
        roadmap_map.get(str(data.get("ai_roadmap", "")).lower(), 0),
        gov_map.get(str(data.get("governance", "")).lower(), 0),
        inov_map.get(str(data.get("innovationskultur", data.get("innovation_culture", ""))).lower(), 0),
    ]
    labels_de = ["Digitalisierung", "Automatisierung", "Papierlos", "KI-Know-how", "Risikofreude", "Datenqualität", "Roadmap", "Governance", "Innovationskultur"]
    labels_en = ["Digitalisation", "Automation", "Paperless", "AI know-how", "Risk appetite", "Data quality", "AI roadmap", "Governance", "Innovation culture"]
    labels = labels_de if lang == "de" else labels_en

    risk_level = 1
    dq = dataset[5]
    gov = dataset[7]
    roadmap = dataset[6]
    if dq == 1 or gov == 1:
        risk_level = 3
    elif roadmap in {1, 3}:
        risk_level = 2

    return {"score": score_percent, "dimensions": {"labels": labels, "values": dataset}, "risk_level": risk_level}

def _weights_from_env() -> Dict[str, int]:
    """
    Optional: SCORE_WEIGHTS='{"auto":1,"paperless":1,"knowhow":1,"risk":1,"dq":1,"roadmap":1,"gov":1,"innov":1,"digit":1}'
    """
    raw = os.getenv("SCORE_WEIGHTS")
    if not raw:
        return {}
    try:
        w = json.loads(raw)
        return {k: int(v) for k, v in w.items()}
    except Exception:
        return {}

def calc_score_percent(data: dict) -> int:
    """
    Gewichtete Score-Berechnung. Default wie bisher, aber ENV überschreibt Gewichte.
    """
    w = {"digit": 1, "auto": 1, "paperless": 1, "knowhow": 1, "risk": 1, "dq": 1, "roadmap": 1, "gov": 1, "innov": 1}
    w.update(_weights_from_env())

    def as_int_val(v, d=0):
        try:
            return int(v)
        except Exception:
            return d

    auto_map = {"sehr_niedrig": 0, "eher_niedrig": 1, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5,
                "very_low": 0, "rather_low": 1, "medium": 3, "rather_high": 4, "very_high": 5}
    pap_map = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5, "0-20%": 1, "21-50%": 2, "51-80%": 4, "81-100%": 5}
    know_map = {"keine": 0, "grundkenntnisse": 1, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5,
                "none": 0, "basic": 1, "medium": 3, "advanced": 4, "expert": 5}
    dq_map = {"hoch": 5, "mittel": 3, "niedrig": 1, "high": 5, "medium": 3, "low": 1}
    roadmap_map = {"ja": 5, "in_planung": 3, "nein": 1, "yes": 5, "planning": 3, "no": 1}
    gov_map = {"ja": 5, "teilweise": 3, "nein": 1, "yes": 5, "partial": 3, "no": 1}
    inov_map = {"sehr_offen": 5, "eher_offen": 4, "neutral": 3, "eher_zurueckhaltend": 2, "sehr_zurückhaltend": 1,
                "very_open": 5, "rather_open": 4, "neutral": 3, "rather_reluctant": 2, "very_reluctant": 1}

    vals = {
        "digit": as_int_val(data.get("digitalisierungsgrad", 1), 1),
        "auto": auto_map.get(str(data.get("automatisierungsgrad", "")).lower(), 0),
        "paperless": pap_map.get(str(data.get("prozesse_papierlos", "0-20")).lower(), 0),
        "knowhow": know_map.get(str(data.get("ki_knowhow", data.get("ai_knowhow", "keine"))).lower(), 0),
        "risk": as_int_val(data.get("risikofreude", data.get("risk_appetite", 1)), 1),
        "dq": dq_map.get(str(data.get("datenqualitaet") or data.get("data_quality") or "").lower(), 0),
        "roadmap": roadmap_map.get(str(data.get("ai_roadmap") or "").lower(), 0),
        "gov": gov_map.get(str(data.get("governance") or "").lower(), 0),
        "innov": inov_map.get(str(data.get("innovationskultur") or data.get("innovation_culture") or "").lower(), 0),
    }

    max_each = 5
    total_weight = sum(w.values())
    weighted = sum(vals[k] * w[k] for k in vals)
    max_score = max_each * total_weight
    try:
        percent = int((weighted / max_score) * 100)
    except Exception:
        percent = 0
    return max(0, min(100, percent))

def build_funding_table(data: dict, lang: str = "de", max_items: int = 6) -> List[Dict[str, str]]:
    import csv
    path = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path):
        return []
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    targets = {"solo": ["solo", "freelancer", "freiberuflich", "einzel"], "team": ["kmu", "team", "small"], "kmu": ["kmu", "sme"]}.get(size, [])
    region = (data.get("bundesland") or data.get("state") or "").lower()
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            zg = (row.get("Zielgruppe", "") or "").lower()
            reg = (row.get("Region", "") or "").lower()
            target_ok = True if not targets else any(t in zg for t in targets)
            region_ok = True if not region else (reg == region or reg == "bund")
            if target_ok and region_ok:
                rows.append(
                    {
                        "name": row.get("Name", ""),
                        "zielgruppe": row.get("Zielgruppe", ""),
                        "foerderhoehe": row.get("Fördersumme (€)", ""),
                        "link": row.get("Link", ""),
                    }
                )
    return rows[:max_items]

def build_tools_table(data: dict, branche: str, lang: str = "de", max_items: int = 8) -> List[Dict[str, str]]:
    import csv
    path = os.path.join("data", "tools.csv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            tags = (row.get("Tags") or row.get("Branche") or "").lower()
            if branche and tags and branche not in tags:
                continue
            out.append(
                {
                    "name": row.get("Name", ""),
                    "usecase": row.get("Usecase") or row.get("Einsatz") or "",
                    "cost": row.get("Kosten") or row.get("Cost") or "",
                    "link": row.get("Link", ""),
                }
            )
    return out[:max_items]

def build_dynamic_funding(data: dict, lang: str = "de", max_items: int = 5) -> str:
    import csv
    path = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, newline="", encoding="utf-8") as csvfile:
            programmes = list(csv.DictReader(csvfile))
    except Exception:
        return ""
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    targets = {"solo": ["solo", "freelancer", "freiberuflich", "einzel"], "team": ["kmu", "team", "small"], "kmu": ["kmu", "sme"]}.get(size, [])
    region = (data.get("bundesland") or data.get("state") or "").lower()

    def matches(row):
        zg = (row.get("Zielgruppe", "") or "").lower()
        reg = (row.get("Region", "") or "").lower()
        target_ok = True if not targets else any(t in zg for t in targets)
        region_ok = True if not region else (reg == region or reg == "bund")
        return target_ok and region_ok

    filtered = [p for p in programmes if matches(p)] or programmes[:max_items]
    selected = filtered[:max_items]
    if not selected:
        return ""
    title = "Dynamische Förderprogramme" if lang == "de" else "Dynamic funding programmes"
    out = [f"<h3>{title}</h3>", "<ul>"]
    for p in selected:
        name = p.get("Name", "")
        desc = (p.get("Beschreibung", "") or "").strip()
        link = p.get("Link", "")
        grant = p.get("Fördersumme (€)", "")
        line = (f"<b>{name}</b>: {desc} – Förderhöhe: {grant}" if lang == "de" else f"<b>{name}</b>: {desc} – Funding amount: {grant}")
        if link:
            line += f' – <a href="{link}" target="_blank">Link</a>'
        out.append(f"<li>{line}</li>")
    out.append("</ul>")
    return "\n".join(out)

def _distill_two_lists(html_src: str, lang: str, title_a: str, title_b: str) -> str:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if lang == "de":
        sys = "Du extrahierst präzise Listen aus HTML."
        usr = (
            f"Extrahiere aus folgendem HTML zwei kompakte Listen als HTML:\n"
            f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n- 4–6 Punkte je Liste, kurze Imperative, nur valides HTML.\n\nHTML:\n{html_src}"
        )
    else:
        sys = "You extract precise lists from HTML."
        usr = (
            f"From the HTML, extract two compact lists as HTML:\n"
            f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n- 4–6 bullets each, short imperatives, return VALID HTML only.\n\nHTML:\n{html_src}"
        )
    try:
        out = _chat_complete([{"role": "system", "content": sys}, {"role": "user", "content": usr}], model_name=model, temperature=0.2)
        return ensure_html(out, lang)
    except Exception:
        return ""

def distill_quickwins_risks(source_html: str, lang: str = "de") -> Dict[str, str]:
    html = _distill_two_lists(source_html, lang, "Quick Wins", "Hauptrisiken" if lang == "de" else "Key Risks")
    if not html:
        return {"quick_wins_html": "", "risks_html": ""}
    m = re.split(r"(?i)<h3[^>]*>", html)
    if len(m) >= 3:
        a = "<h3>" + m[1]
        b = "<h3>" + m[2]
        if "Quick" in a:
            return {"quick_wins_html": a, "risks_html": b}
        else:
            return {"quick_wins_html": b, "risks_html": a}
    return {"quick_wins_html": html, "risks_html": ""}

def distill_recommendations(source_html: str, lang: str = "de") -> str:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if lang == "de":
        sys = "Du destillierst Maßnahmen aus HTML."
        usr = ("Extrahiere aus dem HTML 5–8 konkrete Maßnahmen als geordnete Liste <ol>. "
               "Imperativ, jeweils 1 Zeile. Gib nur HTML zurück.\n\n" + f"HTML:\n{source_html}")
    else:
        sys = "You distill actions from HTML."
        usr = ("Extract 5–8 actionable steps as an ordered list <ol>. "
               "Imperative, one line each. Return HTML only.\n\n" + f"HTML:\n{source_html}")
    try:
        out = _chat_complete([{"role": "system", "content": sys}, {"role": "user", "content": usr}], model_name=model, temperature=0.2)
        return ensure_html(out, lang)
    except Exception:
        return ""

def build_extended_risks(data: dict, lang: str = "de") -> str:
    risks = []
    dq = (data.get("datenqualitaet") or data.get("data_quality") or "").lower()
    if dq in {"niedrig", "low"}:
        risks.append("Die Datenqualität ist niedrig; unstrukturierte/lückenhafte Daten erschweren KI-Projekte."
                     if lang == "de" else "Your data quality is low; unstructured or incomplete data hinder AI projects.")
    if (data.get("ai_roadmap") or "").lower() in {"nein", "no"}:
        risks.append("Es fehlt eine klar definierte KI-Roadmap; Risiko ineffizienter Insellösungen."
                     if lang == "de" else "No clearly defined AI roadmap; risk of inefficient point solutions.")
    if (data.get("governance") or "").lower() in {"nein", "no"}:
        risks.append("Keine Daten-/KI-Governance; erhöhtes Rechts-/Prozessrisiko."
                     if lang == "de" else "No data/AI governance; increased legal/process risk.")
    inv = (data.get("innovationskultur") or data.get("innovation_culture") or "").lower()
    if inv in {"eher_zurueckhaltend", "sehr_zurückhaltend", "rather_reluctant", "very_reluctant"}:
        risks.append("Zurückhaltende Innovationskultur kann KI-Erfolg gefährden."
                     if lang == "de" else "Reluctant innovation culture can jeopardise AI success.")
    if not risks:
        return ""
    return "<ul>" + "".join(f"<li>{r}</li>" for r in risks) + "</ul>"

def build_one_pager(report: Dict[str, Any], lang: str = "de") -> str:
    score = report.get("score_percent", 0)
    quick = report.get("quick_wins_html", "")
    steps = report.get("recommendations_html", "") or report.get("roadmap_html", "")
    tools = report.get("tools_table", [])[:4]
    funds = report.get("foerderprogramme_table", [])[:4]

    def tbl(rows: List[Dict[str, str]], cols: List[str]) -> str:
        if not rows:
            return ""
        thead = "".join(f"<th>{c}</th>" for c in cols)
        trs = []
        for r in rows:
            tds = []
            for c in cols:
                val = r.get(c.lower(), r.get(c)) or ""
                if c.lower() in {"link"} and val:
                    tds.append(f'<td><a href="{val}" target="_blank">{val}</a></td>')
                else:
                    tds.append(f"<td>{val}</td>")
            trs.append("<tr>" + "".join(tds) + "</tr>")
        return f'<table class="mini"><thead><tr>{thead}</tr></thead><tbody>{"".join(trs)}</tbody></table>'

    title = "One-Pager" if lang == "de" else "One-pager"
    col_tools = ["name", "usecase", "cost", "link"]
    col_fund = ["name", "zielgruppe", "foerderhoehe", "link"]

    return f"""
<section class="onepager">
  <h2>{title}</h2>
  <div class="scorebox"><b>Score:</b> {score:.0f}%</div>
  <div class="grid">
    <div>
      <h3>{'Quick Wins'}</h3>
      {quick or '<p>-</p>'}
    </div>
    <div>
      <h3>{'Nächste Schritte' if lang=='de' else 'Next steps'}</h3>
      {steps or '<p>-</p>'}
    </div>
  </div>
  <div class="grid">
    <div>
      <h3>{'Empfohlene Tools' if lang=='de' else 'Recommended tools'}</h3>
      {tbl(tools, col_tools)}
    </div>
    <div>
      <h3>{'Förderungen (Auszug)' if lang=='de' else 'Funding (excerpt)'}</h3>
      {tbl(funds, col_fund)}
    </div>
  </div>
</section>
<style>
.onepager .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.onepager .scorebox {{ background:#eaf6ff; border:1px solid #b5d6f6; padding:10px 12px; border-radius:10px; margin:8px 0 16px; }}
.onepager table.mini {{ width:100%; border-collapse: collapse; font-size: 12px; }}
.onepager table.mini th, .onepager table.mini td {{ border:1px solid #e3e7ef; padding:6px 8px; vertical-align: top; }}
.onepager h3 {{ margin-top:6px; }}
@media print {{
  .onepager .grid {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
"""
# gpt_analyze.py — Teil 4/4

def _jinja_env():
    return Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html", "htm"]),
        enable_async=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )

def _pick_template(lang: str) -> Optional[str]:
    if lang == "de" and os.path.exists("templates/pdf_template.html"):
        return "pdf_template.html"
    if os.path.exists("templates/pdf_template_en.html"):
        return "pdf_template_en.html"
    return None

def _data_uri_for(path: str) -> Optional[str]:
    if not path or path.startswith(("http://", "https://", "data:")):
        return path
    if os.path.exists(path):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    tp = os.path.join("templates", path)
    if os.path.exists(tp):
        mime = mimetypes.guess_type(tp)[0] or "application/octet-stream"
        with open(tp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return None

def _inline_local_images(html: str) -> str:
    def repl(m):
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        data = _data_uri_for(src)
        return m.group(0).replace(src, data) if data else m.group(0)
    return re.sub(r'src="([^"]+)"', repl, html)

def _toc_from_report(report: Dict[str, Any], lang: str) -> str:
    toc_items = []
    def add(title_key, title_label):
        if report.get(title_key):
            toc_items.append(f"<li>{title_label}</li>")
    if lang == "de":
        add("exec_summary_html", "Executive Summary")
        add("vision", "Visionäre Empfehlung")
        if report.get("chart_data"): toc_items.append("<li>Visualisierung</li>")
        if report.get("quick_wins_html") or report.get("risks_html"): toc_items.append("<li>Quick Wins & Risiken</li>")
        add("recommendations_html", "Empfehlungen")
        add("roadmap_html", "Roadmap")
        if report.get("foerderprogramme_table"): toc_items.append("<li>Förderprogramme</li>")
        if report.get("tools_table"): toc_items.append("<li>KI-Tools & Software</li>")
        add("sections_html", "Weitere Kapitel")
    else:
        add("exec_summary_html", "Executive summary")
        add("vision", "Visionary recommendation")
        if report.get("chart_data"): toc_items.append("<li>Visuals</li>")
        if report.get("quick_wins_html") or report.get("risks_html"): toc_items.append("<li>Quick wins & key risks</li>")
        add("recommendations_html", "Recommendations")
        add("roadmap_html", "Roadmap")
        if report.get("foerderprogramme_table"): toc_items.append("<li>Funding programmes</li>")
        if report.get("tools_table"): toc_items.append("<li>AI tools</li>")
        add("sections_html", "Additional sections")
    return "<ul>" + "".join(toc_items) + "</ul>" if toc_items else ""

def generate_full_report(data: dict, lang: str = "de") -> dict:
    """
    Ruft die Kapitel nacheinander ab (stabil) und erstellt strukturierte HTML-Snippets + Tabellen.
    """
    branche = (data.get("branche") or "default").lower()
    lang = _norm_lang(lang)
    data["score_percent"] = calc_score_percent(data)
    solo = is_self_employed(data)
    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar", "yes", "unsure"}

    chapters = ["executive_summary", "vision", "tools"] + (["foerderprogramme"] if wants_funding else []) + ["roadmap", "compliance", "praxisbeispiel"]
    out: Dict[str, Any] = {}
    for chap in chapters:
        try:
            sect_html = gpt_generate_section_html(data, branche, chap, lang=lang)
            out[chap] = ensure_html(strip_code_fences(fix_encoding(sect_html)), lang)
        except Exception as e:
            out[chap] = f"<p>[Fehler in Kapitel {chap}: {e}]</p>"

    # Präambel & Destillate
    out["preface"] = generate_preface(lang=lang, score_percent=data.get("score_percent"))

    src_for_qr = (out.get("executive_summary") or "") + "\n\n" + (out.get("roadmap") or "")
    q_r = distill_quickwins_risks(src_for_qr, lang=lang)
    out["quick_wins_html"] = q_r.get("quick_wins_html", "")
    out["risks_html"] = q_r.get("risks_html", "")

    src_for_rec = (out.get("roadmap") or "") + "\n\n" + (out.get("compliance") or "")
    out["recommendations_html"] = distill_recommendations(src_for_rec, lang=lang) or (out.get("roadmap") or "")
    out["roadmap_html"] = out.get("roadmap", "")
    out["exec_summary_html"] = out.get("executive_summary", "")

    # Vision-Block zusätzlich als "vision_html" verfügbar machen
    if out.get("vision"):
        out["vision_html"] = f"<div class='vision-card'>{out['vision']}</div>"
    else:
        out["vision_html"] = ""

    # Sektionen zusammensetzen (Weitere Kapitel)
    parts = []
    if out.get("vision"):
        parts.append(f"<h2>{'Visionäre Empfehlung' if lang=='de' else 'Visionary Recommendation'}</h2>\n{out['vision']}")
    if out.get("tools"):
        parts.append("<h2>Tools</h2>\n" + out["tools"])
    if out.get("foerderprogramme"):
        label_foerd = "Förderprogramme" if lang == "de" else "Funding"
        note = "<p><em>Hinweis: Für Solo-Selbstständige gefiltert (sofern verfügbar).</em></p>" if solo and lang == "de" else ""
        parts.append(f"<h2>{label_foerd}</h2>\n{note}\n{out['foerderprogramme']}")
    if out.get("compliance"):
        parts.append("<h2>Compliance</h2>\n" + out["compliance"])
    if out.get("praxisbeispiel"):
        parts.append(f"<h2>{'Praxisbeispiel' if lang=='de' else 'Case Study'}</h2>\n{out['praxisbeispiel']}")
    out["sections_html"] = "\n\n".join(parts)

    # Zusätzliche dynamische Förderliste oben einblenden
    if wants_funding:
        dynamic_html = build_dynamic_funding(data, lang=lang)
        if dynamic_html:
            out["sections_html"] = dynamic_html + ("\n\n" + out["sections_html"] if out["sections_html"] else "")

    # Hauptrisiken mit Heuristik ergänzen
    extra_risks = build_extended_risks(data, lang=lang)
    if extra_risks:
        existing = out.get("risks_html", "") or ""
        out["risks_html"] = (existing.strip() + "\n" + extra_risks) if existing.strip() else extra_risks

    # Tabellen (CSV → Dict-Listen), plus Fallbacks aus GPT-HTML
    out["score_percent"] = data["score_percent"]
    out["chart_data"] = build_chart_payload(data, out["score_percent"], lang=lang)

    try:
        out["foerderprogramme_table"] = build_funding_table(data, lang=lang)
    except Exception:
        out["foerderprogramme_table"] = []

    try:
        out["tools_table"] = build_tools_table(data, branche=branche, lang=lang)
    except Exception:
        out["tools_table"] = []

    # Fallback aus GPT-HTML, falls CSV leer blieb
    if wants_funding and not out.get("foerderprogramme_table"):
        teaser = out.get("foerderprogramme") or out.get("sections_html", "")
        rows = []
        # robusteres Parsing (ohne <b> Zwang)
        for m in re.finditer(
            r"(?:<b>)?([^<]+?)(?:</b>)?.*?(?:Förderhöhe|Funding amount)[:\s]*([^<]+).*?<a[^>]*href=\"([^\"]+)\"",
            teaser, re.I | re.S
        ):
            name, amount, link = m.groups()
            rows.append({"name": (name or "").strip(), "zielgruppe": "", "foerderhoehe": (amount or "").strip(), "link": link})
        out["foerderprogramme_table"] = rows[:6]

    if not out.get("tools_table"):
        html_tools = out.get("tools") or out.get("sections_html", "")
        rows = []
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html_tools, re.I):
            link, name = m.group(1), m.group(2)
            if name and link:
                rows.append({"name": name.strip(), "usecase": "", "cost": "", "link": link})
        out["tools_table"] = rows[:8]

    # One-Pager erzeugen + TOC generieren
    out["one_pager_html"] = build_one_pager(out, lang=lang)
    out["toc_html"] = _toc_from_report(out, lang)

    return out

def generate_preface(lang: str = "de", score_percent: Optional[float] = None) -> str:
    if lang == "de":
        preface = (
            "<p>Dieses Dokument fasst die Ergebnisse Ihres KI-Readiness-Checks zusammen und bietet individuelle "
            "Empfehlungen für die nächsten Schritte. Es basiert auf Ihren Angaben und berücksichtigt aktuelle gesetzliche "
            "Vorgaben, Fördermöglichkeiten und technologische Entwicklungen.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Ihr aktueller KI-Readiness-Score liegt bei {score_percent:.0f}%.</b> "
                "Dieser Wert zeigt, wie gut Sie auf den Einsatz von KI vorbereitet sind.</p>"
            )
        return preface
    else:
        preface = (
            "<p>This document summarises your AI-readiness results and provides tailored next steps. "
            "It is based on your input and considers legal requirements, funding options and current AI developments.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Your current AI-readiness score is {score_percent:.0f}%.</b> "
                "It indicates how prepared you are to adopt AI.</p>"
            )
        return preface

def _template_env_and_name(lang: str):
    env = _jinja_env()
    name = _pick_template(lang)
    return env, name

def analyze_briefing(payload: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """
    SYNCHRON (kein async): Wird direkt aus main.py aufgerufen.
    Liefert ein Dict mit 'html', 'lang', 'score_percent', 'meta'.
    """
    lang = _norm_lang(lang or payload.get("lang") or payload.get("language") or payload.get("sprache"))
    report = generate_full_report(payload, lang=lang)

    env, template_name = _template_env_and_name(lang)
    if template_name:
        tmpl = env.get_template(template_name)
        footer_de = (
            "TÜV-zertifiziertes KI-Management © {year}: Wolf Hohl · "
            "E-Mail: kontakt@ki-sicherheit.jetzt · DSGVO- & EU-AI-Act-konform · "
            "Alle Angaben ohne Gewähr; keine Rechtsberatung."
        )
        footer_en = (
            "TÜV-certified AI Management © {year}: Wolf Hohl · "
            "Email: kontakt@ki-sicherheit.jetzt · GDPR & EU-AI-Act compliant · "
            "No legal advice."
        )
        footer_text = (footer_de if lang == "de" else footer_en).format(year=datetime.now().year)
        ctx = {
            "lang": lang,
            "today": datetime.now().strftime("%Y-%m-%d"),
            "datum": datetime.now().strftime("%Y-%m-%d"),
            "score_percent": report.get("score_percent", 0),
            "preface": report.get("preface", ""),
            "exec_summary_html": report.get("exec_summary_html", ""),
            "quick_wins_html": report.get("quick_wins_html", ""),
            "risks_html": report.get("risks_html", ""),
            "recommendations_html": report.get("recommendations_html", ""),
            "roadmap_html": report.get("roadmap_html", ""),
            "sections_html": report.get("sections_html", ""),
            "vision_html": report.get("vision_html", ""),
            "one_pager_html": report.get("one_pager_html", ""),
            "toc_html": report.get("toc_html", ""),
            "chart_data_json": json.dumps(report.get("chart_data", {}), ensure_ascii=False),
            "foerderprogramme_table": report.get("foerderprogramme_table", []),
            "tools_table": report.get("tools_table", []),
            "footer_text": footer_text,
            "logo_main": _data_uri_for("ki-sicherheit-logo.webp") or _data_uri_for("ki-sicherheit-logo.png"),
            "logo_tuev": _data_uri_for("tuev-logo-transparent.webp") or _data_uri_for("tuev-logo.webp"),
            "logo_euai": _data_uri_for("eu-ai.svg"),
            "logo_dsgvo": _data_uri_for("dsgvo.svg"),
            "badge_ready": _data_uri_for("ki-ready-2025.webp"),
        }
        html = tmpl.render(**ctx)
    else:
        title = "KI-Readiness Report" if lang == "de" else "AI Readiness Report"
        html = f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{font-family:Arial,Helvetica,sans-serif;padding:24px;}}</style></head>
<body>
  <h1>{title} · {datetime.now().strftime("%Y-%m-%d")}</h1>
  <div>{report.get("preface","")}</div>
  <h2>Executive Summary</h2>{report.get("exec_summary_html","")}
  <div style="display:flex;gap:24px;">
    <div style="flex:1">{report.get("quick_wins_html","")}</div>
    <div style="flex:1">{report.get("risks_html","")}</div>
  </div>
  <h2>{'Nächste Schritte' if lang=='de' else 'Next steps'}</h2>{report.get("recommendations_html","") or report.get("roadmap_html","")}
  {report.get("sections_html","")}
  <hr>
  <small>TÜV-zertifiziertes KI-Management © {datetime.now().year}: Wolf Hohl · E-Mail: kontakt@ki-sicherheit.jetzt</small>
</body></html>"""

    # Lokale Bilder inline einbetten (robuster PDF-Render) + Code-Fences weg
    html = _inline_local_images(strip_code_fences(html))

    return {
        "html": html,
        "lang": lang,
        "score_percent": report.get("score_percent", 0),
        "meta": {
            "chapters": [k for k in ("executive_summary", "vision", "tools", "foerderprogramme", "roadmap", "compliance", "praxisbeispiel") if report.get(k)],
            "one_pager": True,
        },
    }

# Backwards-Compat alias
analyze_full_report = generate_full_report
