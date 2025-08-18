
import os
import re
import json
import yaml
import zipfile
from datetime import datetime
from typing import Dict, Any, Optional

import pandas as pd
from openai import OpenAI

# Optional domain features (kept from your version)
try:
    from gamechanger_blocks import build_gamechanger_blocks
    from gamechanger_features import GAMECHANGER_FEATURES
    from innovation_intro import INNOVATION_INTRO
except Exception:
    build_gamechanger_blocks = lambda data, feats: []
    GAMECHANGER_FEATURES = {}
    INNOVATION_INTRO = {}

# Optional web search
try:
    from websearch_utils import serpapi_search
except Exception:
    serpapi_search = lambda query, num_results=5: []

client = OpenAI()

# ---------- ZIP bootstrap ----------

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

# ---------- IO helpers ----------

def load_yaml(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ---------- Minimal templating ----------

def render_template(template: str, context: dict) -> str:
    """
    Very small renderer for {{ key }} and {{ key | join(', ') }}.
    """
    def replace_join(m: re.Match) -> str:
        key = m.group(1)
        sep = m.group(2)
        val = context.get(key.strip(), "")
        if isinstance(val, list):
            return sep.join(str(v) for v in val)
        return str(val)

    rendered = re.sub(
        r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}",
        replace_join,
        template,
    )

    def replace_simple(m: re.Match) -> str:
        key = m.group(1)
        val = context.get(key.strip(), "")
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val)

    rendered = re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, rendered)
    return rendered

# ---------- Context builders ----------

def build_context(data: dict, branche: str, lang: str = "de") -> dict:
    """
    Load sector context YAML and merge questionnaire data.
    """
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not os.path.exists(context_path):
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(context_path) if os.path.exists(context_path) else {}
    context.update(data or {})
    # copyright defaults for footer
    context.setdefault("copyright_year", datetime.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")
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
        context["websearch_links_foerder"] = serpapi_search(f"aktuelle Förderprogramme {branche} {projektziel} Deutschland {year}", num_results=5)
        context["websearch_links_tools"]   = serpapi_search(f"aktuelle KI-Tools {branche} Deutschland {year}", num_results=5)
    except Exception:
        context["websearch_links_foerder"] = []
        context["websearch_links_tools"] = []
    return context

# ---------- Formatting helpers ----------

def fix_encoding(text: str) -> str:
    return (
        (text or "")
        .replace("�", "-")
        .replace("–", "-")
        .replace("“", '"')
        .replace("”", '"')
        .replace("’", "'")
    )

def ensure_html(text: str, lang: str = "de") -> str:
    """
    Heuristically convert plain/markdown-ish into simple HTML if no tags are present.
    Keeps existing HTML unchanged.
    """
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t  # looks like HTML already
    lines = [ln.rstrip() for ln in t.splitlines() if ln.strip()]
    html = []
    in_ul = False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>"); in_ul = True
            item = re.sub(r"^[-•*]\s+", "", ln).strip()
            html.append(f"<li>{item}</li>")
        elif re.match(r"^#{1,3}\s+", ln):
            level = len(ln) - len(ln.lstrip("#"))
            txt = ln[level:].strip()
            level = min(3, max(1, level))
            html.append(f"<h{level}>{txt}</h{level}>")
        else:
            if in_ul:
                html.append("</ul>"); in_ul = False
            html.append(f"<p>{ln}</p>")
    if in_ul:
        html.append("</ul>")
    return "\n".join(html)

# ---------- Prompt builder ----------

def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
    """
    Load the prompt for chapter+lang and render variables. Enforce a scannable, HTML-only output style.
    """
    search_paths = [
        f"prompts/{lang}/{chapter}.md",
        f"prompts_unzip/{lang}/{chapter}.md",
        f"{lang}/{chapter}.md",
        f"{lang}_unzip/{lang}/{chapter}.md",
        f"de_unzip/de/{chapter}.md",
        f"en_unzip/en/{chapter}.md",
        f"en_mod/en/{chapter}.md",
    ]
    prompt_text = None
    for p in search_paths:
        if os.path.exists(p):
            try:
                prompt_text = load_text(p)
                break
            except Exception:
                continue
    if prompt_text is None:
        # final attempt (may fail)
        prompt_text = load_text(f"prompts/{lang}/{chapter}.md")

    try:
        prompt = render_template(prompt_text, context)
    except Exception as e:
        prompt = f"[Prompt-Rendering-Fehler: {e}]\n{prompt_text}"

    if str(lang).lower().startswith("de"):
        style = (
            "\n\n---\n"
            "Gib die Antwort AUSSCHLIESSLICH als gültiges HTML zurück (ohne <html>-Wrapper), "
            "nutze <h3>, <p>, <ul>, <ol>, <table> wo sinnvoll. "
            "Keine Meta-Kommentare, keine Vorrede.\n"
            "- Was tun? (3–5 präzise Maßnahmen, Imperativ)\n"
            "- Warum? (max. 2 Sätze, Impact)\n"
            "- Nächste 3 Schritte (Checkliste)\n"
        )
    else:
        style = (
            "\n\n---\n"
            "Return the answer as VALID HTML ONLY (no <html> wrapper). "
            "Use <h3>, <p>, <ul>, <ol>, <table> where helpful. "
            "No meta, no preface.\n"
            "- What to do (3–5 precise actions)\n"
            "- Why (max 2 sentences, impact)\n"
            "- Next 3 steps (checklist)\n"
        )
    return prompt + style

# ---------- OpenAI calls ----------

def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float] = None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

def gpt_generate_section(data, branche, chapter, lang="de"):
    # language normalization
    lang = data.get("lang") or data.get("language") or data.get("sprache") or lang

    # context
    context = build_context(data, branche, lang)
    projektziel = data.get("projektziel", "")
    context = add_websearch_links(context, branche, projektziel)
    context = add_innovation_features(context, branche, data)

    # checklist (optional)
    if not context.get("checklisten"):
        md_path = "data/check_ki_readiness.md"
        if os.path.exists(md_path):
            with open(md_path, encoding="utf-8") as f:
                md = f.read()
            ctx_list = []
            for ln in md.splitlines():
                s = ln.strip()
                if s.startswith("#"):
                    h = s.lstrip("#").strip()
                    ctx_list.append(f"<h3>{h}</h3>")
                elif s.startswith("- "):
                    ctx_list.append(f"<li>{s[2:].strip()}</li>")
            if ctx_list:
                context["checklisten"] = "<ul>" + "\n".join([x for x in ctx_list if x.startswith("<li>")]) + "</ul>"
            else:
                context["checklisten"] = ""
        else:
            context["checklisten"] = ""

    prompt = build_masterprompt(chapter, context, lang)

    default_model = os.getenv("GPT_MODEL_NAME", "gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter == "executive_summary" else default_model

    section_text = _chat_complete(
        messages=[
            {"role": "system", "content": (
                "Du bist ein TÜV-zertifizierter KI-Manager, KI-Strategieberater, "
                "Datenschutz- und Fördermittel-Experte. "
                "Liefere präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
            ) if str(lang).lower().startswith("de") else (
                "You are a TÜV-certified AI manager and strategy consultant. "
                "Deliver precise, actionable, up-to-date, sector-relevant content as HTML."
            )},
            {"role": "user", "content": prompt},
        ],
        model_name=model_name,
        temperature=None,
    )

    section_html = ensure_html(fix_encoding(section_text), lang=lang)

    # limit large HTML tables for tools/funding to 5 rows
    if chapter in {"tools", "foerderprogramme"}:
        try:
            parts = section_html.split("<tr>")
            if len(parts) > 6:
                header = parts[0]
                rows = parts[1:6]
                tail = ""
                if "</table>" in parts[-1]:
                    tail = "</table>"
                section_html = "<tr>".join([header] + rows) + tail
        except Exception:
            pass

    return section_html

# ---------- Distillation helpers ----------

def _distill_two_lists(html_src: str, lang: str, title_a: str, title_b: str):
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if str(lang).lower().startswith("de"):
        sys = "Du extrahierst präzise Listen aus HTML."
        usr = (
            f"Extrahiere aus folgendem HTML zwei kompakte Listen als HTML:\n"
            f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n"
            f"- 4–6 Punkte je Liste\n"
            f"- Kurze, imperative Formulierungen\n"
            f"- Gib AUSSCHLIESSLICH validiertes HTML zurück.\n\n"
            f"HTML:\n{html_src}"
        )
    else:
        sys = "You extract precise lists from HTML."
        usr = (
            f"From the HTML, extract two compact lists as HTML:\n"
            f"<h3>{title_a}</h3><ul>…</ul>\n<h3>{title_b}</h3><ul>…</ul>\n"
            f"- 4–6 bullets each\n"
            f"- short, imperative\n"
            f"- return VALID HTML ONLY.\n\n"
            f"HTML:\n{html_src}"
        )
    try:
        out = _chat_complete(
            messages=[{"role":"system", "content": sys}, {"role":"user","content": usr}],
            model_name=model,
            temperature=0.2,
        )
        return ensure_html(out, lang)
    except Exception:
        return ""

def distill_quickwins_risks(source_html: str, lang: str = "de") -> Dict[str, str]:
    html = _distill_two_lists(source_html, lang, "Quick Wins", "Hauptrisiken" if str(lang).lower().startswith("de") else "Key Risks")
    if not html:
        return {"quick_wins_html": "", "risks_html": ""}
    m = re.split(r"(?i)<h3[^>]*>", html)
    if len(m) >= 3:
        a = "<h3>" + m[1]
        b = "<h3>" + m[2]
        if "Quick Wins" in a or "Quick" in a:
            return {"quick_wins_html": a, "risks_html": b}
        else:
            return {"quick_wins_html": b, "risks_html": a}
    return {"quick_wins_html": html, "risks_html": ""}

def distill_recommendations(source_html: str, lang: str = "de") -> str:
    model = os.getenv("SUMMARY_MODEL_NAME", os.getenv("GPT_MODEL_NAME", "gpt-5"))
    if str(lang).lower().startswith("de"):
        sys = "Du destillierst Maßnahmen aus HTML."
        usr = (
            "Extrahiere aus dem HTML 5–8 konkrete Maßnahmen als geordnete Liste <ol>. "
            "Imperativ, jeweils 1 Zeile. Gib nur HTML zurück.\n\n"
            f"HTML:\n{source_html}"
        )
    else:
        sys = "You distill actions from HTML."
        usr = (
            "Extract 5–8 actionable steps as an ordered list <ol>. "
            "Imperative, one line each. Return HTML only.\n\n"
            f"HTML:\n{source_html}"
        )
    try:
        out = _chat_complete(
            messages=[{"role":"system","content":sys},{"role":"user","content":usr}],
            model_name=model,
            temperature=0.2,
        )
        return ensure_html(out, lang)
    except Exception:
        return ""

# ---------- Scoring ----------

def calc_score_percent(data: dict) -> int:
    score = 0
    max_score = 35
    try:
        score += int(data.get("digitalisierungsgrad", 1))
    except Exception:
        score += 1
    auto_map = {"sehr_niedrig": 0, "eher_niedrig": 1, "mittel": 3, "eher_hoch": 4, "sehr_hoch": 5}
    score += auto_map.get(str(data.get("automatisierungsgrad", "")).lower(), 0)
    pap_map = {"0-20": 1, "21-50": 2, "51-80": 4, "81-100": 5}
    score += pap_map.get(str(data.get("prozesse_papierlos", "0-20")), 0)
    know_map = {"keine": 0, "grundkenntnisse": 1, "mittel": 3, "fortgeschritten": 4, "expertenwissen": 5}
    score += know_map.get(str(data.get("ki_knowhow", "keine")).lower(), 0)
    try:
        score += int(data.get("risikofreude", 1))
    except Exception:
        score += 1
    percent = max(0, min(100, int((score / max_score) * 100)))
    return percent

# ---------- Preface ----------

def generate_preface(lang: str = "de", score_percent: Optional[float] = None) -> str:
    if str(lang).lower().startswith("de"):
        preface = (
            "<p>Dieses Dokument fasst die Ergebnisse Ihres KI-Readiness-Checks zusammen "
            "und bietet individuelle Empfehlungen für die nächsten Schritte. "
            "Es basiert auf Ihren Angaben und berücksichtigt aktuelle gesetzliche Vorgaben, "
            "Fördermöglichkeiten und technologische Entwicklungen.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Ihr aktueller KI-Readiness-Score liegt bei {score_percent:.0f}%.</b> "
                "Dieser Wert zeigt, wie gut Sie auf den Einsatz von KI vorbereitet sind.</p>"
            )
        return preface
    else:
        preface = (
            "<p>This document summarises your AI readiness results and provides "
            "tailored next steps. It is based on your input and considers legal "
            "requirements, funding options and current AI developments.</p>"
        )
        if score_percent is not None:
            preface += (
                f"<p><b>Your current AI readiness score is {score_percent:.0f}%.</b> "
                "It indicates how prepared you are to adopt AI.</p>"
            )
        return preface

# ---------- Full report generation ----------

def gpt_generate_section_html(data, branche, chapter, lang="de") -> str:
    html = gpt_generate_section(data, branche, chapter, lang=lang)
    return ensure_html(html, lang)

def generate_full_report(data: dict, lang: str = "de") -> dict:
    """
    Produce chapter HTML AND template-ready fields:
      exec_summary_html, quick_wins_html, risks_html, recommendations_html,
      roadmap_html, sections_html, (plus optional foerderprogramme/tools/compliance/praxisbeispiel),
      preface, score_percent.
    """
    branche = (data.get("branche") or "default").lower()
    data["score_percent"] = calc_score_percent(data)

    wants_funding = str(data.get("interesse_foerderung", "")).lower() in {"ja", "unklar"}
    chapters = ["executive_summary", "tools"] + (["foerderprogramme"] if wants_funding else []) + ["roadmap", "compliance", "praxisbeispiel"]

    out: Dict[str, str] = {}
    full_text_blocks = []

    for chap in chapters:
        try:
            html = gpt_generate_section_html(data, branche, chap, lang=lang)
            out[chap] = html
            full_text_blocks.append(html)
        except Exception as e:
            out[chap] = f"<p>[Fehler in Kapitel {chap}: {e}]</p>"

    # Preface
    out["preface"] = generate_preface(lang=lang, score_percent=data.get("score_percent"))

    # Distill Quick Wins & Risks from executive_summary + roadmap fallback
    src_for_qr = (out.get("executive_summary") or "") + "\n\n" + (out.get("roadmap") or "")
    q_r = distill_quickwins_risks(src_for_qr, lang=lang)
    out["quick_wins_html"] = q_r.get("quick_wins_html", "")
    out["risks_html"] = q_r.get("risks_html", "")

    # Recommendations distilled from roadmap (+ compliance as fallback)
    src_for_rec = (out.get("roadmap") or "") + "\n\n" + (out.get("compliance") or "")
    out["recommendations_html"] = distill_recommendations(src_for_rec, lang=lang) or (out.get("roadmap") or "")

    # Roadmap block
    out["roadmap_html"] = out.get("roadmap", "")

    # Exec summary passthrough
    out["exec_summary_html"] = out.get("executive_summary", "")

    # Aggregate remaining sections into sections_html
    sections_html_parts = []
    for k, label in [("tools", "Tools"), ("foerderprogramme", "Förderprogramme" if str(lang).lower().startswith("de") else "Funding"), ("compliance", "Compliance"), ("praxisbeispiel", "Praxisbeispiel" if str(lang).lower().startswith("de") else "Case Study")]:
        if out.get(k):
            sections_html_parts.append(f"<h2>{label}</h2>\n{out[k]}")
    out["sections_html"] = "\n\n".join(sections_html_parts)

    # Also return score_percent for the score ring
    out["score_percent"] = data["score_percent"]
    return out

# Backwards-compatible alias
analyze_full_report = generate_full_report
