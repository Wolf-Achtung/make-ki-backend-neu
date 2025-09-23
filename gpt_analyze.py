# gpt_analyze.py — Gold Standard (FULL)
# LLM für: Executive Summary, Risks, Recommendations, Roadmap, Vision
# Deterministisch für: Quick Wins, EU‑AI‑Act, Tools, Förderung, Chancen/Risiken-Fallback, Gamechanger
from __future__ import annotations
import os, re, json
from pathlib import Path
from datetime import datetime as _dt
from typing import Dict, Any, List, Optional

from prompts_loader import load_registry, get_prompt, ensure_unzipped

try:
    from openai import OpenAI
    _OPENAI = OpenAI()
except Exception:
    _OPENAI = None

BASE_DIR = Path(__file__).resolve().parent
PARTIAL_DIRS = [BASE_DIR / "templates" / "partials", BASE_DIR / "partials"]
DATA_DIRS = [BASE_DIR / "data", BASE_DIR]

# ---- Story-Killer: blockt Anekdoten/„Mehr erfahren“/Fantasie-Tools ----
_STORY_PATTERNS = [
    r"\bIn\s+einem\s+kleinen\s+Familienunternehmen\b",
    r"\bStellen\s+Sie\s+sich\b",
    r"\bPraxisbeispiel\b",
    r"\bDer\s+Beratungswald\b",
    r"\bEs\s+war\s+einmal\b",
    r"\bMehr\s+erfahren\b",
]
_FANTASY_TOOL_PATTERNS = [
    r"\bIdeation\s+Assistant\b", r"\bProject\s+Harmony\b", r"\bComms\s+Connect\b",
    r"\bPrivacyGuard\s+AI\b", r"\bSecureChat\s+AI\b", r"\bDataSafe\s+AI\b"
]

def _kill_story(html: str) -> str:
    if not html: return ""
    t = re.sub(r"<[^>]+>", " ", html or "")
    for pat in _STORY_PATTERNS + _FANTASY_TOOL_PATTERNS:
        if re.search(pat, t, flags=re.IGNORECASE):
            return ""
    if re.search(r"%(?!\d)|€(?!\d)", t):
        return ""
    return html.strip()

# ---- helpers ----
def _read_text(p: Path) -> str:
    try: return p.read_text(encoding="utf-8")
    except Exception: return ""

def _find_in(dirs: List[Path], name: str) -> Optional[Path]:
    for d in dirs:
        p = d / name
        if p.exists(): return p
    return None

def _load_json_any(name: str) -> List[Dict[str,Any]]:
    p = _find_in(DATA_DIRS, name)
    if not p: return []
    try: return json.loads(_read_text(p)) or []
    except Exception: return []

def _load_partial(name: str, fallback="") -> str:
    p = _find_in(PARTIAL_DIRS, name)
    return _read_text(p) if p else fallback

# ---- deterministic tables ----
def _render_tools(max_items=12) -> str:
    rows = _load_json_any("tool_whitelist.json")
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    head = "<tr><th>Kategorie</th><th>Option</th><th>Daten/Deployment</th><th>Hinweise</th></tr>"
    body = []
    for r in rows[:max_items]:
        name = r.get("name","—")
        if r.get("sovereign"): name += " <span class='badge'>souverän</span>"
        body.append(f"<tr><td>{r.get('category','—')}</td><td>{name}</td><td>{r.get('data_residency','—')}</td><td>{r.get('notes','')}</td></tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def _render_funding(max_items=8) -> str:
    rows = _load_json_any("funding_whitelist.json")
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    head = "<tr><th>Programm</th><th>Region</th><th>Zielgruppe</th><th>Leistung/Status</th><th>Quelle</th><th>Stand</th></tr>"
    body = []
    for r in rows[:max_items]:
        perf = r.get("benefit","—")
        status = r.get("status","")
        if status and status not in ("aktiv","laufend","kontingentabhängig"):
            perf = f"{perf} ({status})"
        as_of = r.get("as_of","—")
        src = r.get("source","—")
        link = f"<a href='https://{src}'>{src}</a>" if src and src != "—" else "—"
        body.append(f"<tr><td>{r.get('name','—')}</td><td>{r.get('region','—')}</td><td>{r.get('target','—')}</td><td>{perf}</td><td>{link}</td><td>{as_of}</td></tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

# ---- deterministic summary/roadmap fallback ----
def _build_summary(body: dict, lang: str="de") -> dict:
    branche = str(body.get("branche") or body.get("industry") or "").lower()
    size    = str(body.get("unternehmensgroesse") or body.get("company_size") or "").lower()
    opp, risk = [], []
    if "beratung" in branche or "consult" in branche:
        opp += ["Self‑Service‑Assistants (Vier‑Augen‑Prinzip)", "Abrechnungs‑/Report‑Automatisierung", "Qualitäts‑Prompts für Standardtexte"]
        risk += ["Datenqualität & Versionierung", "Fehlende KI‑Policy/Owner", "Tool‑Wildwuchs ohne DPA"]
    if size in ("solo","1","einzel","freelance"):
        opp += ["Vorlagen‑Bibliothek (10 Prompts)", "1 No‑Code‑Automation (z. B. PDF→Buchhaltung)"]
        risk += ["Single‑Point‑Dependency", "Kein Vier‑Augen‑Prinzip"]
    if not opp:  opp  = ["Kommunikations‑Assistants mit Freigabeschleife", "Automatisierung eines manuellen Schritts"]
    if not risk: risk = ["Datenklassifizierung & Zugriffe ungeklärt", "Rollen/Owner für KI‑Einsatz fehlen"]
    if lang != "de":
        opp  = ["Self‑service assistants with HITL", "Automate one manual step", "Prompt library (10)"]
        risk = ["Data quality & access unclear", "No AI policy / no owners"]
    return {"opportunities": opp[:7], "risks": risk[:7]}

def _build_roadmap(body: dict, lang: str="de") -> dict:
    if lang == "de":
        q90  = ["Dateninventur (Top‑10, Owner, Zugriffe)", "Policy‑Mini‑Set (2 S.) + Bestätigung", "Prompt‑Bibliothek (10)", "1 No‑Code‑Automation"]
        q180 = ["2 Piloten (Kommunikation + Backoffice)", "Logging & HITL", "DPA‑Check & Anbieterregister", "Owner je Use‑Case"]
        q365 = ["Skalierung der Piloten", "Schulung & Evals", "Retention/Löschregeln live", "EU‑AI‑Act‑Review/DSFA"]
    else:
        q90  = ["Data inventory (top‑10, owners, access)", "2‑page AI policy + receipt", "Prompt library (10)", "1 no‑code automation"]
        q180 = ["2 pilots (customer comms + backoffice)", "Logging & HITL", "DPA check & vendor register", "Assign owners per use case"]
        q365 = ["Scale pilots", "Training & evals", "Retention/deletion live", "EU AI Act review/DPIA"]
    return {"q90": q90, "q180": q180, "q365": q365}

# ---- LLM helpers ----
def _llm_block(title: str, prompt_key: str, ctx: Dict[str,Any], lang: str, reg: Dict[str,str]) -> str:
    if _OPENAI is None: return ""
    sys = ("Sie sind zertifizierte:r KI‑Manager:in. Schreiben Sie kurze, fachlich saubere Absätze "
           "für Geschäftsführung/KMU. Ton: professionell, beratend, konstruktiv, optimistisch, per Sie. "
           "Nur <p> und <h3>, keine Listen/Tabellen, keine Anekdoten, keine Metaphern, keine Produktnamen.")
    if lang != "de":
        sys = ("You are a certified AI manager. Write concise, factual paragraphs for senior leadership. "
               "Tone: professional, advisory, constructive, optimistic. Only <p> and <h3>; no lists/tables; "
               "no anecdotes or product names.")
    hint = get_prompt(reg, prompt_key, lang)
    payload = {"title": title, "hint": hint, "ctx": ctx}
    try:
        r = _OPENAI.chat.completions.create(
            model=os.getenv("GPT_MODEL_NAME","gpt-4o-mini"),
            temperature=float(os.getenv("GPT_TEMPERATURE","0.2")),
            messages=[{"role":"system","content":sys},
                      {"role":"user","content":json.dumps(payload, ensure_ascii=False)}]
        )
        html = (r.choices[0].message.content or "").strip()
        html = re.sub(r"</?(ul|ol|li|table|thead|tbody|tr|th|td)[^>]*>", "", html, flags=re.I)
        return _kill_story(html)
    except Exception:
        return ""

# ---- Company norm ----
def _company(body: Dict[str,Any]) -> Dict[str,Any]:
    loc = str(body.get("bundesland") or body.get("ort") or body.get("city") or body.get("location") or "—").strip()
    mapping = {"be":"Berlin","by":"Bayern","nw":"Nordrhein‑Westfalen","bw":"Baden‑Württemberg"}
    if loc.lower() in mapping: loc = mapping[loc.lower()]
    return {
        "name": (body.get("company") or body.get("unternehmen") or body.get("firma") or "—"),
        "industry": (body.get("branche") or body.get("industry") or "—").title(),
        "size": (body.get("unternehmensgroesse") or body.get("company_size") or "—").title(),
        "location": loc.title(),
    }

# ---- Gamechanger ----
def _gamechanger(body: dict, lang: str) -> str:
    try:
        from gamechanger_features import GAMECHANGER_FEATURES
        from gamechanger_blocks import build_gamechanger_blocks
        from innovation_intro import INNOVATION_INTRO
        return build_gamechanger_blocks(body, GAMECHANGER_FEATURES)
    except Exception:
        return ""

# ---- PUBLIC ----
def analyze_briefing(body: Dict[str,Any], lang: str="de") -> Dict[str,Any]:
    ensure_unzipped()
    reg = load_registry()

    if not isinstance(body, dict):
        try: body = json.loads(str(body))
        except Exception: body = {}
    lang = "de" if str(lang).lower().startswith("de") else "en"

    company = _company(body)
    meta = {"date": _dt.now().strftime("%d.%m.%Y") if lang=="de" else _dt.now().strftime("%Y-%m-%d"),
            "stand": _dt.now().strftime("%Y-%m-%d"), "year": _dt.now().year, "owner": "Wolf Hohl"}

    # Deterministisch
    quick_wins_html = _load_partial("quick_wins_de.html" if lang=="de" else "quick_wins_en.html", "<p>—</p>")
    eu_ai_act_html  = _load_partial("eu_ai_act_de.html"  if lang=="de" else "eu_ai_act_en.html",  "<p>—</p>")
    tools_html      = _render_tools()
    funding_html    = _render_funding()
    summary_fallback= _build_summary(body, lang)
    roadmap_fallback= _build_roadmap(body, lang)

    ctx = {"company": company, "inputs": body}

    # LLM‑Kapitel (kurze Absätze, „per Sie“, ohne Listen)
    exec_html  = _llm_block("Executive Summary", "exec_summary", ctx, lang, reg)
    risks_html = _llm_block("Risiken", "risks", ctx, lang, reg)
    recs_html  = _llm_block("Empfehlungen", "recommendations", ctx, lang, reg)
    rmap_html  = _llm_block("Roadmap", "roadmap", ctx, lang, reg)
    vision_html= _llm_block("Vision", "vision", ctx, lang, reg)

    # Falls LLM nichts liefert, bleiben Fallbacks bestehen (Summary/Roadmap)
    summary = summary_fallback
    roadmap = roadmap_fallback

    gamechanger_html = _gamechanger(body, lang)

    return {
        "company": company,
        "meta": meta,
        "summary": summary,
        "roadmap": roadmap,
        "quick_wins_html": quick_wins_html,
        "eu_ai_act_html": eu_ai_act_html,
        "tools_html": tools_html,
        "funding_html": funding_html,
        "executive_summary_html": exec_html,
        "risks_html": risks_html,
        "recommendations_html": recs_html,
        "roadmap_html": rmap_html,
        "vision_html": vision_html or "",
        "gamechanger_html": gamechanger_html
    }
# ------- Backwards-Compat SHIM (für app/routers/report.py) -------
def build_report_payload(body: dict, lang: str = "de"):
    """
    Kompatibilität zu älteren Routern:
    - Erwartet ehemals ein Payload-Objekt für das Rendern.
    - Gibt jetzt das Template-Only-Dict von analyze_briefing zurück.
    """
    try:
        return analyze_briefing(body or {}, lang=lang)
    except Exception:
        # niemals crashen – leeres, aber gültiges Template-Context-Dict zurückgeben
        return {
            "company": {"name":"—","industry":"—","size":"—","location":"—"},
            "meta": {"date":"", "stand":"", "year":"", "owner":""},
            "summary": {"opportunities":[],"risks":[]},
            "roadmap": {"q90":[],"q180":[],"q365":[]},
            "quick_wins_html":"", "eu_ai_act_html":"", "tools_html":"", "funding_html":"",
            "executive_summary_html":"", "risks_html":"", "recommendations_html":"",
            "roadmap_html":"", "vision_html":"", "gamechanger_html":""
        }
