# gpt_analyze.py — Block 1/5
"""
KI-Statusbericht (Gold-Standard) – Prompt-first + Live-Layer
- lädt Prompts aus ./prompts/de|en
- ruft OpenAI-LLM an (Prompts-first) und erzeugt narrative Abschnitte
- ergänzt Live-Kasten "Neu seit {Monat}" (Tavily/SerpAPI) gefiltert auf
  Branche × Unternehmensgröße × Hauptleistung × Standort
- optional: CSV-Seeds aus ./data/tools.csv und ./data/foerderprogramme.csv
- liefert ein Kontext-Dict für die Jinja-Templates (pdf_template*.html)
"""

from __future__ import annotations
import os, re, json, csv, time, logging, datetime as dt
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("analyze")

# --- Pfade/Dateien ---
ROOT = os.getcwd()
PROMPT_DIR = os.getenv("PROMPT_DIR", os.path.join(ROOT, "prompts"))
DATA_DIR   = os.path.join(ROOT, "data")
TOOLS_CSV  = os.path.join(DATA_DIR, "tools.csv")
FUNDING_CSV= os.path.join(DATA_DIR, "foerderprogramme.csv")

# --- OpenAI (LLM) ---
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME      = (os.getenv("SUMMARY_MODEL_NAME")
                   or os.getenv("GPT_MODEL_NAME")
                   or os.getenv("EXEC_SUMMARY_MODEL")
                   or "gpt-4o-mini")
TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.6"))
MAX_TOKENS  = int(os.getenv("GPT_MAX_TOKENS", "1600"))

# --- Live-Layer (via websearch_utils) ---
try:
    import websearch_utils as ws
except Exception:
    ws = None
    log.warning("websearch_utils not importable – Live-Kasten wird ggf. leer.")

# --- Monatsnamen für Stand/Hook ---
MONTHS_DE = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]
MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"]

def _month_year(lang: str = "de") -> str:
    today = dt.date.today()
    if (lang or "de").lower().startswith("de"):
        return f"{MONTHS_DE[today.month-1]} {today.year}"
    return f"{MONTHS_EN[today.month-1]} {today.year}"

# ----------------- kleine Utils -----------------
def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

def _lower(s: Optional[str]) -> str:
    return (s or "").strip().lower()

def _get_nested(body: Dict[str, Any], *keys: str, default: str = "") -> str:
    """
    Robust: sucht im body und in body['answers']/body['form'] (versch. Key-Varianten).
    """
    for k in keys:
        v = body.get(k)
        if isinstance(v, str) and _norm(v):
            return _norm(v)
    for container_key in ("answers","form","payload","data"):
        cont = body.get(container_key)
        if isinstance(cont, dict):
            for k in keys:
                for var in (k, k.lower(), k.upper(), k.capitalize()):
                    v = cont.get(var)
                    if isinstance(v, str) and _norm(v):
                        return _norm(v)
    return default

def _read_csv(path: str) -> List[Dict[str,str]]:
    out: List[Dict[str,str]] = []
    try:
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    out.append({k:(v or "").strip() for k,v in row.items()})
    except Exception as e:
        log.warning("CSV read failed %s: %s", path, e)
    return out

def _filter_by_context(items: List[Dict[str,str]], industry: str, size: str, location: str) -> List[Dict[str,str]]:
    if not items: return []
    i, s, l = _lower(industry), _lower(size), _lower(location)
    out = []
    for it in items:
        ind = _lower(it.get("industry") or it.get("branch") or "*")
        siz = _lower(it.get("company_size") or "*")
        reg = _lower(it.get("region") or "*")
        ok = True
        if ind != "*" and ind not in i: ok = False
        if ok and siz != "*" and siz not in s: ok = False
        if ok and reg != "*" and reg not in l: ok = False
        if ok: out.append(it)
    return out

def _html_table(rows: List[Dict[str,str]], cols: List[Tuple[str,str]]) -> str:
    if not rows: return ""
    th = "".join(f"<th>{title}</th>" for _, title in cols)
    trs = []
    for r in rows:
        tds = []
        for key, _title in cols:
            val = (r.get(key) or "").strip()
            if key.endswith("_url") and val:
                val = f'<a href="{val}" target="_blank" rel="noopener">{val}</a>'
            tds.append(f"<td>{val}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return f"""
    <div class="table-wrap">
      <table class="compact">
        <thead><tr>{th}</tr></thead>
        <tbody>{''.join(trs)}</tbody>
      </table>
    </div>
    """
# gpt_analyze.py — Block 2/5
# ----------------- Prompt-Loader -----------------
PROMPT_CACHE: Dict[Tuple[str,str], str] = {}

def _prompt_path_candidates(name: str, lang: str) -> List[str]:
    """
    Bevorzugt Deine Struktur:
      prompts/{lang}/{name}.md
      prompts/{lang}/{name}.txt
    Fallbacks:
      prompts/{name}_{lang}.md|.txt
      prompts/{name}.md|.txt
    """
    lang = (lang or "de").lower()
    cands = [
        os.path.join(PROMPT_DIR, lang, f"{name}.md"),
        os.path.join(PROMPT_DIR, lang, f"{name}.txt"),
        os.path.join(PROMPT_DIR, f"{name}_{lang}.md"),
        os.path.join(PROMPT_DIR, f"{name}_{lang}.txt"),
        os.path.join(PROMPT_DIR, f"{name}.md"),
        os.path.join(PROMPT_DIR, f"{name}.txt"),
    ]
    return cands

def load_prompt(name: str, lang: str, default: str = "") -> str:
    key = (name, lang)
    if key in PROMPT_CACHE:
        return PROMPT_CACHE[key]
    for p in _prompt_path_candidates(name, lang):
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    txt = f.read().strip()
                log.info("[PROMPT] %s <- %s", name, p)
                PROMPT_CACHE[key] = txt
                return txt
        except Exception as e:
            log.warning("[PROMPT] read failed %s: %s", p, e)
    if default:
        log.warning("[PROMPT] %s not found – using default", name)
    PROMPT_CACHE[key] = default
    return default

# ----------------- OpenAI Chat Helper -----------------
def _call_openai(messages: List[Dict[str, str]],
                 model: str = MODEL_NAME,
                 temperature: float = TEMPERATURE,
                 max_tokens: int = MAX_TOKENS) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")
    import httpx  # lokale Abhängigkeit vorhanden
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    t0 = time.time()
    r = httpx.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    js = r.json()
    txt = (js.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    log.info("[LLM] model=%s, %.2fs", model, time.time()-t0)
    return txt.strip()

def _json_from_text(raw: str) -> Dict[str, Any]:
    # tolerant JSON"‑Picker": versucht den äußersten {...}-Block zu extrahieren
    if not raw:
        return {}
    s, e = raw.find("{"), raw.rfind("}")
    if s >= 0 and e > s:
        chunk = raw[s:e+1]
        try:
            return json.loads(chunk)
        except Exception:
            pass
    # als Fallback: naive Heuristik → simple Felder herausholen
    return {}

# ----------------- Live-Layer (Tavily/SerpAPI via websearch_utils) -----------------
def _query_for(topic: str, lang: str, industry: str, size: str, main_offer: str, location: str) -> str:
    """
    Baut suchmaschinen‑taugliche Queries (Branche × Größe × Hauptleistung × Standort)
    topic: 'funding' | 'tools'
    """
    L = (lang or "de").lower()
    loc_en = {"deutschland":"germany","österreich":"austria","schweiz":"switzerland"}
    loc_key = location.lower()
    country = loc_en.get(loc_key, location)

    if topic == "funding":
        return (f"{industry} {main_offer} {size} "
                f"{'Förderung Zuschuss Programm' if L.startswith('de') else 'AI funding grant program'} "
                f"{country} 2025")
    # tools
    return (f"{industry} {main_offer} {size} "
            f"{'KI Werkzeuge Praxis' if L.startswith('de') else 'AI tools best practice'} "
            f"{country} 2025")

def _live_box(items: List[Dict[str,str]], lang: str) -> str:
    if not items:
        return ""
    month = _month_year(lang)
    title = f"Neu seit {month}" if (lang or "de").lower().startswith("de") else f"New since {month}"
    lis = []
    for it in items[:5]:
        t = (it.get("title") or "").strip()
        u = (it.get("url") or "").strip()
        s = (it.get("snippet") or "").strip()
        if not (t and u):
            continue
        lis.append(f'<div class="live-item"><div class="live-meta"></div><a href="{u}" target="_blank" rel="noopener"><strong>{t}</strong></a><div>{s}</div></div>')
    return f'<section class="live-box"><div class="live-title">{title}</div>{"".join(lis)}</section>'

def _search_links(query: str, n: int = 5) -> List[Dict[str,str]]:
    if ws is None:
        return []
    try:
        return ws.search_links(query=query, num_results=n)
    except Exception as e:
        log.warning("search_links failed: %s", e)
        return []
# gpt_analyze.py — Block 3/5
# ----------------- Narrative Defaults (Fallback, niemals leer) -----------------
def _fallback_paragraphs(lang: str) -> Dict[str, str]:
    if (lang or "de").lower().startswith("de"):
        return {
            "exec": ("Unternehmen erzielen schnelle, sichtbare Erfolge, wenn sichere Datenbasen, "
                     "vertrauenswürdige Automatisierung und fokussierte Pilotfälle zusammenspielen. "
                     "Die folgenden Seiten übersetzen das in eine machbare Abfolge."),
            "risks": ("Vermeiden Sie Tool‑Wildwuchs und Schatten‑Automatisierung. Einwilligung, Herkunft "
                      "und Nachvollziehbarkeit müssen sichtbar bleiben – besonders bei externen Daten."),
            "recs": ("Benennen Sie eine verantwortliche Person, definieren Sie zulässige Nutzung und "
                     "Rollout‑Meilensteine, und stellen Sie eine sichere interne Spielwiese bereit."),
            "road": ("90 Tage: Datenhygiene & ein geführter Pilot • 180 Tage: 2–3 Piloten skalieren, Governance live • "
                     "12 Monate: Plattform‑Entscheidungen, Integration, Training auf Breite."),
            "vision": ("Eine Praxis, in der Assistenten die repetitiven 20 % übernehmen, Teams sich auf Empathie und "
                       "Handwerk konzentrieren – und Kund:innen den Unterschied sofort spüren."),
            "game": ("Wissensgestützte Assistenten (RAG) mit eigenem Wissen, geschlossene Feedback‑Schleifen und "
                     "Echtzeitsignale steuern die Prioritäten."),
            "compliance": ("<p><strong>Compliance zuerst.</strong> Alle Empfehlungen orientieren sich an DSGVO, "
                           "ePrivacy‑Richtlinie, Digital Services Act und EU‑AI‑Act. Datenminimierung, Zweckbindung, "
                           "Transparenz und menschliche Aufsicht sind gesetzt.</p>")
        }
    else:
        return {
            "exec": ("You get fast, visible wins when secure data foundations, trustworthy automation and focused pilots "
                     "work together. The next pages turn this into a practical sequence."),
            "risks": ("Avoid tool sprawl and shadow automation. Keep consent, provenance and auditability visible—"
                      "especially when external data enters client‑facing outputs."),
            "recs": ("Name one responsible owner, define acceptable use and rollout gates, and provide a safe internal sandbox."),
            "road": ("90 days: data hygiene & one guided pilot • 180 days: scale 2–3 pilots, governance live • "
                     "12 months: platform choices, integration, training at scale."),
            "vision": ("A practice where assistants handle the repetitive 20%, teams focus on empathy and craft—"
                       "and clients feel the difference from day one."),
            "game": ("Retrieval‑augmented assistants connected to your knowledge, closed feedback loops and "
                     "real‑time signals guide prioritisation."),
            "compliance": ("<p><strong>Compliance first.</strong> We align with GDPR, ePrivacy Directive, the DSA and the EU AI Act. "
                           "Data minimisation, purpose limitation, transparency and human oversight are non‑negotiable.</p>")
        }

def _hook(industry: str, lang: str) -> str:
    if (lang or "de").lower().startswith("de"):
        return f"Kontext: {industry} – maßgeschneiderte Hinweise auf einen Blick."
    return f"Context: {industry} – tailored insights at a glance."

def _titles(lang: str) -> Tuple[str, str, str]:
    if (lang or "de").lower().startswith("de"):
        return "KI‑Statusbericht", "Strategische Vision", "Innovation & Gamechanger"
    return "AI Readiness Report", "Strategic Vision", "Innovation & Gamechanger"

def _cta(lang: str) -> str:
    return "Ihre Meinung zählt: Feedback geben (kurz)" if (lang or "de").lower().startswith("de") else "Your opinion matters: Give feedback (short)"

# --------------- Tools/Funding: Narrative + optional Tabelle + Live ---------------
def _narrative_from_csv_tools(tools: List[Dict[str,str]], lang: str) -> str:
    if not tools: return ""
    parts = []
    for t in tools[:6]:
        name = t.get("name","").strip()
        use  = t.get("use_case","").strip()
        who  = t.get("target","").strip()
        cost = t.get("cost_tier","").strip()
        one  = t.get("one_liner","").strip()
        sent = (f"<p><strong>{name}</strong> – {one or use}. "
                f"{'Geeignet für' if lang.startswith('de') else 'Suitable for'} {who}. "
                f"{'Kosten' if lang.startswith('de') else 'Cost'}: {cost}.</p>")
        parts.append(sent)
    return "\n".join(parts)

def _narrative_from_csv_funding(funds: List[Dict[str,str]], lang: str) -> str:
    if not funds: return ""
    parts = []
    for f in funds[:6]:
        name = f.get("name","").strip()
        what = f.get("what","").strip()
        who  = f.get("target","").strip()
        reg  = f.get("region","").strip()
        amt  = f.get("amount","").strip()
        url  = f.get("info_url","").strip()
        s = (f"<p><strong>{name}</strong> – {what}. "
             f"{'Zielgruppe' if lang.startswith('de') else 'Target'}: {who}. "
             f"{'Region' if lang.startswith('de') else 'Region'}: {reg}. "
             f"{'Förderhöhe' if lang.startswith('de') else 'Amount'}: {amt}. ")
        if url: s += f'<a href="{url}" target="_blank" rel="noopener">Details</a>.'
        s += "</p>"
        parts.append(s)
    return "\n".join(parts)

def _tables_from_seeds(industry: str, size: str, location: str, lang: str) -> Tuple[str, str]:
    tools = _filter_by_context(_read_csv(TOOLS_CSV), industry, size, location)
    funds = _filter_by_context(_read_csv(FUNDING_CSV), industry, size, location)

    table_tools = _html_table(tools[:10], [
        ("name","Tool"), ("use_case","Anwendung" if lang.startswith("de") else "Use case"),
        ("target","Zielgruppe" if lang.startswith("de") else "Target"),
        ("cost_tier","Kosten" if lang.startswith("de") else "Cost"), ("homepage_url","URL"),
    ])
    table_funds = _html_table(funds[:10], [
        ("name","Programm"), ("what","Förderinhalt" if lang.startswith("de") else "Scope"),
        ("target","Zielgruppe" if lang.startswith("de") else "Target"),
        ("amount","Förderhöhe" if lang.startswith("de") else "Amount"), ("info_url","Info"),
    ])
    return table_tools, table_funds
# gpt_analyze.py — Block 4/5
# ----------------- LLM-Orchestrierung (Prompts-first) -----------------
def _compose_and_call_llm(lang: str,
                          industry: str, size: str, main_offer: str, location: str) -> Dict[str, Any]:
    """
    Verknüpft Deine Prompts: prompt_prefix + (kapitelspezifisch) + prompt_additions + prompt_suffix
    und verlangt JSON: executive_summary, quick_wins, risks, recommendations, roadmap,
    vision, gamechanger, compliance, tools_html, funding_html
    """
    L = (lang or "de").lower()
    # Pflichtprompts (Kapitel)
    P = lambda n: load_prompt(n, L, "")
    prefix = P("prompt_prefix")
    suffix = P("prompt_suffix")
    add    = P("prompt_additions_de" if L.startswith("de") else "prompt_additions_en")

    # Kapitelprompts (genau Deine Dateien)
    p_exec  = P("executive_summary")
    p_qw    = P("quick_wins")
    p_risks = P("risks")
    p_recs  = P("recommendations")
    p_road  = P("roadmap")
    p_vision= P("vision")
    p_game  = P("gamechanger")
    p_comp  = P("compliance")
    p_tools = P("tools")
    # in beiden Sprachordnern heißt es 'foerderprogramme.md'
    p_fund  = P("foerderprogramme") or P("funding")

    # Kontextblock für das Modell
    brief = (
        f"Branche/Industry: {industry}\n"
        f"Unternehmensgröße/Company size: {size}\n"
        f"Hauptleistung/Hauptprodukt/Main offer: {main_offer}\n"
        f"Standort/Location: {location}\n"
        f"Schreibe warm, empathisch, ohne Listen und ohne Zahlenwerte. "
        f"Beziehe DSGVO, ePrivacy, DSA und EU‑AI‑Act narrativ ein."
    )

    sys_msg = ("Du bist eine professionelle Texter:in für KI-Statusberichte. "
               "Du lieferst klare, warme Absätze ohne Aufzählungen und ohne Zahlen.")

    messages = [{"role":"system","content": (prefix + "\n\n" + sys_msg if prefix else sys_msg)},
                {"role":"user","content": p_exec + "\n\n" + brief + ("\n\n" + add if add else "")},
                {"role":"user","content": p_qw},
                {"role":"user","content": p_risks},
                {"role":"user","content": p_recs},
                {"role":"user","content": p_road},
                {"role":"user","content": p_vision},
                {"role":"user","content": p_game},
                {"role":"user","content": p_comp},
                {"role":"user","content": p_tools},
                {"role":"user","content": p_fund},
                {"role":"user","content":
                    ("Antworte als JSON mit diesen Schlüsseln: "
                     "executive_summary, quick_wins, risks, recommendations, roadmap, "
                     "vision, gamechanger, compliance, tools_html, funding_html. "
                     "Kein Markdown, kein Codeblock.") + ("\n\n" + suffix if suffix else "")
                }]

    try:
        raw = _call_openai(messages, model=MODEL_NAME, temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
        data = _json_from_text(raw)
        if not isinstance(data, dict):
            data = {}
        return data
    except Exception as e:
        log.exception("LLM call failed: %s", e)
        return {}
# gpt_analyze.py — Block 5/5
def analyze_briefing(body: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """
    Gibt ein Kontext-Dict zurück – keine Jinja-Tags im Text.
    """
    L = (lang or "de").lower()
    # Kontext aus Fragebogen
    industry    = _get_nested(body, "branche","industry","sector","Branche", default="Beratung")
    main_offer  = _get_nested(body, "hauptleistung","hauptprodukt","main_product","main_service","Hauptleistung/Hauptprodukt", default="Beratung & Projekte")
    size        = _get_nested(body, "unternehmensgroesse","unternehmensgröße","company_size","Mitarbeitende","size", default="KMU")
    location    = _get_nested(body, "standort","ort","plz","location","country","Country","Ort", default="Deutschland")
    company     = _get_nested(body, "company","firma","Unternehmen","Company", default="")

    # 1) Prompts-first → LLM
    data = _compose_and_call_llm(L, industry, size, main_offer, location)

    # 2) Live-Layer (gefiltert auf Branche × Größe × Hauptleistung × Standort)
    live_html_funding = ""
    live_html_tools   = ""
    if ws is not None:
        q_f = _query_for("funding", L, industry, size, main_offer, location)
        q_t = _query_for("tools",   L, industry, size, main_offer, location)
        links_f = _search_links(q_f, n=int(os.getenv("SEARCH_MAX_RESULTS","5") or 5))
        links_t = _search_links(q_t, n=int(os.getenv("SEARCH_MAX_RESULTS","5") or 5))
        live_html_funding = _live_box(links_f, L)
        live_html_tools   = _live_box(links_t, L)

    # 3) Seeds als optionale Tabellen (wenn vorhanden)
    table_tools, table_funds = _tables_from_seeds(industry, size, location, L)

    # 4) Fallbacks, falls LLM leer liefert (niemals „nackt“)
    fb = _fallback_paragraphs(L)
    exec_summary = data.get("executive_summary") or fb["exec"]
    quick_wins   = data.get("quick_wins") or (fb["exec"] if L.startswith("en") else "Beginnen Sie mit einer sauberen Datenstrecke und einem ersten Pilotfall.")
    risks        = data.get("risks") or fb["risks"]
    recs         = data.get("recommendations") or fb["recs"]
    roadmap      = data.get("roadmap") or fb["road"]
    vision       = data.get("vision") or fb["vision"]
    gamechanger  = data.get("gamechanger") or fb["game"]
    compliance   = data.get("compliance") or fb["compliance"]

    # 5) Tools/Funding-HTML zusammensetzen
    tools_html   = (data.get("tools_html") or "") + live_html_tools + (table_tools or "")
    funding_html = (data.get("funding_html") or "") + live_html_funding + (table_funds or "")

    title, vision_title, game_title = _titles(L)

    ctx = {
        "title": title,
        "lang": L,
        "company": company,
        "industry": industry,
        "main_offer": main_offer,
        "company_size": size,
        "location": location,
        "industry_hook": _hook(industry, L),  # 1‑Satz‑Hook über Executive Summary
        "executive_summary": exec_summary,
        "quick_wins": quick_wins,
        "risks": risks,
        "recommendations": recs,
        "roadmap": roadmap,
        "vision_title": vision_title,
        "vision": vision,
        "game_title": game_title,
        "gamechanger": gamechanger,
        "compliance_html": compliance,
        "funding_html": funding_html,
        "tools_html": tools_html,
        "stand_datum": _month_year(L),
        "footer_cta": _cta(L),
        "report_version": "gold-std-prompts-first-2025-09-18",
        # Debug Light (nur im Dict, nicht im PDF sichtbar)
        "model_used": MODEL_NAME,
        "prompt_dir": PROMPT_DIR
    }
    return ctx

# Manuelle CLI-Probe (lokal)
if __name__ == "__main__":
    sample = {"branche":"Beratung","hauptleistung":"KI‑Automatisierung","unternehmensgroesse":"10‑49","standort":"Deutschland","company":"Beispiel GmbH","lang":"de"}
    out = analyze_briefing(sample, "de")
    print(json.dumps({k: (v[:100]+"…" if isinstance(v,str) and len(v)>100 else v) for k,v in out.items()}, ensure_ascii=False, indent=2))
