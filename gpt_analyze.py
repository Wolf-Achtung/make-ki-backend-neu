# gpt_analyze.py — Gold-Standard Analyzer — 2025-09-23
import os, json, csv, datetime, re
from pathlib import Path
import httpx

ALLOW_TAVILY = os.getenv("ALLOW_TAVILY","0").lower() in ("1","true")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY","")
LLM_MODE = os.getenv("LLM_MODE","off").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
LOGO_URL = os.getenv("LOGO_URL","")

def _today_iso(): return datetime.date.today().isoformat()

# ---------- Utilities ----------
def _read_text(p: Path) -> str:
    try: return p.read_text(encoding="utf-8")
    except Exception: return ""
def _load_prompts(lang: str) -> str:
    base = Path("prompts") / lang
    if not base.is_dir(): return ""
    manifest = base/"manifest.json"
    files = []
    if manifest.is_file():
        try:
            m = json.loads(_read_text(manifest) or "{}")
            files = [base/f for f in m.get("files", [])]
        except Exception: pass
    if not files:
        files = sorted(base.glob("*.md"))
    parts = []
    for f in files:
        txt = _read_text(f).strip()
        if txt: parts.append(f"<h3>{f.stem.replace('_',' ').title()}</h3><div class='section'><p>{txt}</p></div>")
    return "\n".join(parts)

def _table_html(headers, rows):
    def cell(x): 
        return (x if isinstance(x,str) else str(x)).replace("\n"," ").strip()
    th = "".join(f"<th>{cell(h)}</th>" for h in headers)
    tb = "".join("<tr>"+ "".join(f"<td>{cell(v)}</td>" for v in r) + "</tr>" for r in rows)
    return f"<table class='table'><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table>"

def _guess_csv(pattern_keywords):
    root = Path("data")
    if not root.is_dir(): return []
    cands = []
    for p in root.glob("*.csv"):
        name = p.name.lower()
        if any(k in name for k in pattern_keywords): cands.append(p)
    return cands

def _load_csv_rows(p: Path, max_rows=50):
    try:
        rows = []
        with p.open("r", encoding="utf-8") as f:
            r = csv.reader(f)
            headers = next(r, [])
            for i, row in enumerate(r):
                if i >= max_rows: break
                rows.append(row)
        return headers, rows
    except Exception:
        return [], []

# ---------- Static (deterministic) content ----------
def _deterministic_quickwins(lang):
    if lang.startswith("de"):
        return "Start mit Dateninventur (10 Quellen), Policy‑Mini‑Seite, Prompt‑Bibliothek, eine Schleife automatisieren (4‑Augen‑Check)."
    return "Kick off with a data inventory, a mini policy page, prompt library, and automate one loop (4‑eyes check)."

def _deterministic_risks(lang):
    return "Risiken: Datenqualität, Compliance, Schatten‑IT. Absicherung: Data Owner, AVV/Standorte, Logging/Evaluations, klare Freigaben." if lang.startswith("de") \
        else "Risks: data quality, compliance, shadow IT. Mitigation: data owners, DPA/locations, logging/evaluation, clear approvals."

def _deterministic_recos(lang):
    return "Automatisieren Sie wiederkehrende Arbeiten, starten Sie leichtgewichtige Governance und qualifizieren Sie Schlüsselrollen." if lang.startswith("de") \
        else "Automate recurring work, start lightweight governance and upskill key roles."

def _deterministic_roadmap(lang):
    return "0–3 M: Inventur/Policy/Quick‑Wins. 3–6 M: 2 Piloten + Evaluation. 6–12 M: Skalierung, Schulungen, KPIs." if lang.startswith("de") \
        else "0–3 mo: Inventory/Policy/Quick Wins. 3–6 mo: 2 pilots + evaluation. 6–12 mo: scale, training, KPIs."

def _fallback_tools_table(lang):
    headers = ["Kategorie","Option","Badge","Daten/Deployment","Hinweise"] if lang.startswith("de") \
        else ["Category","Option","Badge","Data/Deployment","Notes"]
    rows = [
        ["LLM/Assistant (EU)","Aleph Alpha","souverän","EU (DE)","EU‑Standorte"],
        ["Local UI/Orchestration","OpenWebUI / Ollama","souverän","self‑host","lokal/prototypen" if lang.startswith("de") else "local/prototypes"],
    ]
    return _table_html(headers, rows)

def _fallback_funding_table(lang):
    headers = ["Programm","Region","Zielgruppe","Leistung/Status","Quelle","Stand"] if lang.startswith("de") \
        else ["Program","Region","Target","Benefit/Status","Source","As of"]
    rows = [
        ["BAFA – Beratungsförderung","Bund","KMU","Zuschuss Beratung (laufend)","bafa.de", _today_iso()[:7]],
        ["Digital Jetzt (BMWK)","Bund","KMU","Investitionen & Qualifizierung (laufend)","bmwk.de", _today_iso()[:7]],
    ]
    return _table_html(headers, rows)

# ---------- Realtime via Tavily ----------
async def _tavily(q: str) -> list:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return []
    url = "https://api.tavily.com/search"
    try:
        async with httpx.AsyncClient(timeout=16.0) as c:
            r = await c.post(url, json={"api_key": TAVILY_API_KEY, "query": q, "search_depth":"advanced", "include_domains":[], "max_results":5})
            if r.status_code == 401:
                # kill switch to avoid log spam
                os.environ["ALLOW_TAVILY"] = "0"
                return []
            rj = r.json()
            results = rj.get("results", []) or rj.get("response", [])
            items = []
            for it in results[:5]:
                title = it.get("title") or it.get("url") or "Link"
                urlx = it.get("url") or ""
                items.append(f"<li><a href='{urlx}'>{title}</a></li>")
            return items
    except Exception:
        return []

async def _realtime_blocks(company: dict, lang: str) -> dict:
    blocks = {"regwatch": "", "funding_realtime": "", "funding_deadlines": "", "tools_news": ""}
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return blocks
    bran = (company.get("branche") or "KMU").lower()
    q_reg = "EU AI Act compliance update site:europa.eu" if not lang.startswith("de") else "EU AI Act Update Compliance site:europa.eu deutsch"
    q_fund = "Förderung KMU KI Fristen 2025 Deutschland" if lang.startswith("de") else "grant funding SME AI deadlines Germany 2025"
    q_tools = "enterprise AI tooling roadmap news 2025 site:blog.google|openai.com|meta.com|microsoft.com"

    reg = await _tavily(q_reg)
    fund = await _tavily(q_fund)
    tools = await _tavily(q_tools)

    if reg: blocks["regwatch"] = "<h3>Regwatch</h3><ul>"+ "".join(reg) +"</ul>"
    if fund: blocks["funding_realtime"] = "<h3>Realtime‑Hinweise</h3><ul>"+ "".join(fund) +"</ul>"
    if tools: blocks["tools_news"] = "<h3>Tools‑News</h3><ul>"+ "".join(tools) +"</ul>"
    # Deadlines (heuristisch aus fund)
    if fund: blocks["funding_deadlines"] = "<h3>Wichtige Fristen</h3><p>Bitte beachten Sie die Einreichungsfenster der o. g. Programme.</p>" if lang.startswith("de") else "<h3>Key Deadlines</h3><p>Please check the submission windows of listed programs.</p>"
    return blocks

# ---------- LLM helpers ----------
async def _openai_chat(prompt: str) -> str:
    if LLM_MODE == "off" or not OPENAI_API_KEY: return ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions",
                             headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                             json={"model":"gpt-4o-mini","messages":[{"role":"user","content":prompt}],"temperature":0.7})
            if r.status_code//100 == 2:
                data = r.json()
                return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""
    return ""

def _visionary_default(lang, company_name):
    if lang.startswith("de"):
        return f"<p><strong>Visionäre Empfehlung:</strong> Bauen Sie ein kleines, nachweisbar sicheres <em>KI‑Enablement‑Center</em> auf (2–3 Muster‑Workflows, Messung & Governance), das Fachbereiche in 6 Wochen sichtbar entlastet und als Blaupause für die Skalierung dient.</p>"
    return f"<p><strong>Visionary Recommendation:</strong> Build a small, verifiably safe <em>AI Enablement Center</em> (2–3 lighthouse workflows, measurement & governance) that relieves teams within 6 weeks and becomes a blueprint for scaling.</p>"

# ---------- Public entry ----------
def analyze_briefing(body: dict, lang: str = "de") -> dict:
    # Meta
    company = body.get("company") or {}
    user_email = (body.get("_user_email") or body.get("to") or "")
    meta = {
        "company_name": company.get("unternehmen") or company.get("company") or "—",
        "branche": company.get("branche") or "—",
        "groesse": company.get("unternehmensgroesse") or "—",
        "standort": company.get("location") or company.get("standort") or "—",
        "date": _today_iso(),
        "as_of": datetime.date.today().isoformat(),
        "created_by": user_email,
        "logo_url": LOGO_URL
    }

    # Deterministic parts
    quick = _deterministic_quickwins(lang)
    risks = _deterministic_risks(lang)
    recos = _deterministic_recos(lang)
    road = _deterministic_roadmap(lang)

    # Data tables
    tools_tbl, fund_tbl = "", ""
    tools_csv = _guess_csv(["tool","whitelist","stack"])
    fund_csv = _guess_csv(["fund","förder","grant","bafa","bmwk"])

    if tools_csv:
        h, rows = _load_csv_rows(tools_csv[0])
        tools_tbl = _table_html(h or ["Kategorie","Option","Badge","Daten/Deployment","Hinweise"], rows) if rows else _fallback_tools_table(lang)
    else:
        tools_tbl = _fallback_tools_table(lang)

    if fund_csv:
        h, rows = _load_csv_rows(fund_csv[0])
        fund_tbl = _table_html(h or (["Programm","Region","Zielgruppe","Leistung/Status","Quelle","Stand"] if lang.startswith("de") else ["Program","Region","Target","Benefit/Status","Source","As of"]), rows) if rows else _fallback_funding_table(lang)
    else:
        fund_tbl = _fallback_funding_table(lang)

    # Realtime
    import anyio
    regwatch = funding_rt = deadlines = tools_news = ""
    if ALLOW_TAVILY and TAVILY_API_KEY:
        try:
            res = anyio.run(_realtime_blocks, company, lang)
            regwatch = res.get("regwatch",""); funding_rt = res.get("funding_realtime",""); deadlines = res.get("funding_deadlines",""); tools_news = res.get("tools_news","")
        except Exception:
            pass

    # LLM: ES + Visionary + Gamechanger
    es = ""
    vision = ""
    gamechanger = ""
    if LLM_MODE != "off" and OPENAI_API_KEY:
        prompt_es = ( "Schreibe eine prägnante Executive Summary (max. 120 Wörter) für einen KI-Statusbericht eines KMU. "
                      f"Firma: {meta['company_name']}, Branche: {meta['branche']}, Größe: {meta['groesse']}, Standort: {meta['standort']}. "
                      "Fokus: Sicherheit (EU AI Act, DSGVO), schnelle Wirkung (Quick Wins), skalierbare Roadmap. "
                      "Ton: seriös, optimistisch, konkret." )
        prompt_vision = ( "Formuliere eine <Visionäre Empfehlung> (max. 80 Wörter) für einen KI-Statusbericht. "
                          f"Firma/Branche: {meta['company_name']} / {meta['branche']}. "
                          "Sie soll ambitioniert, aber machbar sein, konkrete Wirkung in 6–12 Monaten entfalten und messbar sein." )
        prompt_gc = ( "Formuliere 3–5 Bulletpoints <Innovation & Gamechanger> für das Unternehmen (max. 120 Wörter total).")
        es = anyio.run(_openai_chat, prompt_es) or ""
        vision = anyio.run(_openai_chat, prompt_vision) or ""
        gamechanger = anyio.run(_openai_chat, prompt_gc) or ""
    if not es:
        es = ("Diese Executive Summary fasst Ausgangslage und nächste Schritte zusammen: "
              "Dateninventur, Policy, erste Automatisierungen und eine skalierbare Roadmap mit belastbaren Nachweisen (EU AI Act/DSGVO).")
    if not vision:
        vision = _visionary_default(lang, meta["company_name"])
    if not gamechanger:
        gamechanger = "<ul><li>Schnelles Enablement‑Center (2–3 Workflows)</li><li>Messbare Effizienzgewinne</li><li>Saubere Nachweise (Logs/Evaluations)</li></ul>"

    appendix = _load_prompts("de" if lang.startswith("de") else "en")

    return {
        "meta": {
            "company_name": meta["company_name"], "branche": meta["branche"], "groesse": meta["groesse"],
            "standort": meta["standort"], "date": meta["date"], "as_of": meta["as_of"],
            "created_by": meta["created_by"], "logo_url": meta["logo_url"]
        },
        "executive_summary": es,
        "visionary_recommendation": vision,
        "quick_wins": quick,
        "risks": risks,
        "recommendations": recos,
        "roadmap": road,
        "tools_table": tools_tbl,
        "tools_news": tools_news,
        "funding_table": fund_tbl,
        "funding_realtime": funding_rt,
        "funding_deadlines": deadlines,
        "regwatch": regwatch,
        "gamechanger": gamechanger,
        "appendix": appendix
    }
