# gpt_analyze.py — Gold-Standard (Teil 1/4)
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
# gpt_analyze.py — Gold-Standard (Teil 2/4)

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

def build_context(data: dict, branche: str, lang: str = "de") -> dict:
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

    # bequeme Aliase
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
    def replace_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)
    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template_text)
    def replace_simple(m):
        key = m.group(1); val = context.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, template_text)

def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
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
    base_rules = (
        "Gib die Antwort ausschließlich als gültiges HTML ohne <html>-Wrapper zurück. "
        "Nutze <h3>, <p>, <ul>, <ol>, <table>. Keine Meta-Kommentare. Kurze Sätze."
        if is_de else
        "Return VALID HTML only (no <html> wrapper). Use <h3>, <p>, <ul>, <ol>, <table>. No meta talk. Be concise."
    )
    style = "\n\n---\n" + base_rules

    if chapter == "executive_summary":
        style += ("\n- Gliedere in: <h3>Was tun?</h3><ul>…</ul><h3>Warum?</h3><p>…</p><h3>Nächste 3 Schritte</h3><ol>…</ol>"
                  "\n- Maximal 5 Bullet-Points pro Liste. Fette jeweils das erste Schlüsselwort."
                  if is_de else
                  "\n- Structure: <h3>What to do?</h3><ul>…</ul><h3>Why?</h3><p>…</p><h3>Next 3 steps</h3><ol>…</ol>"
                  "\n- Max 5 bullets per list. Bold the first keyword per bullet.")

    if chapter == "vision":
        style += ("\n- Form: 1 kühne Idee (Titel + 1 Satz); 1 MVP (2–4 Wochen, grobe Kosten); 3 KPIs in <ul>. "
                  "Branchen-/Größenbezug, keine Allgemeinplätze."
                  if is_de else
                  "\n- Form: 1 bold idea (title + one-liner); 1 MVP (2–4 weeks, rough cost); 3 KPIs in <ul>. "
                  "Adapt to industry/size, avoid genericities.")

    if chapter == "tools":
        style += ("\n- <table> mit Spalten: Name | Usecase | Kosten | Link. Max. 7 Zeilen, DSGVO/EU-freundlich."
                  if is_de else
                  "\n- <table> columns: Name | Use case | Cost | Link. Max 7 rows. Prefer GDPR/EU-friendly tools.")

    if chapter in ("foerderprogramme", "foerderung", "funding"):
        style += ("\n- <table>: Name | Zielgruppe | Förderhöhe | Link. Max. 5 Zeilen."
                  if is_de else
                  "\n- <table>: Name | Target group | Amount | Link. Max 5 rows.")

    if context.get("is_self_employed"):
        style += ("\n- Solo-Selbstständig: Empfehlungen skalierbar halten; passende Förderungen priorisieren."
                  if is_de else
                  "\n- Solo self-employed: keep recommendations scalable; prioritize suitable funding.")

    return prompt + style

def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float] = None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

def gpt_generate_section(data, branche, chapter, lang="de"):
    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    context = build_context(data, branche, lang)
    context = add_innovation_features(context, branche, data)
    context = add_websearch_links(context, branche, context.get("projektziel", ""))
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f: md = f.read()
            ctx_list = [f"<li>{ln[2:].strip()}</li>" for ln in md.splitlines() if ln.strip().startswith("- ")]
            context["checklisten"] = "<ul>" + "\n".join(ctx_list) + "</ul>" if ctx_list else ""
        else:
            context["checklisten"] = ""
    prompt = build_masterprompt(chapter, context, lang)
    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model
    section_text = _chat_complete(
        messages=[
            {"role": "system", "content":
             ("Du bist TÜV-zertifizierter KI-Manager, KI-Strategieberater, Datenschutz- und Fördermittel-Experte. "
              "Liefere präzise, umsetzbare, aktuelle, branchenrelevante Inhalte als HTML.")
             if lang == "de" else
             ("You are a TÜV-certified AI manager and strategy consultant. "
              "Deliver precise, actionable, up-to-date, sector-relevant content as HTML.")},
            {"role": "user", "content": prompt},
        ],
        model_name=model_name,
        temperature=None,
    )
    return section_text

def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(strip_code_fences(fix_encoding(html)), lang)
# gpt_analyze.py — Gold-Standard (Teil 3/4)

def build_chart_payload(data: dict, score_percent: int, lang: str = "de") -> dict:
    def as_int(v, d=0):
        try: return int(v)
        except Exception: return d

    auto_map = {"sehr_niedrig": 1, "eher_niedrig": 2, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5,
                "very_low": 1, "rather_low": 2, "medium": 3, "rather_high": 4, "very_high": 5}
    pap_map  = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5}
    know_map = {"keine": 1, "grundkenntnisse": 2, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5,
                "none": 1, "basic": 2, "medium": 3, "advanced": 4, "expert": 5}
    dq_map   = {"hoch": 5, "mittel": 3, "niedrig": 1, "high": 5, "medium": 3, "low": 1}
    roadmap_map = {"ja": 5, "in_planung": 3, "nein": 1, "yes": 5, "planning": 3, "no": 1}
    gov_map  = {"ja": 5, "teilweise": 3, "nein": 1, "yes": 5, "partial": 3, "no": 1}
    inov_map = {"sehr_offen": 5, "eher_offen": 4, "neutral": 3, "eher_zurueckhaltend": 2, "sehr_zurückhaltend": 1,
                "very_open": 5, "rather_open": 4, "neutral": 3, "rather_reluctant": 2, "very_reluctant": 1}

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
    labels_de = ["Digitalisierung","Automatisierung","Papierlos","KI-Know-how","Risikofreude","Datenqualität","Roadmap","Governance","Innovationskultur"]
    labels_en = ["Digitalisation","Automation","Paperless","AI know-how","Risk appetite","Data quality","AI roadmap","Governance","Innovation culture"]
    labels = labels_de if lang == "de" else labels_en

    risk_level = 1
    dq, gov, roadmap = dataset[5], dataset[7], dataset[6]
    if dq == 1 or gov == 1: risk_level = 3
    elif roadmap in {1,3}:  risk_level = 2

    return {"score": score_percent, "dimensions": {"labels": labels, "values": dataset}, "risk_level": risk_level}

def _weights_from_env() -> Dict[str, int]:
    raw = os.getenv("SCORE_WEIGHTS")
    if not raw: return {}
    try: return {k:int(v) for k,v in json.loads(raw).items()}
    except Exception: return {}

def calc_score_percent(data: dict) -> int:
    """
    Deprecated global readiness score.

    The Gold‑Standard version of the KI‑Readiness report no longer uses an
    aggregated readiness score. To maintain backwards compatibility this
    function now always returns ``0``.  The individual readiness dimensions
    (digitalisation, automation, paperless processes and AI know‑how) are
    displayed separately as KPI tiles instead of a single score.
    """
    # Previously this function computed an average of the digitalisation and
    # automation degrees.  Returning zero ensures any legacy code expecting
    # an integer still functions without surfacing a misleading aggregate.
    return 0

def build_funding_table(data: dict, lang: str = "de", max_items: int = 6) -> List[Dict[str, str]]:
    import csv, os
    path = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path): return []
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    targets = {"solo":["solo","freelancer","freiberuflich","einzel"],"team":["kmu","team","small"],"kmu":["kmu","sme"]}.get(size,[])
    region = (data.get("bundesland") or data.get("state") or "").lower()
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            zg = (row.get("Zielgruppe","") or "").lower()
            reg = (row.get("Region","") or "").lower()
            t_ok = True if not targets else any(t in zg for t in targets)
            r_ok = True if not region else (reg == region or reg == "bund")
            if t_ok and r_ok:
                rows.append({"name":row.get("Name",""),"zielgruppe":row.get("Zielgruppe",""),
                             "foerderhoehe":row.get("Fördersumme (€)",""),"link":row.get("Link","")})
    return rows[:max_items]

def build_tools_table(data: dict, branche: str, lang: str = "de", max_items: int = 8) -> List[Dict[str, str]]:
    import csv, os
    path = os.path.join("data", "tools.csv")
    if not os.path.exists(path): return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            tags = (row.get("Tags") or row.get("Branche") or "").lower()
            if branche and tags and branche not in tags: continue
            out.append({"name":row.get("Name",""),"usecase":row.get("Usecase") or row.get("Einsatz") or "",
                        "cost":row.get("Kosten") or row.get("Cost") or "","link":row.get("Link","")})
    return out[:max_items]

def build_dynamic_funding(data: dict, lang: str = "de", max_items: int = 5) -> str:
    import csv, os
    path = os.path.join("data", "foerdermittel.csv")
    if not os.path.exists(path): return ""
    try:
        with open(path, newline="", encoding="utf-8") as csvfile:
            programmes = list(csv.DictReader(csvfile))
    except Exception:
        return ""
    size = (data.get("unternehmensgroesse") or data.get("company_size") or "").lower()
    targets = {"solo":["solo","freelancer","freiberuflich","einzel"],"team":["kmu","team","small"],"kmu":["kmu","sme"]}.get(size,[])
    region = (data.get("bundesland") or data.get("state") or "").lower()

    def matches(row):
        zg = (row.get("Zielgruppe","") or "").lower()
        reg = (row.get("Region","") or "").lower()
        t_ok = True if not targets else any(t in zg for t in targets)
        r_ok = True if not region else (reg == region or reg == "bund")
        return t_ok and r_ok

    filtered = [p for p in programmes if matches(p)] or programmes[:max_items]
    selected = filtered[:max_items]
    if not selected: return ""
    title = "Dynamische Förderprogramme" if lang == "de" else "Dynamic funding programmes"
    out = [f"<h3>{title}</h3>","<ul>"]
    for p in selected:
        name = p.get("Name",""); desc = (p.get("Beschreibung","") or "").strip()
        link = p.get("Link",""); grant = p.get("Fördersumme (€)","")
        line = (f"<b>{name}</b>: {desc} – Förderhöhe: {grant}" if lang=="de" else f"<b>{name}</b>: {desc} – Funding amount: {grant}")
        if link: line += f' – <a href="{link}" target="_blank">Link</a>'
        out.append(f"<li>{line}</li>")
    out.append("</ul>")
    return "\n".join(out)
# gpt_analyze.py — Gold-Standard (Teil 4/4)

def distill_quickwins_risks(source_html: str, lang: str = "de") -> Dict[str, str]:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if lang == "de":
        sys = "Du extrahierst präzise Listen aus HTML."
        usr = f"<h3>Quick Wins</h3><ul>…</ul><h3>Hauptrisiken</h3><ul>…</ul>\n- 3–5 Punkte je Liste, nur HTML.\n\nHTML:\n{source_html}"
    else:
        sys = "You extract precise lists from HTML."
        usr = f"<h3>Quick wins</h3><ul>…</ul><h3>Key risks</h3><ul>…</ul>\n- 3–5 bullets each, HTML only.\n\nHTML:\n{source_html}"
    try:
        out = _chat_complete([{"role":"system","content":sys},{"role":"user","content":usr}], model_name=model, temperature=0.2)
        html = ensure_html(out, lang)
    except Exception:
        return {"quick_wins_html":"","risks_html":""}

    m = re.split(r"(?i)<h3[^>]*>", html)
    if len(m) >= 3:
        a = "<h3>" + m[1]; b = "<h3>" + m[2]
        if "Quick" in a: return {"quick_wins_html": a, "risks_html": b}
        else:           return {"quick_wins_html": b, "risks_html": a}
    return {"quick_wins_html": html, "risks_html": ""}

def distill_recommendations(source_html: str, lang: str = "de") -> str:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if lang == "de":
        sys = "Du destillierst Maßnahmen aus HTML."
        usr = "Extrahiere 5 TOP-Empfehlungen als <ol>, jede Zeile 1 Satz, Impact(H/M/L) und Aufwand(H/M/L) in Klammern."
    else:
        sys = "You distill actions from HTML."
        usr = "Extract Top 5 as <ol>, one line each, add Impact(H/M/L) and Effort(H/M/L) in brackets."
    try:
        out = _chat_complete([{"role":"system","content":sys},{"role":"user","content":source_html}], model_name=model, temperature=0.2)
        return ensure_html(out, lang)
    except Exception:
        return ""

def _jinja_env():
    return Environment(loader=FileSystemLoader("templates"),
                       autoescape=select_autoescape(["html","htm"]),
                       enable_async=False, trim_blocks=True, lstrip_blocks=True)

def _pick_template(lang: str) -> Optional[str]:
    if lang == "de" and os.path.exists("templates/pdf_template.html"):
        return "pdf_template.html"
    if os.path.exists("templates/pdf_template_en.html"):
        return "pdf_template_en.html"
    return None

def _data_uri_for(path: str) -> Optional[str]:
    if not path or path.startswith(("http://","https://","data:")): return path
    if os.path.exists(path):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path,"rb") as f: b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    tp = os.path.join("templates", path)
    if os.path.exists(tp):
        mime = mimetypes.guess_type(tp)[0] or "application/octet-stream"
        with open(tp,"rb") as f: b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    return None

def _inline_local_images(html: str) -> str:
    def repl(m):
        src = m.group(1)
        if src.startswith(("http://","https://","data:")): return m.group(0)
        data = _data_uri_for(src)
        return m.group(0).replace(src, data) if data else m.group(0)
    return re.sub(r'src="([^"]+)"', repl, html)

def _toc_from_report(report: Dict[str, Any], lang: str) -> str:
    toc_items = []
    def add(key, label):
        if report.get(key): toc_items.append(f"<li>{label}</li>")
    if lang == "de":
        add("exec_summary_html", "Executive Summary")
        if report.get("chart_data"): toc_items.append("<li>Visualisierung</li>")
        if report.get("quick_wins_html") or report.get("risks_html"): toc_items.append("<li>Quick Wins & Risiken</li>")
        add("recommendations_html", "Empfehlungen"); add("roadmap_html", "Roadmap")
        if report.get("foerderprogramme_table"): toc_items.append("<li>Förderprogramme</li>")
        if report.get("tools_table"): toc_items.append("<li>KI-Tools & Software</li>")
        add("sections_html", "Weitere Kapitel")
    else:
        add("exec_summary_html","Executive summary")
        if report.get("chart_data"): toc_items.append("<li>Visuals</li>")
        if report.get("quick_wins_html") or report.get("risks_html"): toc_items.append("<li>Quick wins & key risks</li>")
        add("recommendations_html", "Recommendations"); add("roadmap_html","Roadmap")
        if report.get("foerderprogramme_table"): toc_items.append("<li>Funding programmes</li>")
        if report.get("tools_table"): toc_items.append("<li>AI tools</li>")
        add("sections_html","Additional sections")
    return "<ul>" + "".join(toc_items) + "</ul>" if toc_items else ""

def generate_full_report(data: dict, lang: str = "de") -> dict:
    branche = (data.get("branche") or "default").lower()
    lang = _norm_lang(lang)
    # Gold‑Standard: do not calculate an aggregate score.  Instead, we rely on the
    # four core readiness dimensions (digitalisation, automation, paperless and AI
    # know‑how) which are presented as individual KPI tiles.  Explicitly set
    # score_percent to None to avoid including the score in the preface.
    data["score_percent"] = None
    solo = is_self_employed(data)
    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja","unklar","yes","unsure"}

    chapters = ["executive_summary","vision","tools"] + (["foerderprogramme"] if wants_funding else []) + ["roadmap","compliance","praxisbeispiel"]
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
    out["quick_wins_html"], out["risks_html"] = q_r.get("quick_wins_html",""), q_r.get("risks_html","")

    src_for_rec = (out.get("roadmap") or "") + "\n\n" + (out.get("compliance") or "")
    # Generate recommendations from the roadmap and compliance sections.  If the
    # language model returns an ordered list (<ol>), we remove duplicate list
    # items to avoid repeating suggestions already covered elsewhere.
    rec_html = distill_recommendations(src_for_rec, lang=lang)
    if rec_html:
        # De‑duplicate <li> entries while preserving order
        try:
            items = re.findall(r"<li[^>]*>(.*?)</li>", rec_html, re.S)
            seen = set()
            unique_items = []
            for it in items:
                # Normalise whitespace and HTML tags
                txt = re.sub(r"<[^>]+>", "", it).strip()
                if txt and txt not in seen:
                    seen.add(txt)
                    unique_items.append(it)
            if unique_items:
                # reconstruct HTML with unique items
                rec_html = "<ol>" + "".join([f"<li>{it}</li>" for it in unique_items]) + "</ol>"
        except Exception:
            pass
    out["recommendations_html"] = rec_html or (out.get("roadmap") or "")
    out["roadmap_html"] = out.get("roadmap","")
    out["exec_summary_html"] = out.get("executive_summary","")

    # Vision separat (NICHT in sections_html mischen)
    out["vision_html"] = f"<div class='vision-card'>{out['vision']}</div>" if out.get("vision") else ""

    # sections_html (ohne Vision)
    parts = []
    if out.get("tools"): parts.append("<h2>Tools</h2>\n" + out["tools"])
    if out.get("foerderprogramme"):
        label_foerd = "Förderprogramme" if lang == "de" else "Funding"
        note = "<p><em>Hinweis: Für Solo-Selbstständige gefiltert (sofern verfügbar).</em></p>" if solo and lang == "de" else ""
        parts.append(f"<h2>{label_foerd}</h2>\n{note}\n{out['foerderprogramme']}")
    if out.get("compliance"): parts.append("<h2>Compliance</h2>\n" + out["compliance"])
    if out.get("praxisbeispiel"): parts.append(f"<h2>{'Praxisbeispiel' if lang=='de' else 'Case Study'}</h2>\n" + out["praxisbeispiel"])
    out["sections_html"] = "\n\n".join(parts)

    # dynamische Förderliste separat bereitstellen (falls Tabelle leer)
    out["dynamic_funding_html"] = ""
    if wants_funding:
        dyn = build_dynamic_funding(data, lang=lang)
        if dyn: out["dynamic_funding_html"] = dyn

    # Diagrammdaten
    out["score_percent"] = data["score_percent"]
    out["chart_data"] = build_chart_payload(data, out["score_percent"], lang=lang)
    out["chart_data_json"] = json.dumps(out["chart_data"], ensure_ascii=False)

    # Tabellen (CSV)
    try: out["foerderprogramme_table"] = build_funding_table(data, lang=lang)
    except Exception: out["foerderprogramme_table"] = []
    try: out["tools_table"] = build_tools_table(data, branche=branche, lang=lang)
    except Exception: out["tools_table"] = []

    # Fallbacks (aus HTML) nur wenn CSV leer blieb
    if wants_funding and not out.get("foerderprogramme_table"):
        teaser = out.get("foerderprogramme") or out.get("sections_html","")
        rows = []
        for m in re.finditer(r'(?:<b>)?([^<]+?)(?:</b>)?.*?(?:Förderhöhe|Funding amount)[:\s]*([^<]+).*?<a[^>]*href="([^"]+)"', teaser, re.I|re.S):
            name, amount, link = m.groups()
            rows.append({"name":(name or "").strip(),"zielgruppe":"","foerderhoehe":(amount or "").strip(),"link":link})
        out["foerderprogramme_table"] = rows[:6]

    if not out.get("tools_table"):
        html_tools = out.get("tools") or out.get("sections_html","")
        rows = []
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html_tools, re.I):
            link, name = m.group(1), m.group(2)
            if name and link:
                rows.append({"name":name.strip(),"usecase":"","cost":"","link":link})
        out["tools_table"] = rows[:8]

    # --- Zusätzliche Kennzahlen, Benchmarks, Timeline und Risiken ---
    # Hilfsfunktionen zum Parsen von Zahlen und Benchmarks
    def _to_num(v):
        """Try to parse a percentage or numeric string into an int between 0 and 100."""
        if v is None:
            return 0
        try:
            # accept values like "35", "35%", "0.35", "7" (slider 1–10)
            s = str(v).strip().replace(",", ".")
            m = re.search(r"(\d+[\.,]?\d*)", s)
            if m:
                num = float(m.group(1))
                # If the number is a fraction (<=1), scale to percentage
                if num <= 1.0:
                    num = num * 100.0
                # If the number is between 1 and 10 and an integer (slider), scale to 0–100
                elif num <= 10 and num == int(num):
                    num = num * 10.0
                return max(0, min(100, int(round(num))))
        except Exception:
            pass
        return 0

    def _map_scale_text(value: str, mapping: Dict[str, int]) -> int:
        """
        Map textual responses to a numeric score.  The questionnaire uses verbal
        scales (e.g. "Eher hoch", "Mittel").  Provide a dictionary mapping of
        normalised lowercase responses to a value between 0 and 100.  If the
        exact key is not found, perform a fuzzy match where a mapping key
        appears as a substring of the user input.  This allows responses such
        as "eher hoch" or "hoch (schätzung)" to map correctly.  Unknown
        responses default to ``0``.
        """
        if not value:
            return 0
        key = str(value).strip().lower()
        # First try exact match
        if key in mapping:
            return mapping[key]
        # Fuzzy substring matching: check longer keys first to avoid
        # matching "hoch" inside "eher hoch" incorrectly.
        for k in sorted(mapping.keys(), key=len, reverse=True):
            if k and k in key:
                return mapping[k]
        return 0

    # ----------------------------------------------------------------------
    # KPI tiles: show the four core readiness dimensions instead of a single
    # aggregate score.  Each dimension is displayed with its own value.  The
    # keys for these values are mapped from the questionnaire responses.
    # ----------------------------------------------------------------------
    # Helper to normalise numeric strings to an integer percentage
    def _dim_value(key: str) -> int:
        return _to_num(data.get(key) or 0)
    own_digi = _dim_value("digitalisierungsgrad") or _dim_value("digitalisierungsgrad (%)") or _dim_value("digitalisierungs_score")
    # Automatisierungsgrad kann verbal angegeben sein (z. B. "Eher hoch").  Verwende eine Mapping-Tabelle.
    auto_mapping = {
        "gar nicht": 0,
        "nicht": 0,
        "eher niedrig": 25,
        "niedrig": 25,
        "mittel": 50,
        "eher hoch": 75,
        "hoch": 75,
        "sehr hoch": 90,
    }
    know_mapping = {
        "sehr niedrig": 10,
        "niedrig": 25,
        "mittel": 50,
        "hoch": 75,
        "sehr hoch": 90,
    }
    # Read raw responses
    raw_auto = data.get("automatisierungsgrad") or data.get("automatisierungsgrad (%)") or data.get("automatisierungs_score")
    raw_know = data.get("ki_knowhow") or data.get("knowhow") or data.get("ai_knowhow")
    own_auto = _dim_value("automatisierungsgrad") or _dim_value("automatisierungsgrad (%)") or _dim_value("automatisierungs_score") or _map_scale_text(raw_auto, auto_mapping)
    own_paper = _dim_value("prozesse_papierlos") or _dim_value("papierlos") or _dim_value("paperless")
    own_know = _dim_value("ki_knowhow") or _dim_value("knowhow") or _dim_value("ai_knowhow") or _map_scale_text(raw_know, know_mapping)

    kpis = []
    kpis.append({
        "label": "Digitalisierung" if lang == "de" else "Digitalisation",
        "value": f"{own_digi}%"
    })
    kpis.append({
        "label": "Automatisierung" if lang == "de" else "Automation",
        "value": f"{own_auto}%"
    })
    kpis.append({
        "label": "Papierlos" if lang == "de" else "Paperless",
        "value": f"{own_paper}%"
    })
    kpis.append({
        "label": "KI-Know-how" if lang == "de" else "AI know‑how",
        "value": f"{own_know}%"
    })
    out["kpis"] = kpis

    # Benchmarks für horizontale Balken (Ihr Wert vs. Branche)
    # Verwendet die zuvor berechneten eigenen Werte (own_digi, own_auto, own_paper, own_know)
    # anstatt sie erneut mit _to_num neu zu bestimmen. Dadurch bleiben Mapping
    # Ergebnisse (z. B. „eher hoch" → 75) konsistent in KPI-Kacheln und Benchmarks.
    # Branchen-Benchmarks aus dem Kontext (falls vorhanden)
    dig_bench = 0
    aut_bench = 0
    try:
        if ctx_bench:
            bstr = str(ctx_bench.get("benchmark", ""))
            m_d = re.search(r"Digitalisierungsgrad\s*[:=]\s*(\d+)", bstr)
            m_a = re.search(r"Automatisierungsgrad\s*[:=]\s*(\d+)", bstr)
            if m_d:
                dig_bench = int(m_d.group(1))
            if m_a:
                aut_bench = int(m_a.group(1))
    except Exception:
        # Wenn Benchmarks nicht geparst werden können, verbleiben sie bei 0
        pass
    # Papierlos und Know-how haben keine Branchenwerte in YAML; setze 50 als neutralen Richtwert
    paper_bench = 50
    know_bench = 50
    # Erstelle Benchmark‑Dictionary, das die eigenen Werte aus den vorab
    # berechneten KPI-Variablen übernimmt. So stimmen Balken und KPI-Kacheln überein.
    benchmarks = {
        ("Digitalisierung" if lang == "de" else "Digitalisation"): {"self": own_digi, "industry": dig_bench},
        ("Automatisierung" if lang == "de" else "Automation"): {"self": own_auto, "industry": aut_bench},
        ("Papierlos" if lang == "de" else "Paperless"): {"self": own_paper, "industry": paper_bench},
        ("Know-how" if lang == "de" else "Know‑how"): {"self": own_know, "industry": know_bench},
    }
    out["benchmarks"] = benchmarks

    # Timeline-Sektion aus der Roadmap extrahieren (30/3M/12M)
    def _distill_timeline_sections(source_html: str, lang: str = "de") -> Dict[str, List[str]]:
        """Extrahiert 2–3 stichpunktartige Maßnahmen für 30 Tage, 3 Monate, 12 Monate."""
        if not source_html:
            return {}
        model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
        if lang == "de":
            sys = "Du extrahierst präzise Listen aus HTML."
            usr = ("<h3>30 Tage</h3><ul>…</ul><h3>3 Monate</h3><ul>…</ul><h3>12 Monate</h3><ul>…</ul>\n"
                   "- 2–3 Punkte je Liste (Stichworte ohne Erklärungen)\n\nHTML:\n" + source_html)
        else:
            sys = "You extract concise lists from HTML."
            usr = ("<h3>30 days</h3><ul>…</ul><h3>3 months</h3><ul>…</ul><h3>12 months</h3><ul>…</ul>\n"
                   "- 2–3 bullets per list (short phrases only)\n\nHTML:\n" + source_html)
        try:
            out_html = _chat_complete([
                {"role": "system", "content": sys},
                {"role": "user", "content": usr}
            ], model_name=model, temperature=0.2)
            html = ensure_html(out_html, lang)
        except Exception:
            return {}
        # parse lists
        res = {"t30": [], "t90": [], "t365": []}
        for match in re.finditer(r"<h3[^>]*>([^<]+)</h3>\s*<ul>(.*?)</ul>", html, re.S|re.I):
            header = match.group(1).lower()
            items_html = match.group(2)
            items = re.findall(r"<li[^>]*>(.*?)</li>", items_html, re.S)
            items = [re.sub(r"<[^>]+>", "", it).strip() for it in items]
            items = [it for it in items if it]
            if '30' in header:
                res['t30'] = items[:3]
            elif '3' in header and ('monate' in header or 'months' in header):
                res['t90'] = items[:3]
            elif '12' in header:
                res['t365'] = items[:3]
        return res

    timeline_sections = _distill_timeline_sections(out.get("roadmap_html", ""), lang=lang)
    out["timeline"] = timeline_sections

    # Risiko-Heatmap heuristisch erstellen
    risk_rows = []
    # Bias/Transparenz – höheres Risiko bei geringem KI-Know-how
    know = own_know
    if know < 30:
        bias_lvl = 'hoch'
    elif know < 60:
        bias_lvl = 'mittel'
    else:
        bias_lvl = 'niedrig'
    risk_rows.append({"category": "Bias/Transparenz" if lang == "de" else "Bias/Transparency", "level": bias_lvl})
    # Datenschutz/AVV – höheres Risiko bei niedrigen Papierlos-Werten
    if own_paper < 30:
        ds_lvl = 'hoch'
    elif own_paper < 60:
        ds_lvl = 'mittel'
    else:
        ds_lvl = 'niedrig'
    risk_rows.append({"category": "Datenschutz/AVV" if lang == "de" else "Data protection/AV", "level": ds_lvl})
    # Lieferantenrisiko – setze medium als Default
    risk_rows.append({"category": "Lieferanten-Risiko" if lang == "de" else "Supplier risk", "level": 'mittel' if lang == 'de' else 'medium'})
    # Abhängigkeit Anbieter – Risiko hoch bei geringem Digitalisierungsgrad
    if own_digi < 30:
        dep_lvl = 'hoch'
    elif own_digi < 60:
        dep_lvl = 'mittel'
    else:
        dep_lvl = 'niedrig'
    risk_rows.append({"category": "Abhängigkeit Anbieter" if lang == "de" else "Vendor lock-in", "level": dep_lvl})
    out["risk_heatmap"] = risk_rows

    # Förder-Badges aus erster Programmeinträgen
    badges = []
    try:
        for row in (out.get("foerderprogramme_table") or [])[:2]:
            zg = (row.get("zielgruppe") or "").lower()
            # Solo/KMU Badge
            if 'solo' in zg or 'freelanc' in zg or 'freiberuf' in zg:
                badges.append("Solo-geeignet" if lang == "de" else "solo-friendly")
            elif 'kmu' in zg or 'sme' in zg:
                badges.append("KMU-geeignet" if lang == "de" else "SME-friendly")
            # Region Badge
            region = (data.get("bundesland") or data.get("state") or "").strip()
            if region:
                badges.append(region)
            # Förderhöhe Badge
            fstr = row.get("foerderhoehe") or row.get("amount") or ""
            m = re.search(r"(\d+\s*%|\d+[\.,]\d+\s*%)", fstr.replace('bis zu','').replace('bis','').replace('up to',''))
            if m:
                percent = m.group(1).strip()
                badges.append(("bis " + percent) if lang == "de" else ("up to " + percent))
            # Break after first row
    except Exception:
        pass
    # Entferne Duplikate, behalte Reihenfolge
    seen = set(); unique_badges = []
    for b in badges:
        if b and b not in seen:
            seen.add(b); unique_badges.append(b)
    out["funding_badges"] = unique_badges

    # One-Pager & TOC
    out["one_pager_html"] = ""  # optionaler Block (nicht genutzt)
    out["toc_html"] = _toc_from_report(out, lang)

    # Append personal and glossary sections
    out["ueber_mich_html"] = build_ueber_mich_section(lang=lang)
    out["glossary_html"] = build_glossary_section(lang=lang)
    return out


def build_ueber_mich_section(lang: str = "de") -> str:
    """
    Build an "Über mich" section for the report.  Uses the user's profile to
    provide a personal introduction.  In a production system this information
    might come from user metadata; here it is hardcoded based on the project
    description.

    :param lang: language code
    :return: HTML string with the personal introduction
    """
    if lang == "de":
        return (
            "<p><strong>Über den Autor</strong></p>"
            "<p>Wolf Hohl ist Texter, Schriftsteller und Gesellschafter mit über 30 Jahren Erfahrung in "
            "Marketing und Kommunikation. Als ehemaliger Geschäftsführer von Kinotrailer‑Produktionen hat er "
            "über 50 Mio € Umsatz verantwortet. Heute lebt er in Berlin, liest viel, macht Yoga und kocht gerne. "
            "Mit dem KI‑Readiness‑Report möchte er Unternehmen helfen, Chancen der künstlichen Intelligenz zu "
            "identifizieren und pragmatisch umzusetzen. Als Solo‑Berater ist er dabei unabhängig und "
            "zertifizierter KI‑Manager in Ausbildung.</p>"
            "<p>Sie erreichen ihn unter <a href=\"mailto:kontakt@ki-sicherheit.jetzt\">kontakt@ki-sicherheit.jetzt</a> "
            "oder über seine Website <a href=\"https://ki-sicherheit.jetzt\">ki-sicherheit.jetzt</a>.</p>"
        )
    else:
        return (
            "<p><strong>About the author</strong></p>"
            "<p>Wolf Hohl is a copywriter, author and former managing director with more than 30 years of experience "
            "in marketing and communications. In his previous role in cinema trailer production he generated over "
            "€50 million in revenue. Today he lives in Berlin, reads a lot, practices yoga and enjoys cooking. As a solo "
            "consultant and aspiring certified AI manager, his mission is to help organisations recognise and realise the "
            "potential of artificial intelligence.</p>"
            "<p>You can reach him at <a href=\"mailto:kontakt@ki-sicherheit.jetzt\">kontakt@ki-sicherheit.jetzt</a> "
            "or via his website <a href=\"https://ki-sicherheit.jetzt\">ki-sicherheit.jetzt</a>.</p>"
        )


def build_glossary_section(lang: str = "de") -> str:
    """
    Build a simple glossary of key terms used in the report.  This helps readers
    unfamiliar with AI or compliance terminology.  Definitions are intentionally
    kept brief and non‑technical.

    :param lang: language code
    :return: HTML string with glossary entries
    """
    if lang == "de":
        entries = {
            "KI (Künstliche Intelligenz)": "Technologien, die aus Daten lernen und selbstständig Entscheidungen treffen oder Empfehlungen aussprechen.",
            "DSGVO": "Datenschutz-Grundverordnung der EU; regelt den Umgang mit personenbezogenen Daten.",
            "DSFA": "Datenschutz-Folgenabschätzung; Analyse der Risiken für Betroffene bei bestimmten Datenverarbeitungen.",
            "EU AI Act": "Zukünftige EU-Verordnung, die Anforderungen und Risikoklassen für KI-Systeme festlegt.",
            "Quick Win": "Maßnahme mit geringem Aufwand und schnellem Nutzen.",
            "MVP": "Minimum Viable Product; erste funktionsfähige Version eines Produkts mit minimalem Funktionsumfang.",
        }
        out = ["<p><strong>Glossar</strong></p>"]
        out.append("<ul>")
        for term, definition in entries.items():
            out.append(f"<li><strong>{term}</strong>: {definition}</li>")
        out.append("</ul>")
        return "\n".join(out)
    else:
        entries = {
            "AI (Artificial Intelligence)": "Technologies that learn from data and can make decisions or generate recommendations on their own.",
            "GDPR": "General Data Protection Regulation; EU regulation governing personal data processing.",
            "DPIA": "Data Protection Impact Assessment; analysis of risks to individuals for certain processing operations.",
            "EU AI Act": "Upcoming EU legislation specifying requirements and risk classes for AI systems.",
            "Quick Win": "Action with low effort and immediate benefit.",
            "MVP": "Minimum Viable Product; first working version of a product with core functionality only.",
        }
        out = ["<p><strong>Glossary</strong></p>"]
        out.append("<ul>")
        for term, definition in entries.items():
            out.append(f"<li><strong>{term}</strong>: {definition}</li>")
        out.append("</ul>")
        return "\n".join(out)


def generate_qr_code_uri(link: str) -> str:
    """
    Generate a QR code image URI for the given link.  This implementation
    delegates the generation to Google's Chart API, which returns a PNG QR code.
    Note: this relies on external network access when rendering the PDF; if
    offline use is required, consider bundling a pre‑generated QR code.

    :param link: URL to encode in the QR code
    :return: direct link to a QR code image
    """
    from urllib.parse import quote
    encoded = quote(link, safe='')
    # 200x200 pixel PNG QR code
    return f"https://chart.googleapis.com/chart?chs=200x200&cht=qr&chl={encoded}&choe=UTF-8"

def generate_preface(lang: str = "de", score_percent: Optional[float] = None) -> str:
    if lang == "de":
        preface = ("<p>Dieses Dokument fasst die Ergebnisse Ihres KI-Readiness-Checks zusammen und bietet individuelle "
                   "Empfehlungen für die nächsten Schritte. Es basiert auf Ihren Angaben und berücksichtigt aktuelle gesetzliche "
                   "Vorgaben, Fördermöglichkeiten und technologische Entwicklungen.</p>")
        if score_percent is not None:
            preface += (f"<p><b>Ihr aktueller KI-Readiness-Score liegt bei {score_percent:.0f}%.</b> "
                        "Dieser Wert zeigt, wie gut Sie auf den Einsatz von KI vorbereitet sind.</p>")
        return preface
    else:
        preface = ("<p>This document summarises your AI-readiness results and provides tailored next steps. "
                   "It is based on your input and considers legal requirements, funding options and current AI developments.</p>")
        if score_percent is not None:
            preface += (f"<p><b>Your current AI-readiness score is {score_percent:.0f}%.</b> "
                        "It indicates how prepared you are to adopt AI.</p>")
        return preface

def analyze_briefing(payload: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    lang = _norm_lang(lang or payload.get("lang") or payload.get("language") or payload.get("sprache"))
    report = generate_full_report(payload, lang=lang)
    env, template_name = _jinja_env(), _pick_template(lang)
    if template_name:
        tmpl = env.get_template(template_name)
        footer_de = ("TÜV-zertifiziertes KI-Management © {year}: Wolf Hohl · "
                     "E-Mail: kontakt@ki-sicherheit.jetzt · DSGVO- & EU-AI-Act-konform · "
                     "Alle Angaben ohne Gewähr; keine Rechtsberatung.")
        footer_en = ("TÜV-certified AI Management © {year}: Wolf Hohl · "
                     "Email: kontakt@ki-sicherheit.jetzt · GDPR & EU-AI-Act compliant · "
                     "No legal advice.")
        footer_text = (footer_de if lang == "de" else footer_en).format(year=datetime.now().year)
        ctx = {
            "lang": lang,
            "today": datetime.now().strftime("%Y-%m-%d"),
            "datum": datetime.now().strftime("%Y-%m-%d"),
            "score_percent": report.get("score_percent", 0),
            "preface": report.get("preface",""),
            "exec_summary_html": report.get("exec_summary_html",""),
            "quick_wins_html": report.get("quick_wins_html",""),
            "risks_html": report.get("risks_html",""),
            "recommendations_html": report.get("recommendations_html",""),
            "roadmap_html": report.get("roadmap_html",""),
            "sections_html": report.get("sections_html",""),
            "vision_html": report.get("vision_html",""),
            "one_pager_html": report.get("one_pager_html",""),
            "toc_html": report.get("toc_html",""),
            "chart_data_json": report.get("chart_data_json","{}"),
            "foerderprogramme_table": report.get("foerderprogramme_table",[]),
            "tools_table": report.get("tools_table",[]),
            "dynamic_funding_html": report.get("dynamic_funding_html",""),
            "footer_text": footer_text,
            "logo_main": _data_uri_for("ki-sicherheit-logo.webp") or _data_uri_for("ki-sicherheit-logo.png"),
            "logo_tuev": _data_uri_for("tuev-logo-transparent.webp") or _data_uri_for("tuev-logo.webp"),
            "logo_euai": _data_uri_for("eu-ai.svg"),
            "logo_dsgvo": _data_uri_for("dsgvo.svg"),
            "badge_ready": _data_uri_for("ki-ready-2025.webp"),
            # neue Kontexte für KPI-Kacheln, Benchmarks, Timeline, Risiko-Heatmap & Förder-Badges
            "kpis": report.get("kpis", []),
            "benchmarks": report.get("benchmarks", {}),
            "timeline": report.get("timeline", {}),
            "risk_heatmap": report.get("risk_heatmap", []),
            # personal & glossary sections
            "ueber_mich_html": report.get("ueber_mich_html", ""),
            "glossary_html": report.get("glossary_html", ""),
            # QR code linking to the KI‑Sicherheit website
            # QR‑Codes are omitted in the Gold‑Standard version.
            "qr_code_uri": "",
            "funding_badges": report.get("funding_badges", []),
        }
        html = tmpl.render(**ctx)
    else:
        title = "KI-Readiness Report" if lang == "de" else "AI Readiness Report"
        html = f"""<!doctype html><html><head><meta charset="utf-8"><style>body{{font-family:Arial;padding:24px;}}</style></head>
<body><h1>{title} · {datetime.now().strftime("%Y-%m-%d")}</h1>
<div>{report.get("preface","")}</div>
<h2>Executive Summary</h2>{report.get("exec_summary_html","")}
<div style="display:flex;gap:24px;"><div style="flex:1">{report.get("quick_wins_html","")}</div>
<div style="flex:1">{report.get("risks_html","")}</div></div>
<h2>{'Nächste Schritte' if lang=='de' else 'Next steps'}</h2>{report.get("recommendations_html","") or report.get("roadmap_html","")}
{report.get("sections_html","")}
<hr><small>TÜV-zertifiziertes KI-Management © {datetime.now().year}: Wolf Hohl · E-Mail: kontakt@ki-sicherheit.jetzt</small></body></html>"""

    html = _inline_local_images(strip_code_fences(html))
    return {"html": html, "lang": lang, "score_percent": report.get("score_percent", 0),
            "meta": {"chapters":[k for k in ("executive_summary","vision","tools","foerderprogramme","roadmap","compliance","praxisbeispiel") if report.get(k)],
                     "one_pager": True}}
