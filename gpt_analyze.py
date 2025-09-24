# gpt_analyze.py — Gold-Standard (Wolf Edition)
# Version: 2025-09-24 (FULL)
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

# ---- optionale Module (Gamechanger) -----------------------------------------
GAME_FEATURES = None
build_gamechanger_blocks = None
try:
    from gamechanger_features import GAMECHANGER_FEATURES as GAME_FEATURES  # noqa
except Exception:
    GAME_FEATURES = None
try:
    from gamechanger_blocks import build_gamechanger_blocks as _gcb  # noqa
    build_gamechanger_blocks = _gcb
except Exception:
    build_gamechanger_blocks = None

# ---- Appendix-Quelle (aus „bitte-einbauen-am-Ende.pdf“) ---------------------
# Inhalt wird unten als HTML generiert; Quelle siehe Projektdokument.
# (Siehe Funktionsrumpf build_appendix_end_html.)

# ---- optionales Postprocessing ----------------------------------------------
try:
    from postprocess_report import postprocess_report_dict  # type: ignore[attr-defined]
except Exception:
    postprocess_report_dict = None

# ---- ZIP-Autounpack ---------------------------------------------------------
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

# ---------------- ENV/Utils --------------------------------------------------
def _env_bool(name: str, default: bool=False) -> bool:
    v = str(os.getenv(name, str(int(default)))).strip().lower()
    return v in {"1","true","yes","on"}

def _parse_domains(name: str) -> List[str]:
    raw = os.getenv(name, "") or ""
    return [d.strip().lower() for d in raw.split(",") if d.strip()]

def _as_int(x) -> Optional[int]:
    try: return int(str(x).strip())
    except Exception: return None

# ---------------- Datei-/Kontext-Loader -------------------------------------
def _load_text(path: Path) -> str:
    try: return path.read_text(encoding="utf-8")
    except Exception: return ""

def _read_csv_rows(path: Path) -> List[Dict[str,str]]:
    try:
        with path.open(newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k,v in r.items()} for r in rd]
    except Exception:
        return []

def _find_data_file(candidates: List[str]) -> Optional[Path]:
    for n in candidates:
        p = BASE_DIR/"data"/n
        if p.exists(): return p
    for n in candidates:
        p = BASE_DIR/n
        if p.exists(): return p
    return None

# ---------------- Branchen-/Größen-Erkennung --------------------------------
def _extract_branche(d: Dict[str, Any]) -> str:
    raw = (str(d.get("branche") or d.get("industry") or d.get("sector") or "")).strip().lower()
    MAP = {
        "beratung":"beratung","consulting":"beratung","dienstleistung":"beratung","services":"beratung",
        "it":"it","software":"it","saas":"it","information technology":"it",
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
    if raw in MAP: return MAP[raw]
    for k,v in MAP.items():
        if k in raw: return v
    return "default"

def is_self_employed(data: dict) -> bool:
    keys_text = ["beschaeftigungsform","beschäftigungsform","arbeitsform","rolle","role","occupation","unternehmensform","company_type"]
    txt = " ".join(str(data.get(k, "") or "") for k in keys_text).lower()
    if any(s in txt for s in ["selbst","freelanc","solo","self-employ"]): return True
    for k in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
        n = _as_int(data.get(k))
        if n is not None and n <= 1: return True
    return False

# ---------------- Sanitizer (Text) -------------------------------------------
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
    repl = {"GPT-Analyse":"LLM-gestützte Analyse","GPT‑Analyse":"LLM-gestützte Analyse"}
    for a,b in repl.items(): text = text.replace(a,b)
    return text

# nur Prozent/Währung entfernen (keine neutralen Zahlen!)
_NUM_PERCENT_CURR = re.compile(r"(?i)(\b\d+(?:[.,]\d+)?\s*%)|(\b(?:€|eur|usd)\s*\d+(?:[.,]\d+)?)|(\b\d+(?:[.,]\d+)?\s*(?:€|eur|usd)\b)")
_BULLET_PAT = re.compile(r"^\s*[-–—•\*]\s*", re.MULTILINE)

def _strip_lists_and_numbers(raw: str) -> str:
    """Für narrative Abschnitte. Entfernt Listenmarker & %/Währungszahlen, NICHT neutrale Zahlen (z. B. '7 Tage')."""
    if not raw: return raw
    t = _sanitize_text(_strip_code_fences(str(raw)))
    t = _BULLET_PAT.sub("", t)
    t = t.replace("</li>", " ").replace("<li>", "").replace("<ul>", "").replace("</ul>", "")
    t = t.replace("<ol>", "").replace("</ol>", "")
    t = _NUM_PERCENT_CURR.sub("", t)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()

def _ensure_html(text: str, lang: str="de") -> str:
    t = (text or "").strip()
    if "<" in t and ">" in t: return t
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    html = []; in_ul=False
    for ln in lines:
        if re.match(r"^[-•*]\s+", ln):
            if not in_ul: html.append("<ul>"); in_ul=True
            html.append("<li>"+re.sub(r"^[-•*]\s+","",ln)+"</li>")
            continue
        if in_ul: html.append("</ul>"); in_ul=False
        html.append("<p>"+ln+"</p>")
    if in_ul: html.append("</ul>")
    return "\n".join(html)

# ---------------- CSV/Dateien ------------------------------------------------
def _merge_by_name(a: List[Dict[str,Any]], b: List[Dict[str,Any]], key_a: str, key_b: str, fields: List[str]) -> None:
    """enrich a (in-place) with fields from b by name match (case-insensitive)."""
    idx = {}
    for r in a:
        name = (r.get(key_a) or "").strip().lower()
        if name: idx[name] = r
    for r in b:
        name = (r.get(key_b) or "").strip().lower()
        if not name or name not in idx: continue
        tgt = idx[name]
        for f in fields:
            if r.get(f) and not tgt.get(f):
                tgt[f] = r.get(f)

# ---------------- Funding (Daten + Deadlines + Renderer) ---------------------
def _norm_size(x: str) -> str:
    x = (x or "").lower()
    if x in {"solo","einzel","einzelunternehmer","freelancer","soloselbstständig","soloselbststaendig"}: return "solo"
    if x in {"team","small"}: return "team"
    if x in {"kmu","sme","mittelstand"}: return "kmu"
    return ""

_DATE_PATTERNS = [
    r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b",                           # 31.12.2025
    r"\b(\d{1,2}\s+(Jan(?:uar)?|Feb(?:ruar)?|März|Maerz|Apr(?:il)?|Mai|Jun(?:i)?|Jul(?:i)?|Aug(?:ust)?|Sep(?:t|tember)?|Okt(?:ober)?|Nov(?:ember)?|Dez(?:ember)?)\s+\d{4})\b",
    r"\b(\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b"
]

def _try_parse_deadline(text: str) -> Optional[str]:
    if not text: return None
    for pat in _DATE_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def _tavily_search(query: str, max_results: int = 5, days: Optional[int] = None) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY","").strip()
    if not key: return []
    payload = {"api_key": key, "query": query, "max_results": max_results,
               "include_answer": False, "search_depth": os.getenv("SEARCH_DEPTH","basic")}
    if days: payload["days"] = int(days)
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
            res = []
            for item in data.get("results", [])[:max_results]:
                res.append({"title": item.get("title"), "url": item.get("url"),
                            "content": item.get("content"), "published_date": item.get("published_date"),
                            "score": item.get("score"), "source": item.get("source")})
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
                res.append({"title": item.get("title"), "url": item.get("link"),
                            "content": item.get("snippet"), "source": item.get("source")})
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
        out.append({"title": title, "url": url, "snippet": snippet,
                    "date": r.get("published_date") or "", "source": r.get("source") or ""})
        if len(out) >= max_items: break
    return out

def _enrich_deadlines_with_tavily(rows: List[Dict[str,Any]], lang: str="de") -> None:
    """Versucht fehlende Fristen via Tavily-Snippets zu erkennen (Heuristik)."""
    if not _env_bool("ALLOW_TAVILY", True): return
    includes = _parse_domains("SEARCH_INCLUDE_DOMAINS"); excludes = _parse_domains("SEARCH_EXCLUDE_DOMAINS")
    for r in rows:
        if r.get("deadline"): continue
        name = (r.get("name") or "").strip()
        if not name: continue
        q = (f"{name} Frist Antrag" if lang.startswith("de") else f"{name} application deadline").strip()
        items = _tavily_search(q, max_results=3, days=90) or _serpapi_search(q, max_results=3)
        items = _sanitize_live_items(items, 3, 280, 0.0, includes, excludes)
        for it in items:
            date = _try_parse_deadline(it.get("snippet") or it.get("title") or "")
            if date:
                r["deadline"] = date
                break

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

    # Deadlines aus separater CSV übernehmen (falls vorhanden)
    dl_file = _find_data_file(["funding_deadlines.csv","deadlines.csv"])
    if dl_file:
        dl_rows = _read_csv_rows(dl_file)
        for r in dl_rows:
            # akzeptiere Spaltennamen 'deadline' oder 'frist'
            if "frist" in r and not r.get("deadline"):
                r["deadline"] = r.get("frist")
        _merge_by_name(out, dl_rows, "name", "name", ["deadline"])

    out = sorted(out, key=lambda x: x.get("_score",0))

    # Fehlt Deadline → über Tavily versuchen
    if _env_bool("ALLOW_TAVILY", True):
        _enrich_deadlines_with_tavily(out, lang)

    # Dedupe/Limit
    seen = set(); uniq = []
    for o in out:
        key = (o["name"].lower(), (o.get("link") or "").lower())
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
        prog = f'<a href="{link}">{name}</a>' if link and name else (name or (link or ""))
        region = (r.get('region') or '').strip().title()
        deadline = (r.get("deadline") or "–").strip()
        out.append(
            "<tr>"
            f"<td>{prog}</td>"
            f"<td>{region or '–'}</td>"
            f"<td>{(r.get('target') or '–')}</td>"
            f"<td>{(r.get('grant') or '–')}</td>"
            f"<td>{deadline or '–'}</td>"
            "</tr>"
        )
    out.append("</tbody></table>")
    if stand:
        out.append(f'<p style="color:#5B6B7C;font-size:12px">Stand: {stand}</p>')
    return "\n".join(out)

# ---------------- Tools (CSV + Fallback + Badges) ----------------------------
def _tools_fallback(branche: str, size: str, lang: str="de") -> List[Dict[str,str]]:
    lib = [
        {"name":"Make (ex Integromat)","category":"Automation","suitable_for":"Formulare → CRM/Angebot","hosting":"EU‑Option","price":"ab €","link":"https://www.make.com"},
        {"name":"Nextcloud","category":"DMS/Collab","suitable_for":"Dateien, Freigaben, Wissensbasis","hosting":"EU/self‑host","price":"frei/€","link":"https://nextcloud.com"},
        {"name":"Matomo","category":"Analytics","suitable_for":"Web‑Analytics ohne 3rd‑Party","hosting":"EU/self‑host","price":"frei/€","link":"https://matomo.org"},
        {"name":"Odoo (CRM Light)","category":"CRM","suitable_for":"Leads/Angebote/Follow‑ups","hosting":"EU","price":"ab €","link":"https://www.odoo.com"},
        {"name":"KNIME","category":"Analytics","suitable_for":"Datenflows/Reporting","hosting":"Desktop/Server (EU)","price":"frei/€","link":"https://www.knime.com"},
        {"name":"Wire","category":"Kommunikation","suitable_for":"Sichere Team‑Kommunikation","hosting":"EU","price":"ab €","link":"https://wire.com"}
    ]
    return lib

def _tool_badges(row: Dict[str,str], lang: str="de") -> List[str]:
    badges: List[str] = []
    hosting = (row.get("hosting") or "").lower()
    name = (row.get("name") or "").lower()
    cat  = (row.get("category") or "").lower()
    price= (row.get("price") or "").lower()

    # Hosting/EU
    if "eu" in hosting or "europe" in hosting or "self" in hosting or "on-prem" in hosting or "onprem" in hosting:
        badges.append("EU‑Hosting" if lang.startswith("de") else "EU hosting")
    # Open Source
    if "open" in hosting or "oss" in hosting or "git" in hosting or name in {"nextcloud","matomo","knime"}:
        badges.append("Open Source" if lang.startswith("de") else "Open source")
    # No/Low‑Code
    if "no-code" in cat or "no code" in cat or "automation" in cat:
        badges.append("No‑/Low‑Code" if lang.startswith("de") else "No/low‑code")
    elif "low" in cat:
        badges.append("Low‑Code" if lang.startswith("de") else "Low‑code")
    # Preis-Hinweis
    if "frei" in price or "free" in price:
        badges.append("Kostenlos" if lang.startswith("de") else "Free")
    return badges[:3]  # max 3

def build_tools_details_struct(data: Dict[str,Any], branche: str, lang: str="de", max_items: int=10) -> Tuple[List[Dict[str,Any]], str]:
    path = _find_data_file(["tools.csv","ki_tools.csv"])
    rows = _read_csv_rows(path) if path else []
    out: List[Dict[str,Any]] = []
    size = (str(data.get("unternehmensgroesse") or data.get("company_size") or "")).lower()

    if rows:
        for r in rows:
            name = r.get("name") or r.get("Tool") or r.get("Tool-Name")
            if not name: continue
            tags = (r.get("Branche-Slugs") or r.get("Tags") or r.get("Branche") or r.get("industry") or "").lower()
            row_size = (r.get("Unternehmensgröße") or r.get("Unternehmensgroesse") or r.get("company_size") or "").lower()
            if branche and tags and branche not in tags:
                continue
            if size and row_size and row_size not in {"alle", size, "kmu"}:
                continue
            out.append({
                "name": name,
                "category": r.get("kategorie") or r.get("category") or "",
                "suitable_for": r.get("eignung") or r.get("use_case") or r.get("einsatz") or "",
                "hosting": r.get("hosting") or r.get("datenschutz") or r.get("data") or "",
                "price": r.get("preis") or r.get("price") or r.get("kosten") or "",
                "link": r.get("link") or r.get("url") or "",
            })
    else:
        out = _tools_fallback(branche, size, lang)

    # Badges berechnen
    for r in out:
        r["badges"] = _tool_badges(r, lang)
    return out[:max_items], ""

def build_tools_html(data: Dict[str,Any], branche: str, lang: str="de", max_items: int=8) -> str:
    rows, _ = build_tools_details_struct(data, branche, lang, max_items)
    if not rows: return ""
    ps = []
    intro = ("Auswahl bewährter, EU‑tauglicher Werkzeuge für einen pragmatischen Start:" 
             if lang.startswith("de") else
             "A curated selection of EU‑friendly tools to get started quickly:")
    ps.append(f"<p>{intro}</p>")
    for r in rows:
        badges = "".join(f'<span class="badge">{b}</span>' for b in (r.get("badges") or []))
        if lang.startswith("de"):
            p  = f"<p><b>{r['name']}</b> ({r.get('category','')}) – geeignet für {r.get('suitable_for','den Alltag')}. "
            p += f"Hosting/Datenschutz: {r.get('hosting','n/a')}; Preis: {r.get('price','n/a')}. {badges} "
            if r.get('link'): p += f'<a href="{r["link"]}">Website</a>'
            p += "</p>"
        else:
            p  = f"<p><b>{r['name']}</b> ({r.get('category','')}) – suitable for {r.get('suitable_for','daily work')}. "
            p += f"Data/hosting: {r.get('hosting','n/a')}; price: {r.get('price','n/a')}. {badges} "
            if r.get('link'): p += f'<a href="{r["link"]}">Website</a>'
            p += "</p>"
        ps.append(p)
    return "\n".join(ps)

# ---------------- Live-Updates (gruppiert) -----------------------------------
def build_live_updates_grouped_html(data: Dict[str, Any], lang: str = "de", max_results: int = 5) -> Tuple[str, str]:
    if not _env_bool("ALLOW_TAVILY", True): return ("","")
    days_default = int(os.getenv("SEARCH_DAYS", "14") or "14")
    days_tools   = int(os.getenv("SEARCH_DAYS_TOOLS", str(days_default)) or str(days_default))
    days_funding = int(os.getenv("SEARCH_DAYS_FUNDING", str(days_default)) or str(days_default))

    branche = _extract_branche(data)
    size = str(data.get("unternehmensgroesse") or data.get("company_size") or "").strip().lower()
    region = str(data.get("bundesland") or data.get("state") or "").strip()
    product = str(data.get("hauptleistung") or data.get("hauptprodukt") or data.get("main_product") or "").strip()

    if lang.startswith("de"):
        q_reg     = "EU AI Act DSGVO ePrivacy DSA Update"
        q_tools   = f"KI Tool DSGVO {branche} {product}".strip()
        q_fund    = f"Förderprogramm KI {region} {branche} {size}".strip()
        labels    = ("Regwatch","Tools‑News","Förderung")
    else:
        q_reg     = "EU AI Act GDPR ePrivacy DSA update"
        q_tools   = f"GDPR-friendly AI tool {branche} {product}".strip()
        q_fund    = f"AI funding {region} {branche} {size}".strip()
        labels    = ("Regwatch","Tools news","Funding")

    buckets = [(labels[0], q_reg, days_default),
               (labels[1], q_tools, days_tools),
               (labels[2], q_fund, days_funding)]

    includes = _parse_domains("SEARCH_INCLUDE_DOMAINS"); excludes = _parse_domains("SEARCH_EXCLUDE_DOMAINS")
    maxlen    = int(os.getenv("LIVE_ITEM_MAXLEN", "240")); min_score = float(os.getenv("LIVE_NEWS_MIN_SCORE", "0.0"))
    do_sanit  = _env_bool("LIVE_NEWS_SANITIZE", True)

    groups = []
    for label, q, days in buckets:
        items = _tavily_search(q, max_results=max_results, days=days) or _serpapi_search(q, max_results=max_results)
        items = _sanitize_live_items(items, max_results, maxlen, min_score, includes, excludes) if do_sanit else items[:max_results]
        if not items: continue
        html = ["<ul>"]
        for it in items:
            meta = " · ".join([x for x in (it.get("date",""), it.get("source","")) if x])
            html.append(f'<li><a href="{it["url"]}">{it["title"][:120]}</a>'
                        + (f' <span style="color:#5B6B7C">({meta})</span>' if meta else "")
                        + (f"<br><span style='color:#5B6B7C;font-size:12px'>{it['snippet']}</span>" if it.get("snippet") else "")
                        + "</li>")
        html.append("</ul>")
        groups.append((label, "\n".join(html)))
    if not groups: return ("","")
    title = ("Neu & relevant" if lang.startswith("de") else "New & relevant") + f" – {_dt.now().strftime('%B %Y')}"
    out = []
    for label, html in groups:
        out.append(f"<h3>{label}</h3>\n{html}")
    return title, "\n".join(out)

# ---------------- Kontext & Prompts ------------------------------------------
def build_context(data: Dict[str, Any], branche: str, lang: str = "de") -> Dict[str, Any]:
    lang = "de" if str(lang).lower().startswith("de") else "en"
    ctx = {}
    ctx.update(data or {})
    ctx["lang"] = lang

    def _guess_size_label(d: dict) -> Tuple[str,str]:
        for key in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
            n = _as_int(d.get(key))
            if n is not None:
                if n <= 1: return ("solo","Solo-Unternehmer:in" if lang=="de" else "Solo entrepreneur")
                if n <= 10: return ("team","Team (2–10)" if lang=="de" else "Small team (2–10)")
                return ("kmu","KMU (11+)" if lang=="de" else "SME (11+)")
        sz = (d.get("unternehmensgroesse") or d.get("company_size") or "").strip().lower()
        if "solo" in sz or "self" in sz: return ("solo","Solo-Unternehmer:in" if lang=="de" else "Solo entrepreneur")
        if "team" in sz or "2" in sz or "10" in sz: return ("team","Team (2–10)" if lang=="de" else "Small team (2–10)")
        if sz: return ("kmu","KMU (11+)" if lang=="de" else "SME (11+)")
        return ("", "")
    cat, label = _guess_size_label(ctx)
    ctx["company_size_category"] = cat
    ctx["company_size_label"] = label or (ctx.get("unternehmensgroesse") or ctx.get("company_size") or "")

    ctx["bundesland"] = str(ctx.get("bundesland") or ctx.get("state") or "").lower()
    ctx.setdefault("branche", branche if lang=="de" else {
        "beratung":"consulting","bau":"construction","bildung":"education","finanzen":"finance","gesundheit":"healthcare",
        "handel":"trade","industrie":"industry","it":"IT","logistik":"logistics","marketing":"marketing","medien":"media",
        "verwaltung":"public administration","default":"business services"
    }.get(branche, "business services"))
    ctx.setdefault("hauptleistung", ctx.get("hauptleistung") or ctx.get("main_service") or ctx.get("hauptprodukt") or "your core service")
    ctx.setdefault("copyright_year", _dt.now().year)
    ctx.setdefault("copyright_owner", "Wolf Hohl")
    return ctx

def _read_prompt(chapter: str, lang: str) -> str:
    base = os.getenv("PROMPTS_DIR", "").strip()
    if chapter == "coaching":
        p_env = os.getenv("COACH_PROMPT_DE" if lang=="de" else "COACH_PROMPT_EN","").strip()
        if p_env and Path(p_env).exists(): return _load_text(Path(p_env))
        alt = Path("prompts")/("de" if lang=="de" else "en")/("business-prompt_de.txt" if lang=="de" else "business-prompt_en.txt")
        if alt.exists(): return _load_text(alt)
    if base:
        p = Path(base)/("de" if lang=="de" else "en")/f"{chapter}.md"
        if p.exists(): return _load_text(p)
    p3 = BASE_DIR/"prompts"/("de" if lang=="de" else "en")/f"{chapter}.md"
    if p3.exists(): return _load_text(p3)
    return f"[NO PROMPT FOUND for {chapter}/{lang}]"

def _render_prompt_vars(tpl: str, ctx: Dict[str,Any]) -> str:
    def _simple(m):
        key = m.group(1); val = ctx.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _simple, tpl)

def build_masterprompt(chapter: str, context: Dict[str,Any], lang: str) -> str:
    base = _read_prompt(chapter, lang)
    rendered = _render_prompt_vars(base, context)
    guard = ("Wenn ein Feld leer ist (z. B. Branche, Hauptleistung, Bundesland), formuliere neutral ohne Platzhalter."
             if lang=="de" else
             "If a field is missing (e.g., industry, core service, state), use neutral phrasing; never output blanks.")
    rules = ("Gib die Antwort als gültiges HTML (ohne <html>-Wrapper). Nutze <h3> und <p>. "
             "Keine Tabellen/Listen. Schreibe 2–3 Absätze, warm, konkret, umsetzbar. "
             "Keine Prozent- oder Geldzahlen."
             if lang=="de" else
             "Return valid HTML only (no <html> wrapper). Use <h3> and <p>. "
             "No tables/lists. Write 2–3 paragraphs, warm, concrete, actionable. "
             "No percentages or currency figures.")
    return rendered + "\n\n---\n" + guard + "\n" + rules

def _chat_complete(messages, model_name: Optional[str], temperature: Optional[float]=None) -> str:
    args = {"model": model_name or os.getenv("GPT_MODEL_NAME","gpt-4o"), "messages": messages}
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE","0.2"))
    args["temperature"] = temperature
    resp = client.chat.completions.create(**args)
    return resp.choices[0].message.content.strip()

def gpt_generate_section_html(data: Dict[str,Any], branche: str, chapter: str, lang: str="de") -> str:
    ctx = build_context(data, branche, lang)
    prompt = build_masterprompt(chapter, ctx, lang)
    model = os.getenv("EXEC_SUMMARY_MODEL" if chapter=="executive_summary" else "GPT_MODEL_NAME","gpt-4o")
    html = _chat_complete(
        messages=[{"role":"system","content": (
            "Sie sind TÜV-zertifizierte:r KI-Manager:in, KI-Strategieberater:in sowie Datenschutz- und Fördermittel-Expert:in. "
            "Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
        ) if lang=="de" else (
            "You are a TÜV-certified AI manager and strategy consultant. "
            "Deliver precise, actionable, up-to-date, sector-relevant content as HTML."
        )},{"role":"user","content": prompt}],
        model_name=model, temperature=None
    )
    return _ensure_html(_strip_lists_and_numbers(html), lang)

# ---------------- Appendix (aus Projekt-Dokument) ----------------------------
def build_appendix_end_html(lang: str="de") -> str:
    if lang.startswith("de"):
        return """
<section>
  <h3>Leistung &amp; Nachweis</h3>
  <p>Als TÜV‑zertifizierter KI‑Manager begleite ich Unternehmen bei der sicheren Einführung, Nutzung und Audit‑Vorbereitung von KI – mit klarer Strategie, dokumentierter Förderfähigkeit und DSGVO‑Konformität.</p>
  <p><b>Schwerpunkte:</b> KI‑Strategie &amp; Audit · EU AI Act &amp; DSGVO · Dokumentation &amp; Governance · minimiertes Haftungsrisiko.</p>
  <p>Kontakt: <a href="mailto:kontakt@ki-sicherheit.jetzt">kontakt@ki-sicherheit.jetzt</a> · <a href="https://ki-sicherheit.jetzt">ki‑sicherheit.jetzt</a></p>
  <h3>Glossar</h3>
  <p><b>KI</b>: Technologien, die aus Daten lernen. <b>DSGVO</b>: EU‑Datenschutzrecht. <b>DSFA</b>: Datenschutz‑Folgenabschätzung. <b>EU AI Act</b>: EU‑Verordnung zu Risikoklassen und Pflichten. <b>Quick Win</b>: schneller Nutzen. <b>MVP</b>: minimal funktionsfähige erste Version.</p>
  <h3>Ihre Meinung zählt</h3>
  <p>2–3 Minuten Feedback helfen, die Empfehlungen weiter zu schärfen.</p>
  <p class="muted">© 2025 KI‑Sicherheit.jetzt – DSGVO &amp; EU‑AI‑Act‑ready – Wolf Hohl · Alle Angaben ohne Gewähr; keine Rechtsberatung.</p>
</section>
""".strip()
    else:
        return """
<section>
  <h3>Scope &amp; Credentials</h3>
  <p>As a TÜV‑certified AI manager I help SMEs adopt, operate and audit AI safely – with clear strategy, documented fundability and GDPR compliance.</p>
  <p><b>Focus:</b> AI strategy &amp; audits · EU AI Act &amp; GDPR · documentation &amp; governance · reduced liability risk.</p>
  <p>Contact: <a href="mailto:kontakt@ki-sicherheit.jetzt">kontakt@ki-sicherheit.jetzt</a> · <a href="https://ki-sicherheit.jetzt">ki‑sicherheit.jetzt</a></p>
  <h3>Glossary</h3>
  <p><b>AI</b>: data‑driven systems. <b>GDPR</b>: EU data protection law. <b>DPIA</b>: data protection impact assessment. <b>EU AI Act</b>: risk classes &amp; obligations. <b>Quick win</b>: fast result. <b>MVP</b>: minimal viable product.</p>
  <h3>We value your feedback</h3>
  <p>2–3 minutes of feedback help us improve recommendations.</p>
  <p class="muted">© 2025 KI‑Sicherheit.jetzt – GDPR &amp; EU‑AI‑Act‑ready – Wolf Hohl · No legal advice.</p>
</section>
""".strip()

# ---------------- Report-Bau -------------------------------------------------
def _append_quickwin_chips(html: str, lang: str, size_cat: str) -> str:
    # Text‑Chips (ohne Farben), wie besprochen
    if not html: return html
    chips = ("Aufwand: niedrig · Hebel: hoch · Risiko: niedrig" if size_cat in {"solo","team"} else
             "Aufwand: mittel · Hebel: hoch · Risiko: mittel")
    note = f"<p class='muted'>{'Priorisierung' if lang.startswith('de') else 'Prioritisation'}: {chips}</p>"
    return note + html

def _append_coach_offer(html: str, lang: str) -> str:
    if not html: html = ""
    add = ("<p><b>Was wir für Sie vorbereiten können:</b> Trusted‑KI‑Check, DSFA‑Vorlage, Rollen &amp; Prozesse, "
           "Förder‑Skizze (1–2 Seiten), MVP‑Plan. Alles als prüffähige Dokumente.</p>"
           if lang.startswith("de") else
           "<p><b>What we can pre‑assemble for you:</b> trusted‑AI checklist, DPIA template, roles &amp; processes, "
           "funding sketch (1–2 pages), MVP plan. All as auditable documents.</p>")
    return html + add

def _build_gamechanger_html(data: Dict[str,Any]) -> str:
    if GAME_FEATURES and build_gamechanger_blocks:
        try:
            return build_gamechanger_blocks(data, GAME_FEATURES)
        except Exception:
            return ""
    return ""

def generate_full_report(data: Dict[str,Any], lang: str="de") -> Dict[str,Any]:
    lang = ("de" if str(lang).lower().startswith("de") else "en")
    branche = _extract_branche(data)

    sections = ["executive_summary","quick_wins","risks","recommendations","coaching","roadmap","vision","gamechanger","compliance"]
    out: Dict[str,Any] = {}

    for ch in sections:
        try:
            out[ch+"_html"] = gpt_generate_section_html(data, branche, ch, lang)
        except Exception:
            out[ch+"_html"] = ""

    # Executive Summary – sicher vorhanden
    if not out.get("executive_summary_html"):
        out["executive_summary_html"] = _ensure_html(
            "Kurzüberblick: Status, 3 schnelle Hebel, größte Risiken, nächste Schritte (30–60 Tage)." if lang=="de" else
            "Quick brief: status, 3 quick wins, top risks, next 30–60‑day steps.", lang
        )

    # Quick-Win‑Chips hinzufügen
    out["quick_wins_html"] = _append_quickwin_chips(out.get("quick_wins_html",""), lang,
                                                    data.get("company_size_category") or data.get("unternehmensgroesse") or "")

    # Coaching Angebot ergänzen
    out["coaching_html"] = _append_coach_offer(out.get("coaching_html",""), lang)

    # Tools & Funding
    try: out["tools_html"] = build_tools_html(data, branche, lang, max_items=8)
    except Exception: out["tools_html"] = ""
    try: out["funding_html"] = build_funding_table_html(data, lang, max_items=8)
    except Exception: out["funding_html"] = ""

    # Live-Updates (gruppiert)
    try:
        title, live_html = build_live_updates_grouped_html(data, lang, max_results=5)
        out["live_title"] = title; out["live_html"] = live_html
    except Exception:
        out["live_title"] = ""; out["live_html"] = ""

    # Gamechanger-Blöcke (aus Dateien, falls vorhanden)
    gc_blocks = _build_gamechanger_html(data)
    if gc_blocks:
        # hängt an bestehende Vision/Gamechanger an
        out["gamechanger_html"] = (out.get("gamechanger_html","") or "") + gc_blocks

    # Appendix
    out["appendix_end_html"] = build_appendix_end_html(lang)

    # Meta
    out["meta"] = {
        "title": ("KI‑Statusbericht" if lang=="de" else "AI Readiness Report"),
        "date": _dt.now().strftime("%d.%m.%Y") if lang=="de" else _dt.now().strftime("%Y-%m-%d"),
    }

    # Globale Sanitisierung NUR für narrative Kapitel (Roadmap NICHT!)
    narrative_keys = {
        "executive_summary_html","quick_wins_html","risks_html","recommendations_html",
        "coaching_html","vision_html","gamechanger_html","compliance_html"
    }
    for k in list(out.keys()):
        if k.endswith("_html") and k in narrative_keys:
            out[k] = _strip_lists_and_numbers(out[k])

    if postprocess_report_dict:
        try: out = postprocess_report_dict(out, lang=lang)  # type: ignore
        except Exception: pass
    return out

# ---------------- Public API -------------------------------------------------
def analyze_briefing(body: Dict[str,Any], lang: str="de") -> str:
    if not isinstance(body, dict):
        try: body = json.loads(str(body))
        except Exception: body = {}
    lang = ("de" if str(lang).lower().startswith("de") else "en")
    report = generate_full_report(body or {}, lang=lang)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html","xml"]))
    tpl_name = "pdf_template.html" if lang=="de" else "pdf_template_en.html"
    tpl = env.get_template(tpl_name)

    ctx = {**report, "now": _dt.now, "lang": lang, **(body or {})}
    html = tpl.render(**ctx)
    html = _sanitize_text(_strip_code_fences(html))
    return html
