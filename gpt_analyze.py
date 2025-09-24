# gpt_analyze.py — Gold-Standard (Wolf Edition)
# Version: 2025-09-24
# Neu:
# - Coaching-Kapitel (coaching_html) nach "Empfehlungen"
# - Live-Layer mit Sanitizer (Whitelist/Blacklist, Dedupe, MaxLen, optionaler Score-Filter)
# - Förder-TABELLE: nur Programmnamen verlinkt, klare Spalten, dedupliziert
# - SEARCH_DAYS_FUNDING / SEARCH_DAYS_TOOLS Fallbacks (ansonsten SEARCH_DAYS / 14)
# - Prompt-Resolver akzeptiert PROMPTS_DIR und business-prompt_de/en.txt
# - Globale Sanitisierung nur für narrative Kapitel (Zahlen in Funding/Live bleiben erhalten)

from __future__ import annotations
import os, re, json, csv, zipfile
from pathlib import Path
from datetime import datetime as _dt
from typing import Dict, Any, Optional, List, Tuple
import httpx

from jinja2 import Environment, FileSystemLoader, select_autoescape
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

# ---------------- Basis-Helfer ----------------
def _env_bool(name: str, default: bool=False) -> bool:
    v = str(os.getenv(name, str(int(default)))).strip().lower()
    return v in {"1","true","yes","on"}

def _parse_domains(name: str) -> List[str]:
    raw = os.getenv(name, "") or ""
    return [d.strip().lower() for d in raw.split(",") if d.strip()]

def _resolve_model(wanted: Optional[str]) -> str:
    fallbacks = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    w = (wanted or "").strip().lower()
    if not w or w.startswith("gpt-5"):
        return fallbacks[0]
    known = set(fallbacks) | {"gpt-4.1", "gpt-4.1-mini"}
    return w if w in known else fallbacks[0]

def _as_int(x) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None

# ---------------- Klassifikatoren ----------------
def _extract_branche(d: Dict[str, Any]) -> str:
    raw = (str(d.get("branche") or d.get("industry") or d.get("sector") or "")).strip().lower()
    MAP = {
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
    if raw in MAP:
        return MAP[raw]
    for k,v in MAP.items():
        if k in raw:
            return v
    return "default"

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

# ---------------- Datei-/Kontextlader ----------------
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

def _find_data_file(candidates: List[str]) -> Optional[Path]:
    for n in candidates:
        p = BASE_DIR/"data"/n
        if p.exists(): return p
    for n in candidates:
        p = BASE_DIR/n
        if p.exists(): return p
    return None

# ---------------- Sanitizer (Text) ----------------
def _strip_code_fences(text: str) -> str:
    if not text: return text
    t = text.replace("\r", "")
    t = t.replace("```html","```").replace("```HTML","```")
    while "```" in t: t = t.replace("```","")
    return t.replace("`","")

def _sanitize_text(value: str) -> str:
    if not value: return value
    text = str(value)
    for ch in ["\uFFFE","\uFEFF","\u200B","\u00AD","�"]:
        text = text.replace(ch, "")
    repl = {
        "GPT-Analyse":"LLM-gestützte Analyse","GPT‑Analyse":"LLM-gestützte Analyse",
        "GPT-gestützt":"LLM-gestützte","GPT‑gestützt":"LLM-gestützte",
    }
    for a,b in repl.items(): text = text.replace(a,b)
    return text

_NUMBER_PAT = re.compile(r"(?:\b\d{1,3}(?:[\.,]\d{1,3})*(?:%|[kKmMbB])?\b)|(?:\b\d+ ?(?:%|EUR|€|USD)\b)")
_BULLET_PAT = re.compile(r"^\s*[-–—•\*]\s*", re.MULTILINE)

def _strip_lists_and_numbers(raw: str) -> str:
    """Nur für narrative Abschnitte verwenden (nicht für Funding/Live)."""
    if not raw: return raw
    t = _sanitize_text(_strip_code_fences(str(raw)))
    t = _BULLET_PAT.sub("", t)
    t = t.replace("</li>", " ").replace("<li>", "")
    t = t.replace("<ul>", "").replace("</ul>", "")
    t = t.replace("<ol>", "").replace("</ol>", "")
    t = _NUMBER_PAT.sub("", t)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r",\s*,", ", ", t)
    return t.strip()

def _ensure_html(text: str, lang: str = "de") -> str:
    t = (text or "").strip()
    if "<" in t and ">" in t: return t
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    html = []
    in_ul = False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul: html.append("<ul>"); in_ul = True
            html.append("<li>"+re.sub(r"^[-•*]\s+","",ln)+"</li>")
            continue
        if in_ul: html.append("</ul>"); in_ul = False
        html.append("<p>"+ln+"</p>")
    if in_ul: html.append("</ul>")
    return "\n".join(html)

# ---------------- CSV/MD ----------------
def _read_csv_rows(path: Path) -> List[Dict[str,str]]:
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k,v in r.items()} for r in rd]
    except Exception:
        return []

# ---------------- Funding (Daten + Renderer) ----------------
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

        if size and target:
            if size not in target and not (target=="kmu" and size in {"team","kmu"}):
                continue

        score = 0
        if region and reg == region: score -= 5
        if reg in {"bund","deutschland","de"}: score -= 1

        out.append({
            "name": name, "target": r.get("zielgruppe") or r.get("target") or r.get("Zielgruppe") or "",
            "region": r.get("region") or r.get("bundesland") or r.get("land") or r.get("Region") or "",
            "grant": grant or "", "use_case": use_case, "link": link, "_score": score
        })

    out = sorted(out, key=lambda x: x.get("_score",0))
    # Dedupe by name+link
    seen = set(); uniq = []
    for o in out:
        key = (o["name"].lower(), (o["link"] or "").lower())
        if key in seen: continue
        seen.add(key); uniq.append(o)
        if len(uniq) >= max_items: break

    stand = ""
    try:
        if path: stand = _dt.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    except Exception:
        pass
    for o in uniq: o.pop("_score", None)
    return uniq, stand

def build_funding_table_html(data: Dict[str,Any], lang: str="de", max_items: int=8) -> str:
    rows, stand = build_funding_details_struct(data, lang, max_items)
    if not rows: return ""
    th = ("Programm","Ebene/Region","Zielgruppe","Zuschuss/Kosten","Frist") if lang.startswith("de") \
         else ("Program","Level/Region","Target","Grant/Costs","Deadline")
    out = [f"<table><thead><tr>{''.join('<th>'+h+'</th>' for h in th)}</tr></thead><tbody>"]
    for r in rows:
        name = (r.get("name") or "").strip()
        link = (r.get("link") or "").strip()
        # NUR Programmnamen verlinken (keine "Zum Programm"-Texte)
        prog = f'<a href="{link}">{name}</a>' if link and name else (name or (link or ""))
        out.append(
            "<tr>"
            f"<td>{prog}</td>"
            f"<td>{(r.get('region') or '').strip()}</td>"
            f"<td>{(r.get('target') or '').strip()}</td>"
            f"<td>{(r.get('grant') or '').strip()}</td>"
            f"<td>{''}</td>"
            "</tr>"
        )
    out.append("</tbody></table>")
    if stand:
        out.append(f'<p style="color:#5B6B7C;font-size:12px">Stand: {stand}</p>')
    return "\n".join(out)

# ---------------- Tools (Narrativ) ----------------
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

# ---------------- Live-Suche (Tavily → SerpAPI) + Sanitizer ----------------
def _tavily_search(query: str, max_results: int = 5, days: Optional[int] = None) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY","").strip()
    if not key: return []
    payload = {
        "api_key": key, "query": query, "max_results": max_results,
        "include_answer": False, "search_depth": os.getenv("SEARCH_DEPTH","basic")
    }
    if days: payload["days"] = int(days)
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
                    "score": item.get("score"), "source": item.get("source")
                })
            return res
    except Exception:
        return []

def _serpapi_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    key = os.getenv("SERPAPI_KEY","").strip()
    if not key: return []
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.get("https://serpapi.com/search.json", params={"q": query, "num": max_results, "api_key": key})
            r.raise_for_status()
            data = r.json()
            res = []
            for item in data.get("organic_results", [])[:max_results]:
                res.append({"title": item.get("title"), "url": item.get("link"), "content": item.get("snippet"), "source": item.get("source")})
            return res
    except Exception:
        return []

def _domain_allowed(url: str, includes: List[str], excludes: List[str]) -> bool:
    u = (url or "").lower()
    if not u: return False
    for bad in excludes:
        if bad and bad in u: return False
    if not includes: return True
    for good in includes:
        if good and good in u: return True
    return False

def _sanitize_live_items(items: List[Dict[str,Any]], max_items: int, maxlen: int, min_score: float,
                         includes: List[str], excludes: List[str]) -> List[Dict[str,Any]]:
    seen, out = set(), []
    for r in items:
        url = (r.get("url") or "").strip()
        if not url or url in seen: 
            continue
        if not _domain_allowed(url, includes, excludes):
            continue
        score = float(r.get("score") or 1.0)
        if min_score and score < min_score:
            continue
        seen.add(url)
        title = (r.get("title") or url).strip()
        snippet = (r.get("content") or "").strip()
        snippet = snippet.replace("<","&lt;").replace(">","&gt;")
        if maxlen and len(snippet) > maxlen:
            snippet = snippet[:maxlen].rstrip()+"…"
        out.append({"title": title, "url": url, "snippet": snippet, "date": r.get("published_date") or "", "source": r.get("source") or ""})
        if len(out) >= max_items: break
    return out

def build_live_updates_html(data: Dict[str, Any], lang: str = "de", max_results: int = 5) -> Tuple[str, str]:
    # Fenster per ENV (Fallback 14)
    days_default = int(os.getenv("SEARCH_DAYS", "14") or "14")
    days_tools   = int(os.getenv("SEARCH_DAYS_TOOLS", str(days_default)) or str(days_default))
    days_funding = int(os.getenv("SEARCH_DAYS_FUNDING", str(days_default)) or str(days_default))

    branche = _extract_branche(data)
    size = str(data.get("unternehmensgroesse") or data.get("company_size") or "").strip().lower()
    region = str(data.get("bundesland") or data.get("state") or "").strip()
    product = str(data.get("hauptleistung") or data.get("hauptprodukt") or data.get("main_product") or "").strip()
    topic = str(data.get("search_topic") or "").strip()

    # Query-Körbe
    if lang.startswith("de"):
        q_funding = f"Förderprogramm KI {region} {branche} {size}".strip()
        q_tools   = f"KI Tool DSGVO {branche} {product}".strip()
    else:
        q_funding = f"AI funding {region} {branche} {size}".strip()
        q_tools   = f"GDPR-friendly AI tool {branche} {product}".strip()

    queries = [(q_funding, days_funding), (q_tools, days_tools)]
    if topic: queries.append((topic, days_default))

    # Suche + Fallback
    raw_items: List[Dict[str,Any]] = []
    for q, days in queries:
        if not q: continue
        res = _tavily_search(q, max_results=max_results, days=days) or _serpapi_search(q, max_results=max_results)
        raw_items.extend(res)

    # Sanitizer / Kuratierung
    includes = _parse_domains("SEARCH_INCLUDE_DOMAINS")
    excludes = _parse_domains("SEARCH_EXCLUDE_DOMAINS")
    max_items = int(os.getenv("LIVE_NEWS_MAX", str(max_results)))
    maxlen    = int(os.getenv("LIVE_ITEM_MAXLEN", "240"))
    min_score = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0.0"))
    do_sanit  = _env_bool("LIVE_NEWS_SANITIZE", True)

    items = _sanitize_live_items(raw_items, max_items, maxlen, min_score, includes, excludes) if do_sanit else raw_items[:max_items]

    if not items:
        return ("", "")

    lab = "Neu seit" if lang.startswith("de") else "New since"
    title = f"{lab} {_dt.now().strftime('%B %Y')}"
    html = ["<ul>"]
    for it in items:
        meta = " · ".join([x for x in (it.get("date",""), it.get("source","")) if x])
        html.append(f'<li><a href="{it["url"]}">{it["title"][:120]}</a>'
                    + (f' <span style="color:#5B6B7C">({meta})</span>' if meta else "")
                    + (f"<br><span style='color:#5B6B7C;font-size:12px'>{it['snippet']}</span>" if it.get("snippet") else "")
                    + "</li>")
    html.append("</ul>")
    return title, "\n".join(html)

# ---------------- Kontextaufbau ----------------
def build_context(data: Dict[str, Any], branche: str, lang: str = "de") -> Dict[str, Any]:
    lang = "de" if str(lang).lower().startswith("de") else "en"
    # Branchenkontext (falls vorhanden)
    ctx = {}
    ctx_path = BASE_DIR/"branchenkontext"/f"{branche}.{lang}.yaml"
    if not ctx_path.exists():
        ctx_path = BASE_DIR/"branchenkontext"/f"default.{lang}.yaml"
    if ctx_path.exists():
        try:
            import yaml
            ctx.update(yaml.safe_load(ctx_path.read_text(encoding="utf-8")) or {})
        except Exception:
            pass

    # Fragebogendaten überlagern
    ctx.update(data or {})
    ctx["lang"] = lang

    # Größe/Label
    def _guess_count(d: dict) -> Optional[int]:
        for key in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
            n = _as_int(d.get(key))
            if n is not None: return n
        sz = (d.get("unternehmensgroesse") or d.get("company_size") or "").strip().lower()
        if sz:
            if any(s in sz for s in ["solo","einzel","self"]): return 1
            m = re.match(r"(\d+)", sz)
            if m:
                try: return int(m.group(1))
                except Exception: pass
        return None

    emp_count = _guess_count(ctx)
    self_emp = is_self_employed(ctx)
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

    ctx["company_size_category"] = cat
    ctx["company_size_label"] = label
    ctx["unternehmensgroesse"] = label
    ctx["self_employed"] = "Yes" if self_emp else "No"
    ctx["selbststaendig"] = "Ja" if (self_emp and lang=="de") else ("Nein" if lang=="de" else ctx["self_employed"])
    ctx["branche"] = branche if lang=="de" else {
        "beratung":"consulting","bau":"construction","bildung":"education","finanzen":"finance",
        "gesundheit":"healthcare","handel":"trade","industrie":"industry","it":"IT","logistik":"logistics",
        "marketing":"marketing","medien":"media","verwaltung":"public administration"
    }.get(branche, branche)

    # bequeme Aliase
    ctx["hauptleistung"] = ctx.get("hauptleistung") or ctx.get("main_service") or ctx.get("hauptprodukt") or ""
    ctx["projektziel"] = ctx.get("projektziel") or ctx.get("ziel") or ""
    # Copyright/Fußzeile
    ctx.setdefault("copyright_year", _dt.now().year)
    ctx.setdefault("copyright_owner", "Wolf Hohl")
    return ctx

# ---------------- Prompt-Resolver ----------------
def _prompt_overrides(chapter: str, lang: str) -> Optional[str]:
    """ENV-Overrides + Deine business-prompt_* Dateien."""
    base = os.getenv("PROMPTS_DIR", "").strip()
    if base:
        p = Path(base)/lang/f"{chapter}.md"
        if p.exists(): return p.read_text(encoding="utf-8")

    # Coaching: spezifische ENV-Override-Dateien
    if chapter == "coaching":
        env_name = "COACH_PROMPT_DE" if lang=="de" else "COACH_PROMPT_EN"
        pth = os.getenv(env_name, "").strip()
        if pth and Path(pth).exists():
            return Path(pth).read_text(encoding="utf-8")

    # Deine gelieferten Dateinamen (ohne Umbenennen)
    if chapter == "coaching":
        alt = Path("prompts")/lang/("business-prompt_de.txt" if lang=="de" else "business-prompt_en.txt")
        if alt.exists(): return alt.read_text(encoding="utf-8")

    return None

def _read_prompt(chapter: str, lang: str) -> str:
    # 1) ENV/Overrides/Deine Dateien
    ov = _prompt_overrides(chapter, lang)
    if ov: return ov
    # 2) Standard-Pfade
    for base in [BASE_DIR/"prompts"/lang, BASE_DIR/"prompts_unzip"/lang]:
        for ext in (".md",".txt"):
            p = base/f"{chapter}{ext}"
            if p.exists(): return _load_text(p)
    # 3) Legacy: prompts/<chapter>_<lang>.md
    p3 = BASE_DIR/"prompts"/f"{chapter}_{lang}.md"
    if p3.exists(): return _load_text(p3)
    return f"[NO PROMPT FOUND for {chapter}/{lang}]"

def _read_optional_context(lang: str) -> str:
    ctx_parts = []
    for name in ["persona.md","praxisbeispiel.md","foerderprogramme.md","tools.md"]:
        for base in [BASE_DIR/"prompts"/lang, BASE_DIR/"prompts_unzip"/lang]:
            p = base/name
            if p.exists():
                ctx_parts.append(_load_text(p)); break
    return "\n\n".join(ctx_parts)

def _render_prompt_vars(tpl: str, ctx: Dict[str,Any]) -> str:
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
    if opt_ctx: rendered = rendered + "\n\n---\n" + opt_ctx

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

# ---------------- Report-Bau & Rendering ----------------
def generate_full_report(data: Dict[str,Any], lang: str="de") -> Dict[str,Any]:
    lang = ("de" if str(lang).lower().startswith("de") else "en")
    branche = _extract_branche(data)

    # Kapitel in Reihenfolge (inkl. Coaching)
    sections = [
        "executive_summary","quick_wins","risks","recommendations",
        "coaching",  # neu – nach Empfehlungen in den Templates eingefügt
        "roadmap","vision","gamechanger","compliance","praxisbeispiel"
    ]
    out: Dict[str,Any] = {}

    # Narrative Kapitel via LLM
    for ch in sections:
        try:
            out[ch+"_html"] = gpt_generate_section_html(data, branche, ch, lang)
        except Exception:
            out[ch+"_html"] = ""

    # Vision/Praxisbeispiel – einfache Fallbacks belassen
    if not out.get("vision_html"):
        if lang=="de":
            out["vision_html"] = ("<p><b>Vision:</b> Ein schlankes KI‑Serviceportal für KMU, das Fragebögen, Tools und Wissen bündelt "
                                  "und so den Einstieg erleichtert. Starten Sie mit einem kleinen Prototypen und bauen Sie entlang "
                                  "der echten Nutzung aus.</p><p>Mit wachsender Erfahrung entsteht ein lebendiges Wissenswerk, das "
                                  "neue Dienstleistungen inspiriert – ohne Zahlen, mit Fokus auf Lernen und Wirkung.</p>")
        else:
            out["vision_html"] = ("<p><b>Vision:</b> A lean AI service portal for SMEs that bundles questionnaires, tools and knowledge "
                                  "to ease the first steps. Start with a small prototype and expand along real usage.</p>"
                                  "<p>Over time it becomes a living knowledge base that inspires new services – no numbers, "
                                  "focused on learning and impact.</p>")

    # Narrative Tools + Funding (Funding als Tabelle)
    try:
        out["tools_html"] = build_tools_narrative(data, branche, lang, max_items=8)
    except Exception:
        out["tools_html"] = ""
    try:
        out["funding_html"] = build_funding_table_html(data, lang, max_items=8)
    except Exception:
        out["funding_html"] = ""

    # Live-Updates
    try:
        title, live_html = build_live_updates_html(data, lang, max_results=5)
        out["live_title"] = title
        out["live_html"] = live_html
    except Exception:
        out["live_title"] = ""
        out["live_html"] = ""

    # Meta für Template
    ort = data.get("ort") or data.get("city") or data.get("location") or ""
    groesse = data.get("unternehmensgroesse") or data.get("company_size") or ""
    out["meta"] = {
        "title": ("KI‑Statusbericht" if lang=="de" else "AI Readiness Report"),
        "subtitle": ("Narrativer KI‑Report – DSGVO & EU‑AI‑Act‑ready" if lang=="de" else "Narrative AI report – GDPR & EU‑AI‑Act‑ready"),
        "date": _dt.now().strftime("%d.%m.%Y") if lang=="de" else _dt.now().strftime("%Y-%m-%d"),
        "branche": branche, "size": groesse, "location": ort
    }

    # **Globale Sanitisierung NUR für narrative Kapitel**
    narrative_keys = {
        "executive_summary_html","quick_wins_html","risks_html","recommendations_html",
        "coaching_html","roadmap_html","vision_html","gamechanger_html","compliance_html","praxisbeispiel_html"
    }
    for k in list(out.keys()):
        if k.endswith("_html") and k in narrative_keys:
            out[k] = _strip_lists_and_numbers(out[k])

    # Optionales Postprocessing
    if postprocess_report_dict:
        try: out = postprocess_report_dict(out, lang=lang)  # type: ignore
        except Exception: pass

    return out

def analyze_briefing(body: Dict[str,Any], lang: str="de") -> str:
    """Entry-Point für main.py – liefert finales HTML für das PDF-Service."""
    if not isinstance(body, dict):
        try: body = json.loads(str(body))
        except Exception: body = {}
    lang = ("de" if str(lang).lower().startswith("de") else "en")

    report = generate_full_report(body or {}, lang=lang)

    # Jinja2-Rendering
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html","xml"])
    )
    tpl_name = "pdf_template.html" if lang=="de" else "pdf_template_en.html"
    tpl = env.get_template(tpl_name)

    ctx = {**report, "now": _dt.now, "lang": lang}
    html = tpl.render(**ctx)

    # Allerletzte Sicherung
    html = _sanitize_text(_strip_code_fences(html))
    return html
