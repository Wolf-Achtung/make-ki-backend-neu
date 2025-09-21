
# gpt_analyze.py — Gold Standard + Live Layer (2025-09-21)
# - Narrative chapters (DE/EN), subheads allowed, tables only for Tools/Funding.
# - Uses Tavily live search when TAVILY_API_KEY is set to fetch current EU-hosted tools & funding hints.
# - Falls back to curated CSVs in ./data/*.csv if live layer is unavailable.
from __future__ import annotations

import os, re, csv, json, math, asyncio, datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
DATA_DIR = BASE_DIR / "data"
DEFAULT_LANG = "de"
LANGS = {"de","en"}
MIN_HTML_LEN = int(os.getenv("MIN_HTML_LEN","1000"))
TAVILY_KEY = os.getenv("TAVILY_API_KEY","").strip()
SEARCH_DAYS = int(os.getenv("SEARCH_DAYS","365"))

# ----------------- Utilities & Sanitizers -----------------

_CODEFENCE_RE = re.compile(r"```.*?```", flags=re.S)
_TAG_RE = re.compile(r"</?(script|style)[^>]*>", flags=re.I)
_LEADING_ENUM_RE = re.compile(r"(?m)^\s*(?:\d+[\.\)]|[-–•])\s+")
_LI_RE = re.compile(r"</?li[^>]*>", flags=re.I)
_OL_UL_RE = re.compile(r"</?(?:ol|ul)[^>]*>", flags=re.I)

def _strip_code_fences(text: str) -> str:
    if not text: return text
    text = _CODEFENCE_RE.sub("", text)
    return text.replace("```","")

def _strip_scripts_styles(text: str) -> str:
    return _TAG_RE.sub("", text or "")

def _normalize_lists_to_paragraphs(html: str) -> str:
    if not html: return html
    html = _LI_RE.sub("\n", html)
    html = _OL_UL_RE.sub("\n", html)
    html = _LEADING_ENUM_RE.sub("", html)
    html = re.sub(r"\n{3,}","\n\n", html)
    return html

def _strip_lists_and_numbers(html: str) -> str:
    if not html: return html
    html = _strip_code_fences(_strip_scripts_styles(html))
    html = _normalize_lists_to_paragraphs(html)
    return html

def _sanitize_text(html: str) -> str:
    if not html: return html
    html = _strip_scripts_styles(html)
    html = _strip_code_fences(html)
    return html.replace("&nbsp;"," ")

# ----------------- Region normalization -----------------

REGION_MAP = {
    "be":"berlin","bb":"brandenburg","bw":"baden-württemberg","by":"bayern",
    "hb":"bremen","hh":"hamburg","he":"hessen","mv":"mecklenburg-vorpommern",
    "ni":"niedersachsen","nw":"nordrhein-westfalen","nrw":"nordrhein-westfalen",
    "rp":"rheinland-pfalz","sl":"saarland","sn":"sachsen","st":"sachsen-anhalt",
    "sh":"schleswig-holstein","th":"thüringen",
}
def normalize_region(value: Optional[str]) -> str:
    if not value: return ""
    v = str(value).strip().lower()
    return REGION_MAP.get(v, v)

# ----------------- LLM -----------------

def _llm_complete(prompt: str, model: Optional[str]=None, temperature: float=0.35) -> str:
    provider = os.getenv("LLM_PROVIDER","openai").lower()
    if provider == "none":
        raise RuntimeError("LLM disabled")
    try:
        # OpenAI-compatible call
        from openai import OpenAI
        client = OpenAI()
        mdl = model or os.getenv("OPENAI_MODEL","gpt-4o-mini")
        r = client.chat.completions.create(
            model=mdl, temperature=temperature,
            messages=[
                {"role":"system","content":"You output warm, compliant HTML paragraphs. Use <h3 class='sub'> subheads. Only use <table class='mini'> for tools and funding. Avoid bullet lists elsewhere."},
                {"role":"user","content": prompt},
            ],
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

# ----------------- Prompts -----------------

def _load_prompt(lang: str, chapter: str) -> str:
    # Prompts are optional here; if not present, we build minimal directives.
    p = BASE_DIR / "prompts" / lang / f"{chapter}.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    # minimal defaults
    if lang=="en":
        defaults = {
            "exec_summary":"Write an executive narrative that anchors on the company's main product/service, size and region. Be concrete about next steps and benefits/risks. Human approval before sending.",
            "quick_wins":"Describe 3–4 safe, reversible first moves as paragraphs.",
            "risks":"Explain practical risks and how to mitigate them (data spill, hallucinations, lock-in, over-automation).",
            "recommendations":"Give 3–4 pragmatic recommendations tailored to the profile.",
            "roadmap":"Plan with time anchors without digits: “immediately”, “in the coming weeks”, “within a year”.",
            "vision":"Describe a useful, credible vision.",
            "gamechanger":"Name a realistic game-changer and side effects.",
            "compliance":"Address GDPR, ePrivacy, DSA and EU AI Act plainly.",
            "tools":"Comment on the tool table and how to choose among EU options.",
            "funding":"Comment on the funding table and a mini-path to apply.",
            "live":"Summarize notable news/tools discovered recently (if any).",
            "trusted_check":"Explain how to use the Trusted AI check one-pager."
        }
    else:
        defaults = {
            "exec_summary":"Schreiben Sie eine Executive Summary, die auf dem wichtigsten Produkt/der Hauptleistung, der Unternehmensgröße und dem Standort aufsetzt. Seien Sie konkret zu nächsten Schritten sowie Nutzen/Risiken. Menschliche Freigabe vor Versand.",
            "quick_wins":"Beschreiben Sie 3–4 sichere, reversible erste Schritte als Absätze.",
            "risks":"Erklären Sie pragmatische Risiken und Gegenmaßnahmen (Datenabfluss, Halluzinationen, Lock-in, Überautomatisierung).",
            "recommendations":"Formulieren Sie 3–4 umsetzbare Empfehlungen, zugeschnitten auf das Profil.",
            "roadmap":"Planen Sie mit Zeitankern ohne Ziffern: „sofort“, „in den nächsten Wochen“, „innerhalb eines Jahres“.",
            "vision":"Skizzieren Sie eine hilfreiche, glaubwürdige Vision.",
            "gamechanger":"Nennen Sie einen realistischen Gamechanger und Nebenwirkungen.",
            "compliance":"Adressieren Sie DSGVO, ePrivacy, DSA und EU‑AI‑Act verständlich.",
            "tools":"Kommentieren Sie die Tool‑Tabelle und die Auswahlkriterien (EU‑Optionen).",
            "funding":"Kommentieren Sie die Förder‑Tabelle und einen Mini‑Pfad zur Antragstellung.",
            "live":"Fassen Sie auffällige News/Tools der letzten Zeit (falls vorhanden) zusammen.",
            "trusted_check":"Erklären Sie kurz, wie die Trusted‑KI‑Check‑Seite genutzt wird."
        }
    return defaults.get(chapter,"")

def _build_prompt(lang: str, chapter: str, ctx: Dict[str,Any]) -> str:
    rules_de = ("Narrative Absätze, per Sie, freundlich, optimistisch; keine Listen (außer Tools/Förderung als <table class='mini'>). "
                "EU‑Hosting bevorzugen, Alltagstauglichkeit. Keine Prozentzahlen. "
                "Verankern Sie die Empfehlungen hart am Profil: hauptleistung (wichtigstes Produkt/Dienstleistung), unternehmensgroesse, bundesland.")
    rules_en = ("Narrative paragraphs, polite and optimistic; no lists (except Tools/Funding as <table class='mini'>). "
                "Prefer EU hosting, everyday usefulness. No percentages. "
                "Anchor advice on: main product/service, company size, region/state.")
    rules = rules_de if lang=="de" else rules_en
    if chapter=="roadmap":
        rules += " Zeitanker ohne Ziffern (sofort / in den nächsten Wochen / innerhalb eines Jahres)." if lang=="de" else " Use time anchors without digits (immediately / in the coming weeks / within a year)."
    prompt = _load_prompt(lang, chapter)
    ctx_json = json.dumps(ctx, ensure_ascii=False)
    return f"{prompt}\n\n---\nKontext/Context:\n{ctx_json}\n\n---\nRegeln/Rules:\n{rules}\n"

# ----------------- Live Layer (Tavily) -----------------

async def _tavily_search(query: str, max_results: int=5, timeout_s: int=10) -> List[Dict[str,Any]]:
    if not TAVILY_KEY:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_KEY,
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "max_results": max_results,
        "days": SEARCH_DAYS,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            return data.get("results",[]) or []
    except Exception:
        return []

def _read_csv(path: Path) -> List[Dict[str,str]]:
    if not path.exists(): return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _curated_tools() -> List[Dict[str,str]]:
    return _read_csv(DATA_DIR / "tools_catalog.csv")

def _curated_funding() -> List[Dict[str,str]]:
    return _read_csv(DATA_DIR / "funding_catalog.csv")

def _rank_tools_for_profile(tools: List[Dict[str,str]], profile: Dict[str,str]) -> List[Dict[str,str]]:
    # naive ranking by category relevance and EU flag
    main = (profile.get("hauptleistung") or "").lower()
    branche = (profile.get("branche") or "").lower()
    size = (profile.get("unternehmensgroesse") or "")
    want_crm = any(x in main for x in ("kunden","vertrieb","crm","angebote","service"))
    want_content = any(x in main for x in ("text","content","inhalt","social","kampagne","video","präsentation"))
    want_prod = any(x in main for x in ("produktion","fertigung","sensor","maschine","logistik"))
    scored = []
    for row in tools:
        score = 0
        if row.get("eu_hosted","").lower() in ("yes","true","1","eu"): score += 3
        cat = row.get("category","").lower()
        if want_crm and "crm" in cat: score += 3
        if want_content and ("writing" in cat or "research" in cat): score += 2
        if want_prod and ("automation" in cat or "erp" in cat): score += 2
        if "automation" in cat: score += 1
        if branche in (row.get("industry_hint","") or "").lower(): score += 1
        scored.append((score,row))
    scored.sort(key=lambda x: (-x[0], x[1].get("name","")))
    return [r for _,r in scored[:6]]

def _rank_funding_for_region(funds: List[Dict[str,str]], region: str, size: str) -> List[Dict[str,str]]:
    region = normalize_region(region)
    out = []
    for row in funds:
        scope = (row.get("region_scope","") or "").lower()
        if scope in ("eu","de") or region in (row.get("region","") or "").lower().split("|"):
            if size in (row.get("size_fit","") or "") or row.get("size_fit","")=="all":
                out.append(row)
    # limit
    return out[:6]

def _render_tools_table(rows: List[Dict[str,str]], lang: str) -> str:
    if not rows:
        return ""
    if lang=="en":
        head = "<tr><th>Tool</th><th>What for</th><th>EU notes</th></tr>"
    else:
        head = "<tr><th>Tool</th><th>Wozu</th><th>EU‑Hinweise</th></tr>"
    body = []
    for r in rows:
        name = r.get("name","").strip()
        what = r.get("what","").strip()
        eu = r.get("eu_note","").strip()
        body.append(f"<tr><td>{name}</td><td>{what}</td><td>{eu}</td></tr>")
    return f"<table class='mini'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def _render_funding_table(rows: List[Dict[str,str]], lang: str) -> str:
    if not rows: return ""
    if lang=="en":
        head = "<tr><th>Programme</th><th>Good fit when…</th><th>Notes</th></tr>"
    else:
        head = "<tr><th>Programm</th><th>Geeignet wenn…</th><th>Hinweise</th></tr>"
    body = []
    for r in rows:
        name = r.get("name","").strip()
        fit = r.get("fit","").strip()
        note = r.get("note","").strip()
        body.append(f"<tr><td>{name}</td><td>{fit}</td><td>{note}</td></tr>")
    return f"<table class='mini'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

async def _live_tools(profile: Dict[str,str], lang: str) -> List[Dict[str,str]]:
    if not TAVILY_KEY: return []
    region = normalize_region(profile.get("bundesland") or "")
    main = profile.get("hauptleistung") or ""
    queries = []
    if lang=="de":
        queries = [
            f"EU gehostetes CRM KMU {region} 2025 Beispiele",
            "EU Schreibassistent Datenschutz konform 2025 Beispiele",
            "Open source Automatisierung EU self host 2025 n8n Alternativen",
        ]
    else:
        queries = [
            f"EU hosted CRM SME {region} 2025 examples",
            "EU writing assistant privacy friendly 2025 examples",
            "open source automation EU self host 2025 n8n alternatives",
        ]
    # Merge top results heuristically (name extraction is fuzzy; we keep short titles)
    results: List[Dict[str,str]] = []
    for q in queries:
        hits = await _tavily_search(q, max_results=4)
        for h in hits:
            title = (h.get("title") or "").strip()
            if not title: continue
            # keep brand-like first token
            brand = title.split("—")[0].split("|")[0].split(" - ")[0].strip()
            if len(brand)>60: brand = brand[:60]
            # naive category guess
            cat = "crm" if "crm" in q.lower() else ("writing" if "write" in q.lower() or "schreib" in q.lower() else "automation")
            results.append({
                "name": brand,
                "category": cat,
                "what": "Kundenfäden bündeln" if cat=="crm" and lang=="de" else ("Customer threads & notes" if cat=="crm" else ("Texte & Recherche" if lang=="de" else "Writing & research")),
                "eu_hosted": "unknown",
                "eu_note": "EU‑Region/ADV prüfen" if lang=="de" else "Check EU region/DPA",
                "industry_hint": "",
            })
    # de-duplicate by name
    seen=set(); dedup=[]
    for r in results:
        if r["name"].lower() in seen: continue
        seen.add(r["name"].lower()); dedup.append(r)
    return dedup[:6]

async def _live_funding(profile: Dict[str,str], lang: str) -> List[Dict[str,str]]:
    if not TAVILY_KEY: return []
    region = normalize_region(profile.get("bundesland") or "")
    size = profile.get("unternehmensgroesse") or ""
    if lang=="de":
        q = f"{region} Förderung Digitalisierung KMU 2025 Programm Antrag Fristen"
    else:
        q = f"{region} funding digitalisation SME 2025 programme apply deadline"
    hits = await _tavily_search(q, max_results=8)
    out = []
    for h in hits:
        title = (h.get("title") or "").strip()
        if not title: continue
        name = title.split("—")[0].split("|")[0].split(" - ")[0].strip()
        if len(name)>80: name = name[:80]
        out.append({
            "name": name,
            "fit": "KMU / Pilot / Qualifizierung" if lang=="de" else "SME / pilot / upskilling",
            "note": "Details & Fristen prüfen" if lang=="de" else "Check details & deadlines",
            "region_scope":"regional",
            "region": region,
            "size_fit": size or "all"
        })
    # de-duplicate
    seen=set(); dedup=[]
    for r in out:
        if r["name"].lower() in seen: continue
        seen.add(r["name"].lower()); dedup.append(r)
    return dedup[:6]

# ----------------- Chapter generation -----------------

CHAPTERS = [
    "exec_summary","quick_wins","risks","recommendations","roadmap",
    "vision","gamechanger","compliance","tools","funding","live","trusted_check"
]

def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(enabled_extensions=("html",)))

def _tpl_name(lang: str) -> str: return "pdf_template_en.html" if lang=="en" else "pdf_template.html"

def _chapter_key(ch: str) -> str: return f"{ch}_html"

def _profile_from_data(data: Dict[str,Any]) -> Dict[str,str]:
    return {
        "branche": str(data.get("branche","")),
        "unternehmensgroesse": str(data.get("unternehmensgroesse","")),
        "bundesland": normalize_region(data.get("bundesland","")),
        "hauptleistung": str(data.get("hauptleistung","")),
        "zielgruppen": ", ".join(data.get("zielgruppen") or []),
    }

def _postprocess(outputs: Dict[str,str]) -> Dict[str,str]:
    out: Dict[str,str] = {}
    for k, v in outputs.items():
        if not k.endswith("_html"):
            out[k]=v; continue
        out[k] = _sanitize_text(v) if k in {"roadmap_html","funding_html","tools_html","live_html"} else _strip_lists_and_numbers(v)
    return out

async def analyze_async(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> Dict[str,str]:
    lang = lang if lang in LANGS else DEFAULT_LANG
    profile = _profile_from_data(data)
    # Build global context
    ctx = dict(data)
    ctx["profile"] = profile
    ctx["now"] = dt.date.today().isoformat()
    # Generate chapters (LLM)
    outputs: Dict[str,str] = {}
    for ch in CHAPTERS:
        try:
            prompt = _build_prompt(lang, ch, ctx)
            outputs[_chapter_key(ch)] = _llm_complete(prompt, model=os.getenv("ANALYZE_MODEL"), temperature=temperature)
        except Exception:
            outputs[_chapter_key(ch)] = ""
    out = _postprocess(outputs)

    # Tools + Funding tables (live or curated)
    tools_rows: List[Dict[str,str]] = []
    funding_rows: List[Dict[str,str]] = []

    try:
        tools_rows = await _live_tools(profile, lang)
    except Exception:
        tools_rows = []
    if not tools_rows:
        tools_rows = _rank_tools_for_profile(_curated_tools(), profile)

    try:
        funding_rows = await _live_funding(profile, lang)
    except Exception:
        funding_rows = []
    if not funding_rows:
        funding_rows = _rank_funding_for_region(_curated_funding(), profile.get("bundesland",""), profile.get("unternehmensgroesse",""))

    # Inject tables in front of LLM text
    tools_table = _render_tools_table(tools_rows, lang)
    funding_table = _render_funding_table(funding_rows, lang)
    out["tools_html"] = f"{tools_table}\n{out.get('tools_html','')}".strip()
    out["funding_html"] = f"{funding_table}\n{out.get('funding_html','')}".strip()

    # Trusted check fallback if empty
    if not out.get("trusted_check_html"):
        if lang=="en":
            out["trusted_check_html"] = (
              "<p>The Trusted AI Check ensures privacy, traceability and reversibility.</p>"
              "<table class='mini'><thead><tr><th>Criterion</th><th>How to recognise</th><th>Next step</th></tr></thead>"
              "<tbody><tr><td>Purpose & benefit</td><td>Clear, limited goal</td><td>Write 2–3 sentences</td></tr>"
              "<tr><td>Data & roles</td><td>Inputs known, roles assigned</td><td>Name owner & reviewer</td></tr>"
              "<tr><td>Human approval</td><td>Four‑eyes before sending</td><td>Checklist + sign‑off</td></tr>"
              "<tr><td>Logging & export</td><td>Events recorded, export possible</td><td>Enable logs, test export</td></tr>"
              "<tr><td>Deletion</td><td>Retention set & enforced</td><td>Define & test deletion</td></tr>"
              "<tr><td>Risk & mitigation</td><td>False outputs, data spill</td><td>Pilot, rollback, data minimisation</td></tr></tbody></table>"
            )
        else:
            out["trusted_check_html"] = (
              "<p>Der Trusted KI‑Check stellt Datenschutz, Nachvollziehbarkeit und Rückbaubarkeit sicher.</p>"
              "<table class='mini'><thead><tr><th>Kriterium</th><th>Woran erkennbar</th><th>Nächster Schritt</th></tr></thead>"
              "<tbody><tr><td>Zweck & Nutzen</td><td>Klares, begrenztes Ziel</td><td>2–3 Sätze formulieren</td></tr>"
              "<tr><td>Daten & Rollen</td><td>Eingaben bekannt, Rollen vergeben</td><td>Owner & Reviewer benennen</td></tr>"
              "<tr><td>Menschliche Freigabe</td><td>Vier‑Augen vor Versand</td><td>Checkliste + Sign‑off</td></tr>"
              "<tr><td>Logging & Export</td><td>Ereignisse protokolliert, Export möglich</td><td>Logs aktivieren, Export testen</td></tr>"
              "<tr><td>Löschung</td><td>Aufbewahrung festgelegt & durchgesetzt</td><td>Löschkonzept definieren & testen</td></tr>"
              "<tr><td>Risiko & Mitigation</td><td>Fehlausgaben, Datenabfluss</td><td>Probelauf, Rückbau, Datensparsamkeit</td></tr></tbody></table>"
            )

    return out

def analyze(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> Dict[str,str]:
    return asyncio.get_event_loop().run_until_complete(analyze_async(data, lang, temperature))

def analyze_briefing(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> Dict[str,Any]:
    sections = analyze(data, lang=lang, temperature=temperature)
    meta = {
        "title": (data.get("meta",{}) or {}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": data.get("branche") or "",
        "groesse": data.get("unternehmensgroesse") or data.get("size") or "",
        "standort": data.get("standort") or data.get("region") or data.get("bundesland") or "",
    }
    ctx = {"meta": meta}
    ctx.update(sections)
    return ctx

def analyze_to_html(data: Dict[str,Any], lang: str=DEFAULT_LANG, temperature: float=0.35) -> str:
    sections = analyze(data, lang=lang, temperature=temperature)
    env = _env()
    tpl = env.get_template(_tpl_name(lang))
    meta = {
        "title": (data.get("meta",{}) or {}).get("title") or ("KI‑Statusbericht" if lang=="de" else "AI Status Report"),
        "date": dt.date.today().strftime("%d.%m.%Y") if lang=="de" else dt.date.today().isoformat(),
        "lang": lang,
        "branche": data.get("branche") or "",
        "groesse": data.get("unternehmensgroesse") or data.get("size") or "",
        "standort": data.get("standort") or data.get("region") or data.get("bundesland") or "",
    }
    html = tpl.render(meta=meta, **sections, now=dt.datetime.now)
    if not html or len(html) < MIN_HTML_LEN or "<h2" not in html:
        html = tpl.render(meta=meta, **sections, now=dt.datetime.now)
    return html
