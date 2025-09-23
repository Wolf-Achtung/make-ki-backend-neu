
"""
gpt_analyze.py — Gold-Standard Analyzer v5.1 (Hotfix Tavily + Callout-Flags)
- Template-Only downstream: returns *only* data dict
- Story-Killer + DE-Guard
- Whitelist-Only for tools & funding (with Bundesland filter + sector_hints)
- Realtime callouts (optional; gated via ENV)
- LLM only for Exec Summary & Gamechanger (LLM_MODE=hybrid)
- Hard-limit MAX_CHARS per section
- Tavily runtime-off on 401 (prevents log spam); early ALLOW_TAVILY gate
"""
import os, json, re, datetime, html, hashlib
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.getcwd())
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"
CACHE_DIR = Path(os.getenv("TAVILY_CACHE_DIR", ".cache")); CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_LANG = (os.getenv("DEFAULT_LANG") or "de").lower()
LLM_MODE = os.getenv("LLM_MODE") or ("hybrid" if os.getenv("ENABLE_LLM_SECTIONS","1") in ("1","true","True") else "off")
GPT_MODEL_NAME = os.getenv("EXEC_SUMMARY_MODEL") or os.getenv("SUMMARY_MODEL_NAME") or os.getenv("GPT_MODEL_NAME") or "gpt-4o-mini"
GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE", "0.2"))
APPENDIX_STRICT = os.getenv("APPENDIX_STRICT", "1") == "1"
MAX_CHARS = int(os.getenv("MAX_CHARS", "1000"))

# Realtime feature flags (can be disabled via ENV for troubleshooting)
SHOW_REGWATCH = os.getenv("SHOW_REGWATCH","1") in ("1","true","True")
SHOW_FUNDING_STATUS = os.getenv("SHOW_FUNDING_STATUS","1") in ("1","true","True")
SHOW_FUNDING_DEADLINES = os.getenv("SHOW_FUNDING_DEADLINES","1") in ("1","true","True")
SHOW_TOOLS_NEWS = os.getenv("SHOW_TOOLS_NEWS","1") in ("1","true","True")

# Tavily
def _ALLOW_TAVILY() -> bool:
    return os.getenv("ALLOW_TAVILY","0") in ("1","true","True")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY","")
TAVILY_CACHE_TTL = int(os.getenv("TAVILY_CACHE_TTL","3600"))

def _reject_if_english(text: str, lang: str) -> bool:
    if lang.startswith("de"):
        return bool(re.search(r"\b(the|and|of|for example|consider|imagine|once in|a company)\b", text or "", re.I))
    return False

STORY_BLOCK = re.compile(r"\b(Ein Unternehmen|Stellen Sie sich vor|Imagine|For instance|Consider a|Once upon|Mehr erfahren|Case study|Fallbeispiel)\b", re.I)

def _load_json(*names: str) -> Any:
    for name in names:
        for p in [DATA_DIR / name, ROOT / name]:
            if p.is_file():
                try: return json.loads(p.read_text(encoding="utf-8"))
                except Exception: pass
    return None

def _load_text(p: Path) -> str:
    try: return p.read_text(encoding="utf-8")
    except Exception: return ""

def _sanitize_inline(text: str) -> str:
    if text is None: return ""
    t = str(text).replace("```html","```").replace("```HTML","```")
    while "```" in t: t = t.replace("```","")
    return t

def _plain(html_text: str) -> str: return re.sub(r"<[^>]+>", " ", html_text or "")
def _clamp(s: str, max_chars: int = MAX_CHARS) -> str:
    if not s or len(s) <= max_chars: return s or ""
    cut = s[:max_chars]; m = re.search(r"[.!?)»](?=[^.!?)»]*$)", cut)
    if m: cut = cut[:m.end()]
    return cut.rstrip() + " …"

# --- Tavily (cached) --------------------------------------------------------
def _cache_key(query: str, k: int) -> Path:
    h = hashlib.sha1(f"{query}|{k}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"tavily_{h}.json"

def tavily_search(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    if not (_ALLOW_TAVILY() and TAVILY_API_KEY): return []
    try:
        import httpx  # type: ignore
        headers = {"Content-Type":"application/json","X-Tavily-API-Key":TAVILY_API_KEY}
        payload = {"query": query, "max_results": max_results}
        with httpx.Client(timeout=15.0) as c:
            r = c.post("https://api.tavily.com/search", headers=headers, json=payload)
            if r.status_code == 401:  # Unauthorized -> switch off to avoid spam
                os.environ["ALLOW_TAVILY"] = "0"
                return []
            if r.status_code == 404:
                # Try legacy endpoint once
                r = c.post("https://api.tavily.com/v1/search", headers=headers, json=payload)
                if r.status_code == 401:
                    os.environ["ALLOW_TAVILY"] = "0"; return []
            if 200 <= r.status_code < 300:
                j = r.json() or {}
                return j.get("results", j.get("data", [])) or []
    except Exception:
        return []
    return []

def tavily_cached(query: str, max_results: int = 3, ttl: int = None) -> List[Dict[str, Any]]:
    if not _ALLOW_TAVILY(): return []
    ttl = ttl if ttl is not None else TAVILY_CACHE_TTL
    p = _cache_key(query, max_results)
    try:
        if p.is_file():
            import time
            age = time.time() - p.stat().st_mtime
            if age < ttl:
                return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    res = tavily_search(query, max_results=max_results)
    try: p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    except Exception: pass
    return res

# --- LLM --------------------------------------------------------------------
def llm_generate(user_prompt: str, system_prompt: str = "", max_tokens: int = 600) -> str:
    if LLM_MODE == "off": return ""
    try:
        import openai  # type: ignore
        client = openai.OpenAI()
        msgs = [{"role":"system","content":system_prompt}] if system_prompt else []
        msgs.append({"role":"user","content":user_prompt})
        resp = client.chat.completions.create(model=GPT_MODEL_NAME, messages=msgs, temperature=float(os.getenv("GPT_TEMPERATURE","0.2")), max_tokens=max_tokens)
        return resp.choices[0].message.content or ""
    except Exception:
        return ""

# --- Whitelists / Bundesländer ----------------------------------------------
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

def _tool_rows() -> List[Dict[str,Any]]:
    return _load_json("tool_whitelist.json") or []

def _funding_rows() -> List[Dict[str,Any]]:
    base = _load_json("funding_whitelist.json") or []
    full = _load_json("funding_states_full.json") or _load_json("funding_states.json") or []
    merged: List[Dict[str,Any]] = []
    if isinstance(full, dict):
        for st, items in full.items():
            for it in items:
                merged.append({
                    "name": it.get("program") or it.get("name") or "—",
                    "region": st,
                    "target": it.get("target","—"),
                    "benefit": it.get("benefit","—"),
                    "status": it.get("status",""),
                    "source": it.get("source","—"),
                    "as_of": it.get("as_of") or datetime.date.today().strftime("%Y-%m")
                } | ({"sector_hints": it.get("sector_hints")} if it.get("sector_hints") else {}))
    elif isinstance(full, list):
        merged = full
    return base + merged

# --- Renderers ---------------------------------------------------------------
def render_tools_table(max_items: int = 18) -> str:
    rows = _tool_rows()
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    head = "<tr><th>Kategorie</th><th>Option</th><th>Badge</th><th>Daten/Deployment</th><th>Hinweise</th></tr>"
    body = []
    for r in rows[:max_items]:
        badge = "<span class='badge souveraen'>souverän</span>" if r.get("sovereign") else ""
        cols = [r.get("category","—"), r.get("name","—"), badge, r.get("hosting","—"), r.get("note","—")]
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def render_funding_table(max_items: int = 24, bundesland: str = "") -> str:
    rows = _funding_rows()
    if not rows: return "<p>— (keine kuratierten Einträge)</p>"
    bl_norm = (bundesland or "").strip().lower(); bl_norm = BUNDESLAND_MAP.get(bl_norm, bl_norm)
    def _keep(r):
        reg = (r.get("region","") or "").strip().lower()
        if not bl_norm: return True
        if reg in ("bund","de","deutschland","eu","europe","europa"): return True
        return bl_norm.lower() in reg
    filtered = [r for r in rows if _keep(r)] or rows
    head_cols = ["Programm","Region","Zielgruppe","Leistung/Status","Quelle","Stand"]
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in head_cols) + "</tr>"
    body=[]
    for r in filtered[:max_items]:
        perf = r.get("benefit","—"); status = r.get("status",""); hints = r.get("sector_hints")
        if hints: perf = f"{perf} <span class='muted'>(Branchen‑Fit: {', '.join(hints)})</span>"
        if status: perf = f"{perf} ({html.escape(status)})"
        cols=[r.get("name","—"), r.get("region","—"), r.get("target","—"), perf, r.get("source","—"), r.get("as_of","")]
        body.append("<tr>"+ "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

# --- Realtime Callouts (guarded) --------------------------------------------
FUNDING_STATUS_KEYS = ["Antragstopp","ausgesetzt","geschlossen","Stopp","Einstellung","Kontingent erschöpft","wieder geöffnet","Frist verlängert","verlängert","läuft wieder","Programmende","Deadline","Einreichung","Antragsfrist","Bewilligung gestoppt"]
DEADLINE_PAT = re.compile(r"\b(?:(?:bis|deadline|frist)\s*[:\-]?\s*)(\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)", re.I)

def _callout_funding_status(bundesland: str, lang: str) -> str:
    if not (_ALLOW_TAVILY() and TAVILY_API_KEY and SHOW_FUNDING_STATUS): return ""
    rows = _funding_rows()
    bl_norm = (bundesland or "").strip().lower(); bl_norm = BUNDESLAND_MAP.get(bl_norm, bl_norm)
    cand = [r for r in rows if r.get("region","").lower() in ("bund","de","deutschland","eu") or bl_norm.lower() in (r.get("region","") or "").lower()]
    hints = []
    for r in cand[:10]:
        q = f'{r.get("name","")} Förderprogramm Status {bl_norm or ""} Antragstopp Frist verlängert'
        for res in tavily_cached(q, max_results=3):
            title = res.get("title","") or ""; snippet = (res.get("content","") or "")[:180]; url = res.get("url","")
            if any(k.lower() in (title + " " + snippet).lower() for k in FUNDING_STATUS_KEYS):
                dom = _domain(url); hints.append(f"<li><strong>{html.escape(r.get('name',''))}</strong>: mögliche Statusänderung – {html.escape(title)} <span class='muted'>({html.escape(dom)})</span></li>"); break
    if not hints: return ""
    head = "<strong>Realtime‑Hinweise Förderprogramme:</strong>" if lang.startswith("de") else "<strong>Realtime funding hints:</strong>"
    note = "<em>Hinweis: automatische Websuche; bitte Quelle prüfen.</em>" if lang.startswith("de") else "<em>Note: automated web search; please verify.</em>"
    return f"<div class='callout'>{head}<ul>{''.join(hints)}</ul>{note}</div>"

def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        d = urlparse(url).netloc
        return d.replace("www.","")
    except Exception:
        return ""

def _callout_funding_deadlines(bundesland: str, lang: str) -> str:
    if not (_ALLOW_TAVILY() and TAVILY_API_KEY and SHOW_FUNDING_DEADLINES): return ""
    rows = _funding_rows()
    bl_norm = (bundesland or "").strip().lower(); bl_norm = BUNDESLAND_MAP.get(bl_norm, bl_norm)
    notes = []
    for r in rows[:12]:
        q = f"{r.get('name','')} Einreichungsfrist Deadline {bl_norm} endet bis"
        for res in tavily_cached(q, max_results=3):
            text = (res.get("title","") or "") + " " + (res.get("content","") or "")
            m = DEADLINE_PAT.search(text)
            if m:
                dom = _domain(res.get("url","")); notes.append(f"<li><strong>{html.escape(r.get('name',''))}</strong>: Frist bis {html.escape(m.group(1))} <span class='muted'>({html.escape(dom)})</span></li>"); break
    if not notes: return ""
    head = "<strong>Deadline‑Radar:</strong> " if lang.startswith("de") else "<strong>Deadline radar:</strong> "
    note = "<em>Hinweis: bitte Quelle prüfen; nur Vorab‑Signal.</em>" if lang.startswith("de") else "<em>Preliminary signal; verify sources.</em>"
    return f"<div class='callout'>{head}<ul>{''.join(notes)}</ul>{note}</div>"

def _callout_tools_news(lang: str) -> str:
    if not (_ALLOW_TAVILY() and TAVILY_API_KEY and SHOW_TOOLS_NEWS): return ""
    rows = _tool_rows()[:6]; hints = []
    for r in rows:
        name = r.get("name",""); q = f"{name} pricing change EU data residency security advisory CVE outage breach update"
        for res in tavily_cached(q, max_results=2):
            title = res.get("title","") or ""; url = res.get("url",""); dom = _domain(url)
            if title:
                hints.append(f"<li>{html.escape(name)}: {html.escape(title)} <span class='muted'>({html.escape(dom)})</span></li>"); break
    if not hints: return ""
    head = "<strong>Vendor/Policy‑News (Tools):</strong>" if lang.startswith("de") else "<strong>Vendor/Policy News (Tools):</strong>"
    note = "<em>Hinweis: Info‑Box; überschreibt nicht die Whitelist.</em>" if lang.startswith("de") else "<em>Informational only; does not override whitelist.</em>"
    return f"<div class='callout'>{head}<ul>{''.join(hints)}</ul>{note}</div>"

def _callout_regulatory(company: Dict[str,Any], lang: str) -> str:
    if not (_ALLOW_TAVILY() and TAVILY_API_KEY and SHOW_REGWATCH): return ""
    branche = (company.get("branche") or company.get("industry") or "").lower()
    topics = ["EU AI Act implementing acts harmonised standards news Germany","GDPR fine Germany supervisory authority news","Datenschutzbehörde Deutschland Hinweise KI DSGVO"]
    if any(k in branche for k in ["bank","finanz","insurance","versicherung"]): topics.append("BaFin KI Rundschreiben Hinweise")
    elif any(k in branche for k in ["gesund","health","medizin"]): topics.append("BfArM KI Leitfaden Medizinprodukte")
    elif any(k in branche for k in ["verwaltung","public","behörde"]): topics.append("BfDI Hinweise KI öffentliche Verwaltung")
    elif any(k in branche for k in ["medien","kreativ","rundfunk"]): topics.append("Landesmedienanstalten KI Leitfäden")
    items = []
    for t in topics:
        for r in tavily_cached(t, max_results=2):
            title = html.escape(r.get("title","") or ""); dom = html.escape(_domain(r.get("url",""))); 
            if title: items.append(f"<li>{title} <span class='muted'>({dom})</span></li>")
            if len(items) >= 3: break
        if len(items) >= 3: break
    if not items: return ""
    head = "<strong>Regulatory‑Watch:</strong>" if lang.startswith("de") else "<strong>Regulatory watch:</strong>"
    return f"<div class='callout'>{head}<ul>{''.join(items[:3])}</ul></div>"

# --- Appendix / Deterministic sections --------------------------------------
def _manifest(lang: str) -> Dict[str, Any]:
    p = PROMPTS_DIR / "manifest.json"
    if p.is_file():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}

def _appendix(lang: str):
    m = _manifest(lang); blocks = []
    if os.getenv("APPENDIX_STRICT","1") == "1" and m:
        base = PROMPTS_DIR / ("de" if lang.startswith("de") else "en")
        for it in m.get("appendix", []):
            file = it.get("file") if isinstance(it, dict) else str(it)
            title = (it.get("title") if isinstance(it, dict) else "") or ""
            p = base / file
            if p.is_file():
                txt = _sanitize_inline(_load_text(p))
                blocks.append({"title": title or p.stem.replace("_"," ").title(), "html": f"<div class='section'>{txt}</div>"})
        return blocks
    base = PROMPTS_DIR / ("de" if lang.startswith("de") else "en")
    defaults = ["prompt_policy.md","best_practices.md","compliance_checklist.md","faq_startpaket.md","glossar_kurz.md"]
    for name in defaults:
        p = base / name
        if p.is_file():
            txt = _sanitize_inline(_load_text(p))
            blocks.append({"title": p.stem.replace("_"," ").title(), "html": f"<div class='section'>{txt}</div>"})
    return blocks

def _det_texts(lang: str) -> Dict[str,str]:
    if lang.startswith("de"):
        return {
            "quickwins": "Start mit Dateninventur (10 Quellen), Policy‑Mini‑Seite (Zwecke/No‑Gos/Freigaben), Prompt‑Bibliothek (10 Aufgaben). Eine Schleife automatisieren (4‑Augen‑Check).",
            "risks": "Risiken: Datenqualität, Compliance, Schatten‑IT. Absicherung: Data Owner, AVV/Standorte, Logging/Evaluations, klare Freigaben.",
            "recs": "Automatisieren Sie wiederkehrende Arbeiten, starten Sie eine leichtgewichtige Governance und qualifizieren Sie Schlüsselrollen.",
            "roadmap": "0–3 M: Inventur/Policy/Quick‑Wins. 3–6 M: 2 Piloten + Evaluation. 6–12 M: Skalierung, Schulungen, KPIs.",
        }
    else:
        return {
            "quickwins": "Light data inventory, one‑page policy, prompt library. Automate one loop with a four‑eyes check.",
            "risks": "Risks: data quality, compliance, shadow IT. Mitigation: data owners, DPAs/locations, logging/evaluations.",
            "recs": "Automate repetitive work, start lightweight governance, upskill key roles.",
            "roadmap": "0–3 m: inventory/policy/quick wins. 3–6 m: two pilots + evaluation. 6–12 m: scale, training, KPIs.",
        }

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
            "bullets":[ "Angebots‑Prompts + Vorlagenbibliothek (Diagnose/Nutzen/Aufwand)",
                        "Reusable Case‑Kits (Reports, Tabellen, Slides) mit RAG auf Referenzen",
                        "Delivery‑Co‑Pilot: QS mit Checklisten, Glossar, Quellenprüfung" ]},
        "finance": { "title":"Finanzen & Versicherungen: Kontrollierte Automatisierung",
            "bullets":[ "Dokument‑Extraktion (Rechnungen/Police) mit Vier‑Augen‑Gate",
                        "Explainable‑AI‑Checks für Scorings; Audit‑Trails, Schwellen & Alerts",
                        "Self‑Service‑Wissen (RAG) für Richtlinien/Produkte/Compliance‑FAQs" ]},
        "construction": { "title":"Bauwesen & Architektur: Angebots‑ & Planungs‑Taktung",
            "bullets":[ "LV‑Analyse & Massen‑Ableitung, Versionen tracken",
                        "Baustellen‑Berichte sprachgesteuert erfassen; Foto‑Belege anhängen",
                        "Nachtrags‑Assistent: Claims dokumentieren, Beweise strukturieren" ]},
        "it": { "title":"IT & Software: Dev‑Produktivität sicher skalieren",
            "bullets":[ "Secure‑Coding‑Kochbuch + Snippet‑RAG; Pair‑Review mit Policies",
                        "Backlog‑Mining: Tickets clustern, Duplikate schließen, Akzeptanzkriterien generieren",
                        "Runbook‑Assistent für On‑Call; Postmortems halbautomatisieren" ]},
        "marketing": { "title":"Marketing & Werbung: Content‑Engine mit Governance",
            "bullets":[ "Kampagnen‑Briefings → strukturierte Prompts; Varianten A/B",
                        "Asset‑RAG (Claims, Produktdaten, CI) + Fact‑Check vor Freigabe",
                        "Repurpose‑Pipelines (Blog → Social/Newsletter/Slides) mit Sperrlisten" ]},
        "education": { "title":"Bildung: Curricula & Betreuung entlasten",
            "bullets":[ "Material‑RAG (Skripte/Aufgaben/Lösungen) inkl. Quellen/Lizenzen",
                        "Tutor‑Co‑Pilot: FAQs, Übungsfeedback, Rubrics – Protokollierung",
                        "Barrierefreiheit: Zusammenfassungen, Audio, einfache Sprache" ]},
        "public": { "title":"Verwaltung: Vorgangsbearbeitung beschleunigen",
            "bullets":[ "Posteingang klassifizieren, fehlende Angaben anfordern (Vorlagen)",
                        "Bescheid‑Entwürfe aus Regelwerken, Fachprüfung behalten",
                        "Wissens‑RAG zu Leistungen/Paragraphen, Änderungen monitoren" ]},
        "media": { "title":"Medien & Kreativwirtschaft: Rechtekonforme Produktion",
            "bullets":[ "Asset‑Management mit Lizenz‑Metadaten; Nutzungssperren automatisieren",
                        "Schnitt/Transkript/Untertitel‑Pipelines; QC‑Checklisten",
                        "Ideen‑Boards mit Referenzen statt Anekdoten; Versionierung" ]},
        "commerce": { "title":"Handel & E‑Commerce: Katalog‑ und Service‑Ops",
            "bullets":[ "Produktdaten normalisieren; Lücken füllen; Übersetzungen mit Glossar",
                        "FAQ‑RAG + Assistent für Retouren/Anfragen; Eskalationsrouten",
                        "Merch‑Texte/Bilder variieren; Preise/Bestände strikt aus Quelle" ]},
    }
    cfg = GC.get(key, GC["consulting"])
    return _clamp(_gc_block(cfg["title"], cfg["bullets"]))

# --- Main analyze ------------------------------------------------------------
def analyze_briefing(body: Dict[str, Any], lang: str = DEFAULT_LANG) -> Dict[str, Any]:
    lang = (lang or DEFAULT_LANG).lower()
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

    d = _det_texts(lang)
    quickwins = d["quickwins"]; risks = d["risks"]; recs = d["recs"]; roadmap = d["roadmap"]

    exec_sum = ""
    if LLM_MODE != "off":
        sys = "Sie sind präzise, sachlich, per Sie. Max. 900 Zeichen. Keine Anekdoten, keine Platzhalter."
        if not lang.startswith("de"): sys = "You are precise and succinct. Formal 'you'. Max 900 characters. No anecdotes."
        prompt = f"Erstellen Sie eine Executive Summary (3–5 Sätze) auf {'Deutsch' if lang.startswith('de') else 'English'}, per Sie. Branche={meta['branche']}, Größe={meta['groesse']}, Standort={meta['standort']}."
        exec_sum = llm_generate(prompt, system_prompt=sys, max_tokens=450)
        exec_sum = _sanitize_inline(exec_sum)
        if STORY_BLOCK.search(exec_sum) or _reject_if_english(_plain(exec_sum), lang): exec_sum = ""
    if not exec_sum: exec_sum = recs

    tools_html = render_tools_table()
    funding_html = render_funding_table(bundesland=meta["standort"])

    gamechanger_html = ""
    if LLM_MODE != "off":
        gc_try = _sanitize_inline(llm_generate(
            f"Bitte verfassen Sie einen kurzen 'Innovation & Gamechanger'-Baustein (DE per Sie) für Branche={meta['branche']}, Größe={meta['groesse']}, Standort={meta['standort']}. "
            "Format: <h3>…</h3><ul><li>…</li>…</ul>; max. 900 Zeichen; keine Anekdoten; keine Platzhalter.",
            system_prompt="Sie sind präzise, sachlich, ohne Storytelling.", max_tokens=500))
        if gc_try and not STORY_BLOCK.search(gc_try) and not _reject_if_english(_plain(gc_try), lang):
            gamechanger_html = _clamp(gc_try)
    if not gamechanger_html:
        gamechanger_html = _gamechanger_deterministic(company, lang)

    regwatch_html = _callout_regulatory(company, lang) if SHOW_REGWATCH else ""
    funding_rt_html = _callout_funding_status(meta["standort"], lang) if SHOW_FUNDING_STATUS else ""
    funding_deadlines_html = _callout_funding_deadlines(meta["standort"], lang) if SHOW_FUNDING_DEADLINES else ""
    tools_news_html = _callout_tools_news(lang) if SHOW_TOOLS_NEWS else ""

    exec_sum = _clamp(exec_sum); quickwins = _clamp(quickwins); risks = _clamp(risks); recs = _clamp(recs); roadmap = _clamp(roadmap); gamechanger_html = _clamp(gamechanger_html)

    if _reject_if_english(" ".join([_plain(x) for x in [exec_sum, quickwins, risks, recs, roadmap, gamechanger_html]]), lang):
        d = _det_texts(lang); exec_sum, quickwins, risks, recs, roadmap = d["recs"], d["quickwins"], d["risks"], d["recs"], d["roadmap"]
        gamechanger_html = _gamechanger_deterministic(company, lang)

    appendix_blocks = _appendix(lang)
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
        "gamechanger": gamechanger_html,
        "appendix": appendix_html,
    }
