
"""
gpt_analyze.py — Gold-Standard Analyzer v4
Neu in v4:
- Tavily-Caching (Datei-Cache mit TTL; ENV: TAVILY_CACHE_TTL, TAVILY_CACHE_DIR)
- Regulatory-Watch (EU-AI-Act / DSGVO / branchenspez. Aufsicht) als Callout
- Funding-Deadline-Radar (Einreichungsfenster/Fristen) als Callout
- Gestärktes Vendor-Release-Signal (Pricing/EU-Hosting/Security Advisories)
- Fortführung: Realtime-Förder-Statushinweise, Tools-News, Gamechanger-Fallbacks
"""
import os, json, re, datetime, html, hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.getcwd())
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"
CACHE_DIR = Path(os.getenv("TAVILY_CACHE_DIR", ".cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
TAVILY_CACHE_TTL = int(os.getenv("TAVILY_CACHE_TTL", "3600"))  # Sekunden

# ---- ENV / Modelle ----------------------------------------------------------
LLM_MODE = os.getenv("LLM_MODE") or ("hybrid" if os.getenv("ENABLE_LLM_SECTIONS","1") in ("1","true","True") else "off")
GPT_MODEL_NAME = os.getenv("EXEC_SUMMARY_MODEL") or os.getenv("SUMMARY_MODEL_NAME") or os.getenv("GPT_MODEL_NAME") or "gpt-4o-mini"
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))
APPENDIX_STRICT = os.getenv("APPENDIX_STRICT", "1") == "1"
MAX_CHARS = int(os.getenv("MAX_CHARS", "1000"))
ALLOW_TAVILY = os.getenv("ALLOW_TAVILY", "0") == "1"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# ---- Utilities --------------------------------------------------------------
def _load_json_any(fname: str) -> Any:
    for p in [DATA_DIR / fname, ROOT / fname]:
        if p.is_file():
            try: return json.loads(p.read_text(encoding="utf-8"))
            except Exception: pass
    return None

def _load_text(path: Path) -> str:
    try: return path.read_text(encoding="utf-8")
    except Exception: return ""

def _sanitize_p(text: str) -> str:
    if text is None: return ""
    t = str(text).replace("```html","```").replace("```HTML","```")
    while "```" in t: t = t.replace("```","")
    return t

def _plain_text(html_text: str) -> str:
    return re.sub(r"<[^>]+>", " ", html_text or "")

def _clamp_text(s: str, max_chars: int = MAX_CHARS) -> str:
    if not s: return s
    if len(s) <= max_chars: return s
    cut = s[:max_chars]
    m = re.search(r"[.!?)](?=[^.!?)]*$)", cut)
    if m: cut = cut[:m.end()]
    return cut.rstrip() + " …"

def _reject_if_english(text: str, lang: str) -> bool:
    if lang.startswith("de"):
        return bool(re.search(r"\b(the|and|of|in the|for example|organisation|organization)\b", text or "", re.I))
    return False

STORY_BLOCK = re.compile(r"\b(Ein Unternehmen|In the\s|Consider a|Imagine a|For instance, a|Once\s)\b", re.I)

# ---- LLM (optional) ---------------------------------------------------------
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
        return resp.choices[0].message.content or ""
    except Exception:
        return ""

# ---- Tavily (cached) --------------------------------------------------------
def _cache_key(query: str) -> Path:
    h = hashlib.sha1((query or "").encode("utf-8")).hexdigest()
    return CACHE_DIR / f"tavily_{h}.json"

def tavily_search(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """Raw Tavily call (no cache)"""
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return []
    try:
        import httpx
        headers = {"Content-Type":"application/json","X-Tavily-API-Key":TAVILY_API_KEY}
        payload = {"query": query, "max_results": max_results}
        with httpx.Client(timeout=15.0) as c:
            r = c.post("https://api.tavily.com/search", headers=headers, json=payload)
            if 200 <= r.status_code < 300:
                j = r.json()
                return j.get("results", [])
    except Exception:
        return []
    return []

def tavily_cached_search(query: str, max_results: int = 3, ttl_seconds: int = TAVILY_CACHE_TTL) -> List[Dict[str, Any]]:
    p = _cache_key(query + f"|{max_results}")
    try:
        if p.is_file():
            age = datetime.datetime.now().timestamp() - p.stat().st_mtime
            if age < ttl_seconds:
                return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    res = tavily_search(query, max_results=max_results)
    try:
        p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return res

def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        d = urlparse(url).netloc
        return d.replace("www.","")
    except Exception:
        return ""

# ---- Whitelists / Bundesländer ---------------------------------------------
BUNDESLAND_MAP = {
    "be":"Berlin","berlin":"Berlin",
    "by":"Bayern","bayern":"Bayern",
    "bw":"Baden-Württemberg","baden-württemberg":"Baden-Württemberg","baden wuerttemberg":"Baden-Württemberg","badenwuerttemberg":"Baden-Württemberg",
    "hh":"Hamburg","hamburg":"Hamburg",
    "he":"Hessen","hessen":"Hessen",
    "bb":"Brandenburg","brandenburg":"Brandenburg",
    "mv":"Mecklenburg-Vorpommern","mecklenburg-vorpommern":"Mecklenburg-Vorpommern","mecklenburg vorpommern":"Mecklenburg-Vorpommern",
    "ni":"Niedersachsen","niedersachsen":"Niedersachsen",
    "nw":"Nordrhein-Westfalen","nordrhein-westfalen":"Nordrhein-Westfalen","nrw":"Nordrhein-Westfalen",
    "rp":"Rheinland-Pfalz","rheinland-pfalz":"Rheinland-Pfalz",
    "sl":"Saarland","saarland":"Saarland",
    "sn":"Sachsen","sachsen":"Sachsen",
    "st":"Sachsen-Anhalt","sachsen-anhalt":"Sachsen-Anhalt",
    "sh":"Schleswig-Holstein","schleswig-holstein":"Schleswig-Holstein",
    "th":"Thüringen","thueringen":"Thüringen","thuringen":"Thüringen",
    "hb":"Bremen","bremen":"Bremen"
}

def _tools_rows() -> List[Dict[str,Any]]:
    return _load_json_any("tool_whitelist.json") or []

def _funding_rows() -> List[Dict[str,Any]]:
    # merges 'funding_whitelist.json' and optional 'funding_states.json'
    base = _load_json_any("funding_whitelist.json") or []
    states = _load_json_any("funding_states.json") or []
    return base + states

def render_tools_from_whitelist(max_items: int = 18) -> str:
    rows = _tools_rows()
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    head = "<tr><th>Kategorie</th><th>Option</th><th>Badge</th><th>Daten/Deployment</th><th>Hinweise</th></tr>"
    body = []
    for r in rows[:max_items]:
        badge = f"<span class='badge souveraen'>souverän</span>" if r.get("sovereign") else ""
        cols = [r.get("category","—"), r.get("name","—"), badge, r.get("hosting","—"), r.get("note","—")]
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def render_funding_from_whitelist(max_items: int = 20, bundesland: str = "") -> str:
    rows = _funding_rows()
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    bl_norm = (bundesland or "").strip().lower()
    bl_norm = BUNDESLAND_MAP.get(bl_norm, bl_norm)
    def _keep(r):
        reg = (r.get("region","") or "").strip().lower()
        if not bl_norm: return True
        if reg in ("bund","de","deutschland","eu","europe","europa"): return True
        return bl_norm.lower() in reg
    filtered = [r for r in rows if _keep(r)]
    if not filtered: filtered = rows
    head_cols = ["Programm","Region","Zielgruppe","Leistung/Status","Quelle"]
    if any("as_of" in r for r in filtered): head_cols.append("Stand")
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in head_cols) + "</tr>"
    body=[]
    for r in filtered[:max_items]:
        perf = r.get("benefit","—")
        status = r.get("status","")
        if status: perf = f"{perf} ({status})"
        cols=[r.get("name","—"), r.get("region","—"), r.get("target","—"), perf, r.get("source","—")]
        if "as_of" in r: cols.append(r.get("as_of",""))
        body.append("<tr>"+ "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

# ---- Realtime-Callouts ------------------------------------------------------
FUNDING_STATUS_KEYWORDS = [
    "Antragstopp","ausgesetzt","geschlossen","Stopp","Einstellung",
    "Kontingent erschöpft","wieder geöffnet","Frist verlängert","verlängert","läuft wieder",
    "Programmende","Deadline","Einreichung","Antragsfrist","Bewilligung gestoppt"
]
DEADLINE_PAT = re.compile(r"\b(?:(?:bis|deadline|frist)\s*[:\-]?\s*)(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)", re.I)

def _funding_realtime_callout(bundesland: str, lang: str) -> str:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return ""
    rows = _funding_rows()
    if not rows: return ""
    bl_norm = (bundesland or "").strip().lower()
    bl_norm = BUNDESLAND_MAP.get(bl_norm, bl_norm)
    cand = [r for r in rows if r.get("region","").lower() in ("bund","de","deutschland","eu") or bl_norm.lower() in (r.get("region","") or "").lower()]
    hints = []
    for r in cand[:8]:
        q = f'{r.get("name","")} Förderprogramm Status {bl_norm or ""} Antragstopp Frist verlängert'
        results = tavily_cached_search(q, max_results=3)
        for res in results:
            title = res.get("title","") or ""
            snippet = (res.get("content","") or "")[:180]
            url = res.get("url","")
            if any(k.lower() in (title + " " + snippet).lower() for k in FUNDING_STATUS_KEYWORDS):
                dom = _domain(url)
                hints.append(f"<li><strong>{html.escape(r.get('name',''))}</strong>: mögliche Statusänderung – {html.escape(title)} <span class='muted'>({html.escape(dom)})</span></li>")
                break
    if not hints: return ""
    head = "<strong>Realtime‑Hinweise Förderprogramme:</strong>" if lang.startswith("de") else "<strong>Realtime funding hints:</strong>"
    note = "<em>Hinweis: automatische Websuche; bitte Quelle prüfen.</em>" if lang.startswith("de") else "<em>Note: automated web search; please verify sources.</em>"
    return f"<div class='callout'>{head}<ul>{''.join(hints)}</ul>{note}</div>"

def _funding_deadline_radar_callout(bundesland: str, lang: str) -> str:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return ""
    rows = _funding_rows()
    if not rows: return ""
    bl_norm = (bundesland or "").strip().lower()
    bl_norm = BUNDESLAND_MAP.get(bl_norm, bl_norm)
    notes = []
    for r in rows[:10]:
        q = f"{r.get('name','')} Einreichungsfrist Deadline {bl_norm} endet bis"
        for res in tavily_cached_search(q, max_results=3):
            text = (res.get("title","") or "") + " " + (res.get("content","") or "")
            m = DEADLINE_PAT.search(text)
            if m:
                dom = _domain(res.get("url",""))
                notes.append(f"<li><strong>{html.escape(r.get('name',''))}</strong>: Frist bis {html.escape(m.group(1))} <span class='muted'>({html.escape(dom)})</span></li>")
                break
    if not notes: return ""
    head = "<strong>Deadline‑Radar:</strong> " if lang.startswith("de") else "<strong>Deadline radar:</strong> "
    note = "<em>Hinweis: bitte Quelle prüfen; nur Vorab‑Signal.</em>" if lang.startswith("de") else "<em>Note: preliminary signal; verify sources.</em>"
    return f"<div class='callout'>{head}<ul>{''.join(notes)}</ul>{note}</div>"

def _tools_news_callout(lang: str) -> str:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return ""
    rows = _tools_rows()[:6]
    hints = []
    for r in rows:
        name = r.get("name","")
        q = f"{name} pricing change EU data residency security advisory CVE outage breach update"
        for res in tavily_cached_search(q, max_results=2):
            title = res.get("title","") or ""
            url = res.get("url","")
            dom = _domain(url)
            if title:
                hints.append(f"<li>{html.escape(name)}: {html.escape(title)} <span class='muted'>({html.escape(dom)})</span></li>")
                break
    if not hints: return ""
    head = "<strong>Vendor/Policy‑News (Tools):</strong>" if lang.startswith("de") else "<strong>Vendor/Policy News (Tools):</strong>"
    note = "<em>Hinweis: Info‑Box; überschreibt nicht die Whitelist.</em>" if lang.startswith("de") else "<em>Informational only; does not override whitelist.</em>"
    return f"<div class='callout'>{head}<ul>{''.join(hints)}</ul>{note}</div>"

def _regulatory_watch_callout(company: Dict[str,Any], lang: str) -> str:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return ""
    branche = (company.get("branche") or company.get("industry") or "").lower()
    loc = company.get("location") or company.get("standort") or ""
    topics = [
        "EU AI Act implementing acts harmonised standards news Germany",
        "GDPR fine Germany supervisory authority news",
        "Datenschutzbehörde Deutschland Hinweise KI DSGVO"
    ]
    # branchenspezifische Aufsicht (leichtgewichtiges Mapping)
    if any(k in branche for k in ["bank","finanz","insurance","versicherung"]):
        topics.append("BaFin KI Rundschreiben Hinweis artificial intelligence")
    elif any(k in branche for k in ["gesund","health","medizin"]):
        topics.append("BfArM KI Leitfaden Medizinprodukte")
    elif any(k in branche for k in ["verwaltung","public","behörde"]):
        topics.append("BfDI Hinweise KI öffentliche Verwaltung")
    elif any(k in branche for k in ["medien","kreativ","rundfunk"]):
        topics.append("Landesmedienanstalten KI Leitfäden")
    items = []
    for t in topics:
        for r in tavily_cached_search(t, max_results=2):
            title = html.escape(r.get("title","") or "")
            dom = html.escape(_domain(r.get("url","")))
            if title:
                items.append(f"<li>{title} <span class='muted'>({dom})</span></li>")
            if len(items) >= 3: break
        if len(items) >= 3: break
    if not items: return ""
    head = "<strong>Regulatory‑Watch:</strong>" if lang.startswith("de") else "<strong>Regulatory watch:</strong>"
    return f"<div class='callout'>{head}<ul>{''.join(items[:3])}</ul></div>"

# ---- Appendix / Gamechanger-Fallbacks --------------------------------------
def _manifest(lang: str) -> Dict[str, Any]:
    path = PROMPTS_DIR / "manifest.json"
    if path.is_file():
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}

def _appendix_blocks(lang: str):
    m = _manifest(lang)
    blocks = []
    if APPENDIX_STRICT and m:
        items = m.get("appendix", [])
        base = PROMPTS_DIR / ("de" if lang.startswith("de") else "en")
        for it in items:
            file = it.get("file") if isinstance(it, dict) else str(it)
            title = (it.get("title") if isinstance(it, dict) else "") or ""
            p = base / file
            if p.is_file():
                txt = _sanitize_p(_load_text(p))
                blocks.append({"title": title or p.stem.replace("_"," ").title(), "html": f"<div class='section'>{txt}</div>"})
        return blocks
    # Fallback-Appendix (5 Standardblöcke)
    base = PROMPTS_DIR / ("de" if lang.startswith("de") else "en")
    defaults = ["prompt_policy.md","best_practices.md","compliance_checklist.md","faq_startpaket.md","glossar_kurz.md"]
    for name in defaults:
        p = base / name
        if p.is_file():
            txt = _sanitize_p(_load_text(p))
            blocks.append({"title": p.stem.replace("_"," ").title(), "html": f"<div class='section'>{txt}</div>"})
    return blocks

def _gc_block(title: str, bullets: List[str]) -> str:
    lis = "".join(f"<li>{html.escape(b)}</li>" for b in bullets if b)
    return f"<h3>{html.escape(title)}</h3><ul>{lis}</ul>"

def _gamechanger_deterministic(company: Dict[str,Any], lang: str) -> str:
    raw = (company.get("branche") or company.get("industry") or "").lower()
    sector_map = {
        "beratung & dienstleistungen":"consulting","beratung":"consulting","dienstleistungen":"consulting","services":"consulting",
        "finanzen & versicherungen":"finance","finanzen":"finance","versicherung":"finance","bank":"finance","insurance":"finance",
        "bauwesen & architektur":"construction","bau":"construction","architektur":"construction","construction":"construction",
        "it & software":"it","it":"it","software":"it","saas":"it","technology":"it",
        "marketing & werbung":"marketing","marketing":"marketing","werbung":"marketing","advertising":"marketing",
        "bildung":"education","education":"education","hochschule":"education","schule":"education",
        "verwaltung":"public","public":"public","behörde":"public","oeffentliche verwaltung":"public",
        "medien & kreativwirtschaft":"media","medien":"media","kreativ":"media","creative":"media",
        "handel & e-commerce":"commerce","handel":"commerce","e-commerce":"commerce","retail":"commerce"
    }
    key = sector_map.get(raw, raw) or "consulting"
    GC = {
        "consulting": { "title":"Beratung: KI‑Beschleuniger im Angebots‑ und Delivery‑Prozess",
            "bullets":[ "Standardisierte Angebots‑Prompts (Diagnose, Nutzen, Aufwand) + Vorlagenbibliothek",
                        "Reusable Case‑Kits (Reports, Spreadsheets, Slides) mit RAG auf eigene Referenzen",
                        "Delivery‑Co‑Pilot: Qualitätssicherung mit Checklisten, Glossar, Quellenprüfung" ]},
        "finance": { "title":"Finanzen & Versicherungen: Kontrollierte Automatisierung",
            "bullets":[ "Dokument‑Extraktion (Rechnungen/Police) mit Vier‑Augen‑Gate",
                        "Explainable‑AI‑Checks für Scorings; Audit‑Trails, Schwellen & Alerts",
                        "Self‑Service‑Wissen (RAG) für Richtlinien, Produkte, Compliance‑FAQs" ]},
        "construction": { "title":"Bauwesen & Architektur: Angebots‑ und Planungs‑Taktung",
            "bullets":[ "LV‑Analyse & Massen‑Ableitung halbautomatisieren, Versionen tracken",
                        "Baustellen‑Berichte sprachgesteuert erfassen; Foto‑Belege anhängen",
                        "Nachtrags‑Assistent: Claims dokumentieren, Beweise strukturieren" ]},
        "it": { "title":"IT & Software: Dev‑Produktivität sicher skalieren",
            "bullets":[ "Secure‑Coding‑Kochbuch + Snippet‑RAG; Pair‑Review mit Policies",
                        "Backlog‑Mining: Tickets clustern, Duplikate schließen, Akzeptanzkriterien generieren",
                        "Runbook‑Assistent für On‑Call; Postmortems halbautomatisieren" ]},
        "marketing": { "title":"Marketing & Werbung: Content‑Engine mit Governance",
            "bullets":[ "Kampagnen‑Briefings → strukturierte Prompts; Varianten A/B automatisch",
                        "Asset‑RAG (Claims, Produktdaten, CI) + Fact‑Check vor Freigabe",
                        "Repurpose‑Pipelines (Blog → Social/Newsletter/Slides) mit Sperrlisten" ]},
        "education": { "title":"Bildung: Curricula & Betreuung entlasten",
            "bullets":[ "Material‑RAG (Skripte, Aufgaben, Lösungen) inkl. Quellen & Lizenzhinweisen",
                        "Tutor‑Co‑Pilot: FAQs, Übungsfeedback, Rubrics – Protokollierung aktiv",
                        "Barrierefreiheit: Zusammenfassungen, Audio‑Versionen, einfache Sprache" ]},
        "public": { "title":"Verwaltung: Vorgangsbearbeitung beschleunigen",
            "bullets":[ "Posteingang klassifizieren, fehlende Angaben anfordern (Vorlagen)",
                        "Bescheid‑Entwürfe aus Regelwerken generieren, Fachprüfung behalten",
                        "Wissens‑RAG zu Leistungen/Paragraphen, Änderungen monitoren" ]},
        "media": { "title":"Medien & Kreativwirtschaft: Rechtekonforme Produktion",
            "bullets":[ "Asset‑Management mit Lizenz‑Metadaten; Nutzungssperren automatisieren",
                        "Schnitt/Transkript/Untertitel‑Pipelines; QC‑Checklisten standardisieren",
                        "Ideen‑Boards mit Referenzen statt Text‑Anekdoten; Versionierung" ]},
        "commerce": { "title":"Handel & E‑Commerce: Katalog‑ und Service‑Ops",
            "bullets":[ "Produktdaten normalisieren, Lücken füllen; Übersetzungen mit Glossar",
                        "FAQ‑RAG + Assistent für Retouren/Anfragen; Eskalationsrouten klar",
                        "Merch‑Texte/Bilder variieren, Preise/Bestände strikt aus Quelle" ]},
    }
    cfg = GC.get(key, GC["consulting"])
    return _clamp_text(_gc_block(cfg["title"], cfg["bullets"]), MAX_CHARS)

# ---- News Callouts ----------------------------------------------------------
def _news_callout(company: Dict[str,Any], lang: str) -> str:
    if not (ALLOW_TAVILY and TAVILY_API_KEY): return ""
    branche = company.get("branche") or company.get("industry") or ""
    loc = company.get("location") or company.get("standort") or ""
    q = f"aktuelle Nachrichten KI Einführung {branche} Unternehmen Deutschland {loc}".strip()
    results = tavily_cached_search(q, max_results=3)
    if not results: return ""
    items = []
    for r in results:
        title = html.escape(r.get("title",""))
        source = html.escape(r.get("source","") or _domain(r.get("url","")))
        items.append(f"<li>{title} <span class='muted'>({source})</span></li>")
    head = "<strong>Realtime‑Hinweise (News):</strong>" if lang.startswith("de") else "<strong>Realtime notes (news):</strong>"
    return "<div class='callout'>"+head+"<ul>"+ "".join(items[:3]) + "</ul></div>"

# ---- Hauptfunktion ----------------------------------------------------------
def analyze_briefing(body: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    lang = (lang or "de").lower()
    company = body.get("company") if isinstance(body.get("company"), dict) else body
    loc_raw = (company.get("standort") or company.get("location") or "").strip().lower()
    company["location"] = BUNDESLAND_MAP.get(loc_raw, company.get("location") or loc_raw or "")
    meta = {
        "company_name": company.get("unternehmen") or company.get("company") or "—",
        "branche": company.get("branche") or company.get("industry") or "—",
        "groesse": company.get("unternehmensgroesse") or company.get("size") or "—",
        "standort": company.get("location") or "—",
        "date": datetime.date.today().strftime("%d.%m.%Y"),
        "as_of": datetime.date.today().isoformat(),
    }

    # Deterministische Kurztexte
    def det_short(section: str) -> str:
        if lang.startswith("de"):
            presets = {
                "quickwins": "Start mit Dateninventur (10 Quellen), Policy‑Mini‑Seite (Zwecke/No‑Gos/Freigaben), Prompt‑Bibliothek (10 Aufgaben). Eine Schleife automatisieren (4‑Augen‑Check).",
                "risks": "Risiken: Datenqualität, Compliance, Schatten‑IT. Absicherung: Data Owner, AVV/Standorte, Logging & Evaluations, klare Freigaben.",
                "recs": "Automatisieren, Governance leichtgewichtig starten (Rollen, Policy, Logging), Schlüsselrollen qualifizieren.",
                "roadmap": "0–3 M: Inventur/Policy/Quick‑Wins. 3–6 M: 2 Piloten + Evaluation. 6–12 M: Skalierung, Schulungen, KPIs.",
            }
        else:
            presets = {
                "quickwins": "Light data inventory, one‑page policy, prompt library. Automate one loop with a four‑eyes check.",
                "risks": "Risks: data quality, compliance, shadow IT. Mitigation: data owners, DPAs/locations, logging & evaluations.",
                "recs": "Automate repetitive work, lightweight governance, upskill key roles.",
                "roadmap": "0–3 m: inventory/policy/quick wins. 3–6 m: two pilots + evaluation. 6–12 m: scale, training, KPIs.",
            }
        return presets.get(section, "")

    # Exec Summary (LLM optional)
    exec_sum = ""
    if LLM_MODE != "off":
        sys = "Sie sind präzise, sachlich, per Sie. Max. 900 Zeichen. Keine Anekdoten."
        if lang.startswith("en"): sys = "You are precise and succinct. Formal 'you'. Max 900 characters. No anecdotes."
        prompt = f"Erstellen Sie eine Executive Summary (3–5 Sätze) für Branche={meta['branche']}, Größe={meta['groesse']}, Standort={meta['standort']}."
        exec_sum = llm_generate(prompt, system=sys, max_tokens=450)
        exec_sum = _sanitize_p(exec_sum)
        if STORY_BLOCK.search(exec_sum) or _reject_if_english(_plain_text(exec_sum), lang):
            exec_sum = ""
    if not exec_sum: exec_sum = det_short("recs")

    risks = det_short("risks")
    recs = det_short("recs")
    roadmap = det_short("roadmap")
    quickwins = det_short("quickwins")

    tools_html = render_tools_from_whitelist()
    funding_html = render_funding_from_whitelist(bundesland=meta["standort"])

    # Gamechanger
    gamechanger_html = ""
    if LLM_MODE != "off":
        gc_try = _sanitize_p(llm_generate(f"""
Bitte verfassen Sie einen kurzen 'Innovation & Gamechanger'-Baustein (DE, per Sie) für:
Branche: {meta['branche']}, Unternehmensgröße: {meta['groesse']}, Standort: {meta['standort']}.
Format: <h3>…</h3><ul><li>…</li>…</ul> ; max. 900 Zeichen; keine Anekdoten; keine Platzhalter.
""".strip(), system="Sie sind präzise, sachlich, ohne Storytelling.", max_tokens=500))
        if gc_try and not STORY_BLOCK.search(gc_try) and not _reject_if_english(_plain_text(gc_try), lang):
            gamechanger_html = _clamp_text(gc_try, MAX_CHARS)
    if not gamechanger_html:
        gamechanger_html = _gamechanger_deterministic(company, lang)

    # Realtime-Boxen
    regwatch_html = _regulatory_watch_callout(company, lang)
    news_html = _news_callout(company, lang)
    funding_rt_html = _funding_realtime_callout(meta["standort"], lang)
    funding_deadlines_html = _funding_deadline_radar_callout(meta["standort"], lang)
    tools_news_html = _tools_news_callout(lang)

    # Kürzen & Sprache
    exec_sum = _clamp_text(exec_sum)
    for v in [risks, recs, roadmap, quickwins]:
        _ = _clamp_text(v)
    if _reject_if_english(" ".join([_plain_text(x) for x in [exec_sum, risks, recs, roadmap, quickwins, gamechanger_html]]), lang):
        exec_sum = det_short("recs"); risks = det_short("risks"); recs = det_short("recs"); roadmap = det_short("roadmap"); quickwins = det_short("quickwins"); gamechanger_html = _gamechanger_deterministic(company, lang)

    appendix_blocks = _appendix_blocks(lang)
    appendix_html = "".join(f"<h3>{html.escape(b['title'])}</h3>{b['html']}" for b in appendix_blocks)

    return {
        "meta": meta,
        "executive_summary": exec_sum,
        "quick_wins": quickwins,
        "risks": risks,
        "recommendations": recs,
        "roadmap": roadmap,
        "tools_table": tools_html,
        "funding_table": funding_html,
        "funding_realtime": funding_rt_html,
        "funding_deadlines": funding_deadlines_html,
        "tools_news": tools_news_html,
        "regwatch": regwatch_html,
        "gamechanger": (gamechanger_html + news_html),
        "appendix": appendix_html,
    }
