# gpt_analyze.py — Gold-Standard
# Version: 2025-09-20-gold
# Features:
# - Live-Layer (Tavily / SerpAPI fallback) für "Live-Updates"-Abschnitt
# - Robuster Prompt-Resolver mit Kompat-Layer (prompts/, prompts_unzip/)
# - Persona-/Kapitel-Prompts, optionale Kontext-Prompts (praxisbeispiel.md, foerderprogramme.md, tools.md)
# - Sanitisierung: entfernt Code-Fences, Bullet-Listen, nackte Zahlen/Einheiten
# - Volle Template-Integration (setzt 'meta'), keine leeren PDFs
# - Fallbacks für Vision & Praxisbeispiel; narrative Förder-/Tool-Texte (CSV/MD)
# - Keine "return outside function" / NameError

import os, re, json, csv, zipfile, mimetypes
from pathlib import Path
from datetime import datetime as _dt
from typing import Dict, Any, Optional, List, Tuple

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

# OpenAI Client (verwende Umgebungsvariable GPT_MODEL_NAME / EXEC_SUMMARY_MODEL)
from openai import OpenAI
client = OpenAI()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

# Optionales Post-Processing (wenn vorhanden)
try:
    from postprocess_report import postprocess_report_dict  # type: ignore[attr-defined]
except Exception:
    postprocess_report_dict = None

# --- ZIP-Autounpack (Prompts/Kontexte/Daten) ---
def _ensure_unzipped(zip_name: str, dest_dir: str):
    try:
        z = BASE_DIR / zip_name
        d = BASE_DIR / dest_dir
        if z.exists() and not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(z), "r") as zf:
                zf.extractall(str(d))
    except Exception:
        pass

_ensure_unzipped("prompts.zip", "prompts_unzip")
_ensure_unzipped("branchenkontext.zip", "branchenkontext")
_ensure_unzipped("data.zip", "data")
_ensure_unzipped("aus-Data.zip", "data")  # falls extern geliefert

# --- Helpers: Modellwahl / Branche / Größe ---
def _resolve_model(wanted: Optional[str]) -> str:
    fallbacks = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    w = (wanted or "").strip().lower()
    if not w or w.startswith("gpt-5"):
        return fallbacks[0]
    known = set(fallbacks) | {"gpt-4.1", "gpt-4.1-mini"}
    return w if w in known else fallbacks[0]

def _extract_branche(d: Dict[str, Any]) -> str:
    raw = (str(d.get("branche") or d.get("industry") or d.get("sector") or "")).strip().lower()
    m = {
        "beratung":"beratung","consulting":"beratung","dienstleistung":"beratung","services":"beratung",
        "it":"it","software":"it","information technology":"it","saas":"it","kollaboration":"it",
        "marketing":"marketing","werbung":"marketing","advertising":"marketing",
        "bau":"bau","construction":"bau","architecture":"bau",
        "industrie":"industrie","produktion":"industrie","manufacturing":"industrie",
        "handel":"handel","retail":"handel","e-commerce":"handel","ecommerce":"handel",
        "finanzen":"finanzen","finance":"finanzen","insurance":"finanzen",
        "gesundheit":"gesundheit","health":"gesundheit","healthcare":"gesundheit",
        "medien":"medien","media":"medien","kreativwirtschaft":"medien",
        "logistik":"logistik","logistics":"logistik","transport":"logistik",
        "verwaltung":"verwaltung","public administration":"verwaltung",
        "bildung":"bildung","education":"bildung"
    }
    if raw in m: 
        return m[raw]
    for k,v in m.items():
        if k in raw:
            return v
    return "default"

def _as_int(x) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None

def is_self_employed(data: dict) -> bool:
    keys_text = ["beschaeftigungsform","beschäftigungsform","arbeitsform","rolle","role","occupation","unternehmensform","company_type"]
    txt = " ".join(str(data.get(k, "") or "") for k in keys_text).lower()
    if any(s in txt for s in ["selbst","freelanc","solo","self-employ"]):
        return True
    for k in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
        n = _as_int(data.get(k))
        if n is not None and n <= 1:
            return True
    return False

# --- Dateilader ---
def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

# --- Sanitizer: Code-Fences / Listen / Zahlen ---
def _strip_code_fences(text: str) -> str:
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html","```").replace("```HTML","```")
    while "```" in t:
        t = t.replace("```","")
    return t.replace("`","")

def _sanitize_text(value: str) -> str:
    if not value:
        return value
    text = str(value)
    # unsichtbare Zeichen u. typische „�“
    for ch in ["\uFFFE","\uFEFF","\u200B","\u00AD","�"]:
        text = text.replace(ch, "")
    # GPT->LLM neutralisieren
    repl = {
        "GPT-Analyse":"LLM-gestützte Analyse", "GPT‑Analyse":"LLM-gestützte Analyse",
        "GPT-gestützt":"LLM-gestützte", "GPT‑gestützt":"LLM-gestützte",
        "GPT-gestützte":"LLM-gestützte", "GPT‑gestützte":"LLM-gestützte",
        "GPT-Prototyp":"KI-Prototyp","GPT‑Prototyp":"KI-Prototyp",
        "GPT-Portal":"KI-Portal","GPT‑Portal":"KI-Portal",
    }
    for a,b in repl.items():
        text = text.replace(a,b)
    return text

_NUMBER_PAT = re.compile(r"(?:\b\d{1,3}(?:[\.,]\d{1,3})*(?:%|[kKmMbB])?\b)|(?:\b\d+ ?(?:%|EUR|€|USD)\b)")
_BULLET_PAT = re.compile(r"^\s*[-–—•\*]\s*", re.MULTILINE)

def _strip_lists_and_numbers(raw: str) -> str:
    """entfernt Listen-Markierungen + nackte Zahlen/Einheiten; erzeugt saubere Absätze"""
    if not raw:
        return raw
    t = _sanitize_text(_strip_code_fences(str(raw)))
    # Listenpunkte in Fließtext überführen
    t = _BULLET_PAT.sub("", t)
    t = t.replace("</li>", " ").replace("<li>", "")
    t = t.replace("<ul>", "").replace("</ul>", "")
    t = t.replace("<ol>", "").replace("</ol>", "")
    # nackte Zahlen/Prozent/Einheiten entfernen
    t = _NUMBER_PAT.sub("", t)
    # überzählige Leerzeichen/Kommas glätten
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r",\s*,", ", ", t)
    return t.strip()

def _ensure_html(text: str, lang: str = "de") -> str:
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    html = []
    in_ul = False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul:
                html.append("<ul>"); in_ul = True
            html.append("<li>"+re.sub(r"^[-•*]\s+","",ln)+"</li>")
            continue
        if in_ul:
            html.append("</ul>"); in_ul = False
        html.append("<p>"+ln+"</p>")
    if in_ul: html.append("</ul>")
    return "\n".join(html)

# --- CSV/MD Hilfen ---
def _find_data_file(candidates: List[str]) -> Optional[Path]:
    for n in candidates:
        p = BASE_DIR/"data"/n
        if p.exists(): return p
    for n in candidates:
        p = BASE_DIR/n
        if p.exists(): return p
    nested = BASE_DIR/"ki_backend"/"make-ki-backend-neu-main"/"data"
    for n in candidates:
        p = nested/n
        if p.exists(): return p
    return None

def _read_csv_rows(path: Path) -> List[Dict[str,str]]:
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k,v in r.items()} for r in rd]
    except Exception:
        return []

def _read_md_table(path: Path) -> List[Dict[str,str]]:
    if not path or not path.exists():
        return []
    try:
        lines = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception:
        return []
    if len(lines) < 2 or "|" not in lines[0] or "|" not in lines[1]:
        return []
    headers = [h.strip().strip("|").strip() for h in lines[0].split("|") if h.strip()]
    rows: List[Dict[str,str]] = []
    for ln in lines[2:]:
        if "|" not in ln: continue
        cells = [c.strip().strip("|").strip() for c in ln.split("|")]
        if not any(cells): continue
        row = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}
        rows.append(row)
    return rows
# --- Förderprogramme (Struktur + Narrative) ---
def _norm_size(x: str) -> str:
    x = (x or "").lower()
    if x in {"solo","einzel","einzelunternehmer","freelancer","soloselbstständig","soloselbststaendig"}: return "solo"
    if x in {"team","small"}: return "team"
    if x in {"kmu","sme","mittelstand"}: return "kmu"
    return ""

def build_funding_details_struct(data: Dict[str,Any], lang: str="de", max_items: int=8) -> Tuple[List[Dict[str,Any]], str]:
    path = _find_data_file(["foerdermittel.csv","foerderprogramme.csv"])
    rows = _read_csv_rows(path) if path else []
    out: List[Dict[str,Any]] = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")
    region = (str(data.get("bundesland") or data.get("state") or "")).lower()
    if region == "be": region = "berlin"

    for r in rows:
        name = r.get("name") or r.get("programm") or r.get("Program") or r.get("Name")
        if not name: continue
        target = (r.get("zielgruppe") or r.get("target") or r.get("Zielgruppe") or "").lower()
        reg = (r.get("region") or r.get("bundesland") or r.get("land") or r.get("Region") or "").lower()
        grant = r.get("foerderart") or r.get("grant") or r.get("quote") or r.get("kosten") or r.get("Fördersumme (€)")
        use_case = r.get("einsatz") or r.get("zweck") or r.get("beschreibung") or r.get("use_case") or r.get("Beschreibung") or ""
        link = r.get("link") or r.get("url") or r.get("Link") or ""

        # Größe grob filtern (kmu zählt auch für team)
        if size and target:
            if size not in target and not (target=="kmu" and size in {"team","kmu"}):
                continue

        score = 0
        if region and reg == region: score -= 5
        if reg in {"bund","deutschland","de"}: score -= 1

        out.append({
            "name": name,
            "target": r.get("zielgruppe") or r.get("target") or r.get("Zielgruppe") or "",
            "region": r.get("region") or r.get("bundesland") or r.get("land") or r.get("Region") or "",
            "grant": grant or "",
            "use_case": use_case,
            "link": link,
            "_score": score
        })

    out = sorted(out, key=lambda x: x.get("_score",0))[:max_items]
    for o in out: o.pop("_score", None)

    stand = ""
    try:
        if path: stand = _dt.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    except Exception:
        pass

    return out, stand

def build_funding_narrative(data: Dict[str,Any], lang: str="de", max_items: int=6) -> str:
    rows, _ = build_funding_details_struct(data, lang, max_items)
    if not rows: return ""
    ps = []
    if lang.startswith("de"):
        for r in rows:
            p = f"<p><b>{r['name']}</b> – geeignet für {r.get('target','KMU')}, Region: {r.get('region','DE')}. "
            if r.get('use_case'): p += f"{r['use_case']} "
            if r.get('grant'):    p += f"<i>Förderart/Kosten: {r['grant']}</i> "
            if r.get('link'):     p += f'<a href="{r["link"]}">Zum Programm</a>'
            p += "</p>"; ps.append(p)
    else:
        for r in rows:
            p = f"<p><b>{r['name']}</b> – suitable for {r.get('target','SMEs')}, region: {r.get('region','DE')}. "
            if r.get('use_case'): p += f"{r['use_case']} "
            if r.get('grant'):    p += f"<i>Grant/Costs: {r['grant']}</i> "
            if r.get('link'):     p += f'<a href="{r["link"]}">Open</a>'
            p += "</p>"; ps.append(p)
    return "\n".join(ps)

# --- Tools (Struktur + Narrative) ---
def build_tools_details_struct(data: Dict[str,Any], branche: str, lang: str="de", max_items: int=12) -> Tuple[List[Dict[str,Any]], str]:
    path = _find_data_file(["tools.csv","ki_tools.csv"])
    rows = _read_csv_rows(path) if path else []
    out: List[Dict[str,Any]] = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")

    for r in rows:
        name = r.get("name") or r.get("Tool") or r.get("Tool-Name")
        if not name: continue
        tags = (r.get("Branche-Slugs") or r.get("Tags") or r.get("Branche") or "").lower()
        row_size = (r.get("Unternehmensgröße") or r.get("Unternehmensgroesse") or r.get("company_size") or "").lower()

        if branche and tags and branche not in tags: 
            continue
        if size and row_size and row_size not in {"alle", size}:
            if not ((row_size=="kmu" and size in {"team","kmu"}) or (row_size=="team" and size=="solo")):
                continue

        out.append({
            "name": name,
            "category": r.get("kategorie") or r.get("category") or "",
            "suitable_for": r.get("eignung") or r.get("use_case") or r.get("einsatz") or "",
            "hosting": r.get("hosting") or r.get("datenschutz") or r.get("data") or "",
            "price": r.get("preis") or r.get("price") or r.get("kosten") or "",
            "link": r.get("link") or r.get("url") or "",
        })
    return out[:max_items], ""

def build_tools_narrative(data: Dict[str,Any], branche: str, lang: str="de", max_items: int=6) -> str:
    rows, _ = build_tools_details_struct(data, branche, lang, max_items)
    if not rows: return ""
    ps = []
    if lang.startswith("de"):
        for r in rows:
            p  = f"<p><b>{r['name']}</b> ({r.get('category','')}) – geeignet für {r.get('suitable_for','Alltag')}. "
            p += f"Hosting/Datenschutz: {r.get('hosting','n/a')}; Preis: {r.get('price','n/a')}. "
            if r.get('link'): p += f'<a href="{r["link"]}">Zur Website</a>'
            p += "</p>"; ps.append(p)
    else:
        for r in rows:
            p  = f"<p><b>{r['name']}</b> ({r.get('category','')}) – suitable for {r.get('suitable_for','daily work')}. "
            p += f"Hosting/data: {r.get('hosting','n/a')}; price: {r.get('price','n/a')}. "
            if r.get('link'): p += f'<a href="{r["link"]}">Website</a>'
            p += "</p>"; ps.append(p)
    return "\n".join(ps)

# --- Live Layer (Tavily -> SerpAPI fallback) ---
def _tavily_search(query: str, max_results: int = 5, days: Optional[int] = None) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY","").strip()
    if not key:
        return []
    payload = {
        "api_key": key, "query": query, "max_results": max_results,
        "include_answer": False, "search_depth": os.getenv("SEARCH_DEPTH","basic")
    }
    if days: payload["days"] = days
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
            res = []
            for item in data.get("results", [])[:max_results]:
                res.append({
                    "title": item.get("title"), "url": item.get("url"),
                    "content": item.get("content"), "published_date": item.get("published_date"),
                    "score": item.get("score")
                })
            return res
    except Exception:
        return []

def _serpapi_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    key = os.getenv("SERPAPI_KEY","").strip()
    if not key:
        return []
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.get("https://serpapi.com/search.json", params={"q": query, "num": max_results, "api_key": key})
            r.raise_for_status()
            data = r.json()
            res = []
            for item in data.get("organic_results", [])[:max_results]:
                res.append({"title": item.get("title"), "url": item.get("link"), "content": item.get("snippet")})
            return res
    except Exception:
        return []

def build_live_updates_html(data: Dict[str, Any], lang: str = "de", max_results: int = 5) -> Tuple[str, str]:
    branche = _extract_branche(data)
    size = str(data.get("unternehmensgroesse") or data.get("company_size") or "").strip().lower()
    region = str(data.get("bundesland") or data.get("state") or data.get("ort") or data.get("city") or "").strip()
    product = str(data.get("hauptleistung") or data.get("hauptprodukt") or data.get("main_product") or "").strip()
    topic = str(data.get("search_topic") or "").strip()
    days = int(os.getenv("SEARCH_DAYS", "30"))
    base_de = f"Förderprogramm KI {region} {branche} {size}".strip()
    base_en = f"AI funding {region} {branche} {size}".strip()
    t_de = f"KI Tool {branche} {product} DSGVO".strip()
    t_en = f"GDPR-friendly AI tool {branche} {product}".strip()
    queries = [q for q in ([base_de, t_de, topic] if lang.startswith("de") else [base_en, t_en, topic]) if q]
    title = ("Neu seit " if lang.startswith("de") else "New since ") + _dt.now().strftime("%B %Y")

    seen, items = set(), []
    for q in queries:
        res = _tavily_search(q, max_results=max_results, days=days) or _serpapi_search(q, max_results=max_results)
        for r in res:
            url = (r.get("url") or "").strip()
            if not url or url in seen: 
                continue
            seen.add(url)
            date = r.get("published_date") or ""
            li = f'<li><a href="{url}">{(r.get("title") or url)[:120]}</a>'
            if date: li += f' <span style="color:#5B6B7C">({date})</span>'
            snippet = (r.get("content") or "")[:240].replace("<","&lt;").replace(">","&gt;")
            if snippet:
                li += f"<br><span style='color:#5B6B7C;font-size:12px'>{snippet}</span>"
            li += "</li>"
            items.append(li)

    html = "<ul>" + "".join(items[:max_results]) + "</ul>" if items else ""
    return title, html
# --- Kontextaufbau inkl. Kompat-Layer ----
def build_context(data: Dict[str, Any], branche: str, lang: str = "de") -> Dict[str, Any]:
    def _norm_lang(l: Optional[str]) -> str:
        x = (l or "de").lower().strip()
        return "de" if x.startswith("de") else "en"

    lang = _norm_lang(lang)
    # Branchenkontext (falls vorhanden)
    ctx_path = BASE_DIR/"branchenkontext"/f"{branche}.{lang}.yaml"
    if not ctx_path.exists():
        ctx_path = BASE_DIR/"branchenkontext"/f"default.{lang}.yaml"
    context = _load_yaml(ctx_path) if ctx_path.exists() else {}

    # Fragebogendaten überlagern
    context.update(data or {})
    context["lang"] = lang

    # Größe klassifizieren
    def _guess_count(d: dict) -> Optional[int]:
        for key in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
            n = _as_int(d.get(key))
            if n is not None:
                return n
        sz = (d.get("unternehmensgroesse") or d.get("company_size") or "").strip().lower()
        if sz:
            if any(s in sz for s in ["solo","einzel","self"]):
                return 1
            m = re.match(r"(\d+)", sz)
            if m:
                try: return int(m.group(1))
                except Exception: pass
        return None

    emp_count = _guess_count(context)
    self_emp = is_self_employed(context)

    if self_emp: cat = "solo"
    else:
        if emp_count is None:     cat = "team"
        elif emp_count <= 1:      cat = "solo"
        elif emp_count <= 10:     cat = "team"
        else:                     cat = "kmu"

    if lang == "de":
        label = "Solo-Unternehmer:in" if cat=="solo" else ("Team (2–10 Mitarbeitende)" if cat=="team" else "KMU (11+ Mitarbeitende)")
    else:
        label = "Solo entrepreneur" if cat=="solo" else ("Small team (2–10 people)" if cat=="team" else "SME (11+ people)")

    context["company_size_category"] = cat
    context["company_size_label"] = label
    context["unternehmensgroesse"] = label
    context["self_employed"] = "Yes" if self_emp else "No"
    context["selbststaendig"] = "Ja" if (self_emp and lang=="de") else ("Nein" if lang=="de" else context["self_employed"])

    # Branche normieren (englische Übersetzung)
    if lang != "de":
        tr = {"beratung":"consulting","bau":"construction","bildung":"education","finanzen":"finance",
              "gesundheit":"healthcare","handel":"trade","industrie":"industry","it":"IT",
              "logistik":"logistics","marketing":"marketing","medien":"media","verwaltung":"public administration"}
        context["branche"] = tr.get(branche, branche)
    else:
        context["branche"] = branche

    # bequeme Aliase
    context["hauptleistung"] = context.get("hauptleistung") or context.get("main_service") or context.get("hauptprodukt") or ""
    context["projektziel"] = context.get("projektziel") or context.get("ziel") or ""

    # Copyright/Fußzeile Defaults
    context.setdefault("copyright_year", _dt.now().year)
    context.setdefault("copyright_owner", "Wolf Hohl")

    return context

# --- Prompt-Resolver (mit Persona & Kompat) ---
def _read_prompt(chapter: str, lang: str) -> str:
    # Hauptpfad
    p = BASE_DIR/"prompts"/lang/f"{chapter}.md"
    if p.exists():
        return _load_text(p)
    # Kompat: prompts_unzip
    p2 = BASE_DIR/"prompts_unzip"/lang/f"{chapter}.md"
    if p2.exists():
        return _load_text(p2)
    # weitere einfache Fallbacks (alt)
    p3 = BASE_DIR/"prompts"/f"{chapter}_{lang}.md"
    if p3.exists():
        return _load_text(p3)
    return f"[NO PROMPT FOUND for {chapter}/{lang}]"

def _read_optional_context(lang: str) -> str:
    # optionale Kontext-Prompts einbinden (wenn vorhanden)
    ctx_parts = []
    for name in ["persona.md","praxisbeispiel.md","foerderprogramme.md","tools.md"]:
        for base in [BASE_DIR/"prompts"/lang, BASE_DIR/"prompts_unzip"/lang]:
            p = base/name
            if p.exists():
                ctx_parts.append(_load_text(p))
                break
    return "\n\n".join(ctx_parts)

def _render_prompt_vars(tpl: str, ctx: Dict[str,Any]) -> str:
    # {{ var }} und {{ list|join(', ') }}
    def _join(m):
        key, sep = m.group(1), m.group(2)
        val = ctx.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)
    tpl = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", _join, tpl)
    def _simple(m):
        key = m.group(1); val = ctx.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _simple, tpl)

def build_masterprompt(chapter: str, context: Dict[str,Any], lang: str) -> str:
    base = _read_prompt(chapter, lang)
    opt_ctx = _read_optional_context(lang)
    rendered = _render_prompt_vars(base, context)
    if opt_ctx:
        rendered = rendered + "\n\n---\n" + opt_ctx

    is_de = (lang == "de")
    base_rules = (
        "Gib die Antwort ausschließlich als gültiges HTML ohne <html>-Wrapper zurück. "
        "Verwende nur <h3> und <p>. Keine Listen, keine Tabellen, keine Aufzählungen. "
        "Formuliere 2–3 zusammenhängende Absätze, freundlich, motivierend, konkret und umsetzbar. "
        "Integriere kurze Best‑Practice‑Beispiele. Keine Zahlen/Prozentwerte."
        if is_de else
        "Return VALID HTML only (no <html> wrapper). Use only <h3> and <p>. "
        "Avoid lists and tables. Write 2–3 connected paragraphs; warm, motivating, concrete and actionable. "
        "Include a short best‑practice example. No numbers or percentages."
    )
    return rendered + "\n\n---\n" + base_rules

def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float]=None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME","gpt-5"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE","0.3"))
    if not str(args["model"]).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

def gpt_generate_section_html(data: Dict[str,Any], branche: str, chapter: str, lang: str="de") -> str:
    ctx = build_context(data, branche, lang)
    prompt = build_masterprompt(chapter, ctx, lang)
    default_model = os.getenv("GPT_MODEL_NAME","gpt-5")
    model_name = os.getenv("EXEC_SUMMARY_MODEL", default_model) if chapter=="executive_summary" else default_model
    html = _chat_complete(
        messages=[
            {"role":"system","content": (
                "Sie sind TÜV-zertifizierte:r KI-Manager:in, KI-Strategieberater:in sowie Datenschutz- und Fördermittel-Expert:in. "
                "Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
            ) if lang=="de" else (
                "You are a TÜV-certified AI manager and strategy consultant. "
                "Deliver precise, actionable, up-to-date, sector-relevant content as HTML."
            )},
            {"role":"user","content": prompt},
        ],
        model_name=model_name, temperature=None
    )
    return _ensure_html(_strip_lists_and_numbers(html), lang)

# --- Score/KPI (Platzhalter für Kompatibilität) ---
def calc_score_percent(data: dict) -> int:
    # Aggregierter Readiness-Score nicht mehr genutzt – für Alt-Code 0 zurückgeben
    return 0

def build_chart_payload(data: dict, score_percent: int, lang: str = "de") -> dict:
    # Dimensionen symbolisch – für alte Templates beibehalten
    labels_de = ["Digitalisierung","Automatisierung","Papierlos","KI-Know-how","Risikofreude","Datenqualität","Roadmap","Governance","Innovationskultur"]
    labels_en = ["Digitalisation","Automation","Paperless","AI know-how","Risk appetite","Data quality","AI roadmap","Governance","Innovation culture"]
    return {"score": score_percent, "dimensions": {"labels": (labels_de if lang=="de" else labels_en), "values": [0]*9}, "risk_level": 1}

# --- Fallbacks ---
def fallback_vision(data: dict, lang: str = "de") -> str:
    if lang=="de":
        return ("<p><b>Vision:</b> Ein schlankes KI‑Serviceportal für KMU, das Fragebögen, Tools und Wissen bündelt "
                "und so den Einstieg erleichtert. Starten Sie mit einem kleinen Prototypen und bauen Sie entlang "
                "der echten Nutzung aus.</p><p>Mit wachsender Erfahrung entsteht ein lebendiges Wissenswerk, das "
                "neue Dienstleistungen inspiriert – ohne Zahlen, mit Fokus auf Lernen und Wirkung.</p>")
    else:
        return ("<p><b>Vision:</b> A lean AI service portal for SMEs that bundles questionnaires, tools and knowledge "
                "to ease the first steps. Start with a small prototype and expand along real usage.</p>"
                "<p>Over time it becomes a living knowledge base that inspires new services – no numbers, "
                "focused on learning and impact.</p>")

def _fallback_praxisbeispiel(branche: str, lang: str = "de") -> str:
    md_path = BASE_DIR/"data"/"praxisbeispiele.md"
    if not md_path.exists():
        return ""
    # Sehr toleranter MD-Parser: nimm einfach die erste Case-Box nach Überschrift
    try:
        txt = _load_text(md_path)
        # grob erste Case-Zeilen aufsammeln
        lines = []
        capture = False
        for ln in txt.splitlines():
            if ln.strip().lower().startswith("**case"):
                capture = True
                continue
            if capture and ln.strip().startswith("**"):  # nächste fette Überschrift = Ende
                break
            if capture and ln.strip():
                lines.append(re.sub(r"^[\-\*\•]\s*","",ln.strip()))
        desc = " ".join(lines)
        return f"<p>{_strip_lists_and_numbers(desc)}</p>"
    except Exception:
        return ""
# --- Report-Bau & Rendering ---
def generate_full_report(data: Dict[str,Any], lang: str="de") -> Dict[str,Any]:
    lang = ("de" if str(lang).lower().startswith("de") else "en")
    branche = _extract_branche(data)

    sections = [
        "executive_summary","quick_wins","risks","recommendations",
        "roadmap","vision","gamechanger","compliance","praxisbeispiel"
    ]
    out: Dict[str,Any] = {}

    # Kapitel durch LLM erzeugen (robust; Fehler -> leer)
    for ch in sections:
        try:
            out[ch+"_html"] = gpt_generate_section_html(data, branche, ch, lang)
        except Exception:
            out[ch+"_html"] = ""

    # Vision-Fallback
    if not out.get("vision_html"):
        out["vision_html"] = fallback_vision(data, lang)

    # Praxisbeispiel-Fallback, falls leer
    if not out.get("praxisbeispiel_html"):
        out["praxisbeispiel_html"] = _fallback_praxisbeispiel(branche, lang)

    # Narrative Förderprogramme/Tools
    try:
        out["funding_html"] = build_funding_narrative(data, lang, max_items=6)
    except Exception:
        out["funding_html"] = ""
    try:
        out["tools_html"] = build_tools_narrative(data, branche, lang, max_items=8)
    except Exception:
        out["tools_html"] = ""

    # Live-Updates (mit Tavily/SerpAPI)
    try:
        title, live_html = build_live_updates_html(data, lang, max_results=5)
        out["live_title"] = title
        out["live_html"] = live_html
    except Exception:
        out["live_title"] = ""
        out["live_html"] = ""

    # Benchmarks/KPIs ausblenden (Kompat-Felder leer)
    out["benchmarks"] = {}
    out["kpi_badges_html"] = ""

    # Meta für Template zwingend setzen (verhindert 'meta is undefined')
    ort = data.get("ort") or data.get("city") or data.get("location") or ""
    groesse = data.get("unternehmensgroesse") or data.get("company_size") or ""
    out["meta"] = {
        "title": ("KI‑Statusbericht" if lang=="de" else "AI Readiness Report"),
        "subtitle": ("Narrativer KI‑Report – DSGVO & EU‑AI‑Act‑ready" if lang=="de" else "Narrative AI report – GDPR & EU AI Act‑ready"),
        "date": _dt.now().strftime("%d.%m.%Y") if lang=="de" else _dt.now().strftime("%Y-%m-%d"),
        "branche": branche,
        "size": groesse,
        "location": ort
    }

    # Globale Sanitisierung (Zahlen/Listen raus)
    for k in list(out.keys()):
        if k.endswith("_html"):
            out[k] = _strip_lists_and_numbers(out[k])

    # Optionales Postprocessing
    if postprocess_report_dict:
        try:
            out = postprocess_report_dict(out, lang=lang)  # type: ignore
        except Exception:
            pass

    return out

def analyze_briefing(body: Dict[str,Any], lang: str="de") -> str:
    """Entry-Point für main.py – liefert finales HTML für das PDF-Service."""
    if not isinstance(body, dict):
        try:
            body = json.loads(str(body))
        except Exception:
            body = {}
    lang = ("de" if str(lang).lower().startswith("de") else "en")

    report = generate_full_report(body or {}, lang=lang)

    # Jinja2-Rendering
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html","xml"])
    )
    tpl_name = "report_template_de.html" if lang=="de" else "report_template_en.html"
    tpl = env.get_template(tpl_name)

    ctx = {**report, "now": _dt.now, "lang": lang}
    html = tpl.render(**ctx)

    # Allerletzte Sicherung: Code-Fences & Sonderzeichen bereinigen
    html = _sanitize_text(_strip_code_fences(html))
    return html
