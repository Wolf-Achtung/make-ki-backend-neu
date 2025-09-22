
"""
gpt_analyze.py — Gold-Standard Analyzer (deterministische Basis + optionale LLM-Blöcke)
- Template-Only friendly: liefert ausschließlich ein Daten-Dict
- Story-Killer + Sprachwächter (DE default)
- Whitelist-Only Tabellen (Tools/Förderung), Förder-Filter nach Bundesland (inkl. Kürzel-Mapping)
- Appendix STRICT: nur manifest.json
- Optionale LLM: Executive Summary + Gamechanger (hart begrenzt, 1000 Zeichen, keine Stories)
- Optionale Tavily-News (Callout), wenn TAVILY_API_KEY und ALLOW_TAVILY=1
"""
import os, json, re, datetime, html
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------- Config / ENV ----------
ROOT = Path(os.getcwd())
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"

LLM_MODE = os.getenv("LLM_MODE", "hybrid")  # 'off'|'hybrid'
GPT_MODEL_NAME = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))
APPENDIX_STRICT = os.getenv("APPENDIX_STRICT", "1") == "1"
MAX_CHARS = int(os.getenv("MAX_CHARS", "1000"))

ALLOW_TAVILY = os.getenv("ALLOW_TAVILY", "0") == "1"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ---------- Utilities ----------
def _load_json_any(fname: str) -> Any:
    for p in [DATA_DIR / fname, ROOT / fname]:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None

def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def _clamp_text(s: str, max_chars: int = MAX_CHARS) -> str:
    if not s: return s
    if len(s) <= max_chars: return s
    cut = s[:max_chars]
    # bis zum letzten Satzende
    m = re.search(r"[.!?)](?=[^.!?)]*$)", cut)
    if m: cut = cut[:m.end()]
    return cut.rstrip() + " …"

def _sanitize_p(text: str) -> str:
    # Entferne Codefences & Markdown-Triple-Backticks
    t = text.replace("```html","```").replace("```HTML","```")
    while "```" in t: t = t.replace("```","")
    return t

def _plain_text(html_text: str) -> str:
    return re.sub(r"<[^>]+>", " ", html_text)

def _reject_if_english(text: str, lang: str) -> bool:
    if lang.startswith("de"):
        return bool(re.search(r"\b(the|and|of|in the|for example|organisation)\b", text, re.I))
    if lang.startswith("en"):
        return False
    return False

STORY_BLOCK = re.compile(r"\b(Ein Unternehmen|In the\s|Consider a|Imagine a|For instance, a|Once\s)\b", re.I)

# ---------- LLM (optional) ----------
def llm_generate(prompt: str, system: str = "", max_tokens: int = 600) -> str:
    if LLM_MODE == "off": return ""
    try:
        import openai  # type: ignore
        client = openai.OpenAI()
        msgs = []
        if system: msgs.append({"role":"system","content":system})
        msgs.append({"role":"user","content":prompt})
        resp = client.chat.completions.create(
            model=GPT_MODEL_NAME,
            messages=msgs,
            temperature=GPT_TEMPERATURE,
            max_tokens=max_tokens
        )
        text = resp.choices[0].message.content or ""
        return text
    except Exception as e:
        return ""

# ---------- Tavily (optional) ----------
def tavily_search(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return []
    try:
        import httpx
        headers = {"Content-Type":"application/json","X-Tavily-API-Key":TAVILY_API_KEY}
        payload = {"query":query, "max_results":max_results}
        with httpx.Client(timeout=15.0) as c:
            r = c.post("https://api.tavily.com/search", headers=headers, json=payload)
            if 200 <= r.status_code < 300:
                j = r.json()
                return j.get("results", [])
    except Exception:
        return []
    return []

# ---------- Whitelist-Tabellen ----------
def render_tools_from_whitelist(max_items: int = 14) -> str:
    rows = _load_json_any("tool_whitelist.json") or []
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    head = "<tr><th>Kategorie</th><th>Option</th><th>Badge</th><th>Daten/Deployment</th><th>Hinweise</th></tr>"
    body = []
    for r in rows[:max_items]:
        badge = f"<span class='badge souveraen'>souverän</span>" if r.get("sovereign") else ""
        cols = [r.get("category","—"), r.get("name","—"), badge, r.get("hosting","—"), r.get("note","—")]
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

BUNDESLAND_MAP = {"be":"Berlin","by":"Bayern","bw":"Baden-Württemberg","hh":"Hamburg","he":"Hessen","bb":"Brandenburg","mv":"Mecklenburg-Vorpommern","ni":"Niedersachsen","nw":"Nordrhein-Westfalen","rp":"Rheinland-Pfalz","sl":"Saarland","sn":"Sachsen","st":"Sachsen-Anhalt","sh":"Schleswig-Holstein","th":"Thüringen","hb":"Bremen"}

def render_funding_from_whitelist(max_items: int = 12, bundesland: str = "") -> str:
    rows = _load_json_any("funding_whitelist.json") or []
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    bl_norm = (bundesland or "").strip().lower()
    bl_norm = BUNDESLAND_MAP.get(bl_norm, bl_norm)
    def _keep(r):
        reg = (r.get("region","") or "").strip().lower()
        if not bl_norm: return True
        if reg in ("bund","de","deutschland","eu","europe","europa"): return True
        return bl_norm.lower() in reg
    filtered = [r for r in rows if _keep(r)]
    if not filtered: filtered = rows  # zur Not bundesweite
    head_cols = ["Programm","Region","Zielgruppe","Leistung/Status","Quelle"]
    if any("as_of" in r for r in filtered): head_cols.append("Stand")
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in head_cols) + "</tr>"
    body=[]
    for r in filtered[:max_items]:
        perf = r.get("benefit","—")
        status = r.get("status","")
        if status and status not in ("aktiv","laufend","kontingentabhängig"):
            perf = f"{perf} ({status})"
        cols=[r.get("name","—"), r.get("region","—"), r.get("target","—"), perf, r.get("source","—")]
        if "as_of" in r: cols.append(r.get("as_of",""))
        body.append("<tr>"+ "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    html_table = f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"
    return html_table

# ---------- Appendix Strict / Manifest ----------
def _manifest(lang: str) -> Dict[str, Any]:
    path = PROMPTS_DIR / "manifest.json"
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _appendix_blocks(lang: str) -> List[Dict[str,str]]:
    m = _manifest(lang)
    blocks: List[Dict[str,str]] = []
    if APPENDIX_STRICT and m:
        items = m.get("appendix", [])
        base = PROMPTS_DIR / ("de" if lang.startswith("de") else "en")
        for it in items:
            if isinstance(it, dict):
                file = it.get("file"); title = it.get("title","")
            else:
                file = str(it); title = ""
            p = base / file
            if p.is_file():
                txt = _sanitize_p(_load_text(p))
                blocks.append({"title": title or p.stem.replace("_"," ").title(), "html": f"<div class='section'>{txt}</div>"})
        return blocks

    # Default (falls kein manifest.json): konkrete 4–5 Blöcke
    base = PROMPTS_DIR / ("de" if lang.startswith("de") else "en")
    defaults = ["prompt_policy.md","best_practices.md","compliance_checklist.md","faq_startpaket.md","glossar_kurz.md"]
    for name in defaults:
        p = base / name
        if p.is_file():
            txt = _sanitize_p(_load_text(p))
            blocks.append({"title": p.stem.replace("_"," ").title(), "html": f"<div class='section'>{txt}</div>"})
    return blocks

# ---------- Gamechanger (LLM, hart begrenzt) ----------
def _gamechanger_llm(company: Dict[str,Any], lang: str) -> str:
    branche = company.get("branche") or company.get("industry") or ""
    groesse = company.get("unternehmensgroesse") or company.get("size") or ""
    leistung = company.get("hauptleistung") or company.get("main_service") or ""
    sys = "Sie sind ein nüchterner, präziser Unternehmensberater. Per Sie. Keine Anekdoten. Max. 900 Zeichen. Kein Marketing-Sprech."
    if lang.startswith("en"):
        sys = "You are a precise management consultant. Formal 'you'. No anecdotes. Max 900 characters. No hype."
    prompt = f"""
Erarbeiten Sie einen kompakten 'Innovation & Gamechanger'-Vorschlag
für Branche: {branche}, Hauptleistung: {leistung}, Unternehmensgröße: {groesse}.
Vorgaben:
- 1 Leitidee mit klarem Nutzen (operativ + finanziell), 3 stichpunktartige Next Steps.
- Keine Anekdoten, keine Story-Wendungen, keine 'Imagine/Consider'.
- Keine Platzhalter ('{{','}}').
- Sprache: {'Deutsch' if lang.startswith('de') else 'English'}, per Sie, sachlich.
Ausgabeformat (HTML):
<h3>Innovation & Gamechanger</h3>
<p>[Leitidee, 3-4 Sätze]</p>
<ul><li>[Next Step 1]</li><li>[Next Step 2]</li><li>[Next Step 3]</li></ul>
"""
    txt = llm_generate(prompt.strip(), system=sys, max_tokens=500) or ""
    txt = _sanitize_p(txt)
    if STORY_BLOCK.search(txt) or _reject_if_english(_plain_text(txt), lang):
        return ""  # verwerfen
    return _clamp_text(txt, MAX_CHARS)

# ---------- News Callout (Tavily) ----------
def _news_callout(company: Dict[str,Any], lang: str) -> str:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return ""
    branche = company.get("branche") or company.get("industry") or ""
    loc = company.get("location") or company.get("standort") or ""
    q = f"aktuelle Nachrichten KI Einführung {branche} Unternehmen Deutschland {loc}".strip()
    results = tavily_search(q, max_results=3)
    if not results: return ""
    items = []
    for r in results:
        title = html.escape(r.get("title",""))
        source = html.escape(r.get("source",""))
        items.append(f"<li>{title} <span class='muted'>({source})</span></li>")
    return "<div class='callout'><strong>Realtime‑Hinweise (News):</strong><ul>"+ "".join(items) + "</ul></div>"

# ---------- Hauptfunktion ----------------------------------------------------
def analyze_briefing(body: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """
    Liefert ein Daten-Dict für die Jinja-Templates.
    """
    lang = (lang or "de").lower()
    company = body.get("company") if isinstance(body.get("company"), dict) else body
    # Normalisiere Standort
    loc = (company.get("standort") or company.get("location") or "").strip().lower()
    company["location"] = BUNDESLAND_MAP.get(loc, company.get("location") or loc or "")
    # Meta
    meta = {
        "company_name": company.get("unternehmen") or company.get("company") or "—",
        "branche": company.get("branche") or company.get("industry") or "—",
        "groesse": company.get("unternehmensgroesse") or company.get("size") or "—",
        "standort": company.get("location") or "—",
        "date": datetime.date.today().strftime("%d.%m.%Y"),
        "as_of": datetime.date.today().isoformat(),
    }

    # ---- Deterministische Basistexte (kurz, DE/EN) ----
    def det_short(section: str) -> str:
        if lang.startswith("de"):
            presets = {
                "quickwins": "Start mit Dateninventur (10 Quellen), Policy‑Mini‑Seite (Zwecke/No‑Gos/Freigaben), Prompt‑Bibliothek (10 Aufgaben). Eine Schleife automatisieren (4‑Augen‑Check).",
                "risks": "Risiken: Datenqualität, Compliance, Schatten‑IT. Absicherung: Datenverantwortliche benennen, AVV/Standorte prüfen, Logging & Evaluations festlegen, klare Freigaben.",
                "recs": "Empfehlung: Wiederkehrendes automatisieren, Governance leichtgewichtig starten (Rollen, Policy, Logging), Qualifizierung in Schlüsselrollen.",
                "roadmap": "0–3 M: Inventur/Policy/Quick‑Wins. 3–6 M: 2 Piloten + Evaluationskriterien. 6–12 M: Skalierung, Schulungen, Controlling‑KPIs.",
            }
        else:
            presets = {
                "quickwins": "Start with a light data inventory, a one‑page policy, and a prompt library (10 tasks). Automate one loop with four‑eyes check.",
                "risks": "Risks: data quality, compliance, shadow IT. Mitigation: assign data owners, check DPAs/locations, set logging & evaluations.",
                "recs": "Recommendation: automate repetitive work, lightweight governance (roles, policy, logging), upskill key roles.",
                "roadmap": "0–3 m: inventory/policy/quick wins. 3–6 m: 2 pilots + evaluation gates. 6–12 m: scale, training, KPIs.",
            }
        return presets.get(section, "")

    # ---- LLM: Executive Summary (optional) ----
    exec_sum = ""
    if LLM_MODE != "off":
        sys = "Sie sind präzise, sachlich, per Sie. Max. 900 Zeichen. Keine Anekdoten."
        if lang.startswith("en"):
            sys = "You are precise and succinct. Formal 'you'. Max 900 characters. No anecdotes."
        prompt = f"Erstellen Sie eine Executive Summary (3–5 Sätze) für Branche={meta['branche']}, Größe={meta['groesse']}, Standort={meta['standort']}."
        exec_sum = llm_generate(prompt, system=sys, max_tokens=450)
        exec_sum = _sanitize_p(exec_sum)
        if STORY_BLOCK.search(exec_sum) or _reject_if_english(_plain_text(exec_sum), lang):
            exec_sum = ""

    if not exec_sum:
        # deterministische Kurzfassung
        exec_sum = det_short("recs")

    # ---- Weitere Kernsektionen deterministisch (LLM aus) ----
    risks = det_short("risks")
    recs = det_short("recs")
    roadmap = det_short("roadmap")
    quickwins = det_short("quickwins")

    # ---- Whitelist-Tabellen ----
    tools_html = render_tools_from_whitelist()
    funding_html = render_funding_from_whitelist(bundesland=meta["standort"])

    # ---- Gamechanger (optional LLM) ----
    gamechanger_html = _gamechanger_llm(company, lang) if LLM_MODE != "off" else ""
    news_html = _news_callout(company, lang)

    # ---- Appendix (strict) ----
    appendix_blocks = _appendix_blocks(lang)
    appendix_html = "".join(f"<h3>{html.escape(b['title'])}</h3>{b['html']}" for b in appendix_blocks)

    # ---- Kürzen & Sprache prüfen ----
    exec_sum = _clamp_text(exec_sum)
    risks = _clamp_text(risks)
    recs = _clamp_text(recs)
    roadmap = _clamp_text(roadmap)
    quickwins = _clamp_text(quickwins)

    for k in [exec_sum, risks, recs, roadmap, quickwins, gamechanger_html, appendix_html]:
        if _reject_if_english(_plain_text(k or ""), lang) and lang.startswith("de"):
            # hartes Fallback auf deterministische Texte
            exec_sum = det_short("recs")
            risks = det_short("risks")
            recs = det_short("recs")
            roadmap = det_short("roadmap")
            quickwins = det_short("quickwins")
            gamechanger_html = ""

    # ---- Ergebnisdict ----
    result = {
        "meta": meta,
        "executive_summary": exec_sum,
        "quick_wins": quickwins,
        "risks": risks,
        "recommendations": recs,
        "roadmap": roadmap,
        "tools_table": tools_html,
        "funding_table": funding_html,
        "gamechanger": gamechanger_html + news_html,
        "appendix": appendix_html,
    }
    return result
