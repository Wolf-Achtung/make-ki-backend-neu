
# gpt_analyze.py — Gold-Standard, clean build (2025-09-19)
# -*- coding: utf-8 -*-
import os
import re
import csv
import json
import base64
import zipfile
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

try:
    # OpenAI SDK v1
    from openai import OpenAI
    _OPENAI_CLIENT = OpenAI()
except Exception:
    _OPENAI_CLIENT = None  # allow running in environments without OpenAI SDK

# --------------------------------------------------------------------------------------
# Paths & template environment
# --------------------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "htm"]),
        enable_async=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )

def _pick_template(lang: str) -> str:
    if lang.lower().startswith("de") and (TEMPLATES_DIR / "pdf_template.html").exists():
        return "pdf_template.html"
    if (TEMPLATES_DIR / "pdf_template_en.html").exists():
        return "pdf_template_en.html"
    # fallback to German template name for both
    return "pdf_template.html"

# --------------------------------------------------------------------------------------
# Unzip support (prompts, data, branchenkontext)
# --------------------------------------------------------------------------------------

def ensure_unzipped(zip_name: str, dest_dir: str) -> None:
    try:
        z = BASE_DIR / zip_name
        d = BASE_DIR / dest_dir
        if z.exists() and not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(z), "r") as zf:
                zf.extractall(str(d))
    except Exception:
        # non-fatal
        pass

# Prefer extracting into the canonical directory names the code expects
ensure_unzipped("prompts.zip", "prompts")
ensure_unzipped("branchenkontext.zip", "branchenkontext")
ensure_unzipped("data.zip", "data")
ensure_unzipped("aus-Data.zip", "data")

# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").strip().lower()
    return "de" if l.startswith("de") else "en"

def _resolve_model(wanted: Optional[str]) -> str:
    """Map unknown/placeholder models to safe fallbacks to prevent 400s."""
    w = (wanted or "").strip().lower()
    if not w or w.startswith("gpt-5"):
        return os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
    known = {
        "gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini",
        "gpt-4o-audio-preview", "gpt-3.5-turbo"
    }
    return w if w in known else os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")

def fix_encoding(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("�", "-")
            .replace("–", "-")
            .replace("“", '"')
            .replace("”", '"')
            .replace("’", "'")
    )

def strip_code_fences(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")

def _strip_lists_and_numbers(html: str) -> str:
    """Remove list tags and obvious numeric KPIs (esp. %), keep links intact."""
    if not html:
        return ""
    t = html
    # Replace list tags with plain text spacing
    t = re.sub(r"</?(ul|ol|li)[^>]*>", " ", t, flags=re.I)
    # Remove common bullet prefixes at line starts
    t = re.sub(r"(?m)^\s*(?:[-*•]\s+|\d{1,3}[\.\)]\s+)", "", t)
    # Nuke percentages but preserve href/src attributes
    t = re.sub(r"(?<!href=\")(?<!src=\")\b\d{1,3}(?:[.,]\d+)?\s*%", " deutlich ", t)
    # Collapse multiple spaces
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t

def ensure_html(text: str, lang: str = "de") -> str:
    """If content isn't HTML-ish, wrap into <p> blocks; allow only <h3> and <p>."""
    t = (text or "").strip()
    if "<" in t and ">" in t:
        # still strip lists & numbers
        return _strip_lists_and_numbers(t)
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    out: List[str] = []
    for ln in lines:
        if ln.startswith("#"):
            level = min(3, len(ln) - len(ln.lstrip("#")))
            txt = ln[level:].strip()
            out.append(f"<h{level}>{txt}</h{level}>")
        else:
            out.append(f"<p>{ln}</p>")
    return _strip_lists_and_numbers("\n".join(out))

def _data_uri_for(path: str) -> Optional[str]:
    if not path or path.startswith(("http://", "https://", "data:")):
        return path
    p = Path(path)
    if not p.is_absolute():
        p = BASE_DIR / path
    if not p.exists():
        # try templates dir
        cand = TEMPLATES_DIR / path
        if not cand.exists():
            return None
        p = cand
    mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None

def _inline_local_images(html: str) -> str:
    def repl(m):
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        data = _data_uri_for(src)
        if not data:
            return m.group(0)
        return m.group(0).replace(src, data)
    return re.sub(r'src="([^"]+)"', repl, html)

def _extract_branche(d: Dict[str, Any]) -> str:
    raw = str(d.get("branche") or d.get("industry") or d.get("sector") or "").strip().lower()
    m = {
        "beratung": "beratung", "consulting": "beratung",
        "it": "it", "software": "it", "information technology": "it", "saas": "it",
        "marketing": "marketing", "werbung": "marketing", "advertising": "marketing",
        "bau": "bau", "construction": "bau", "architecture": "bau",
        "industrie": "industrie", "produktion": "industrie", "manufacturing": "industrie",
        "handel": "handel", "retail": "handel", "e-commerce": "handel", "ecommerce": "handel",
        "finanzen": "finanzen", "finance": "finanzen", "insurance": "finanzen",
        "gesundheit": "gesundheit", "health": "gesundheit", "healthcare": "gesundheit",
        "medien": "medien", "media": "medien",
        "logistik": "logistik", "logistics": "logistik",
        "verwaltung": "verwaltung", "public administration": "verwaltung",
        "bildung": "bildung", "education": "bildung",
    }
    if raw in m:
        return m[raw]
    for k, v in m.items():
        if k in raw:
            return v
    return "default"

def _as_int(x: Any) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None

# --------------------------------------------------------------------------------------
# Context, compliance, funding, tools & live updates
# --------------------------------------------------------------------------------------

def is_self_employed(data: dict) -> bool:
    keys_text = [
        "beschaeftigungsform","beschäftigungsform","arbeitsform","rolle","role","occupation",
        "unternehmensform","company_type"
    ]
    txt = " ".join(str(data.get(k, "") or "") for k in keys_text).lower()
    if any(s in txt for s in ["selbst", "freelanc", "solo", "self-employ"]):
        return True
    for k in ["mitarbeiter", "mitarbeiterzahl", "anzahl_mitarbeiter", "employees", "employee_count", "team_size"]:
        n = _as_int(data.get(k))
        if n is not None and n <= 1:
            return True
    return False

def _norm_size(x: str) -> str:
    x = (x or "").lower()
    if x in {"solo","einzel","einzelunternehmer","freelancer","soloselbstständig","soloselbststaendig"}: return "solo"
    if x in {"team","small","2-10","2–10"}: return "team"
    if x in {"kmu","sme","mittelstand","11-100","11–100"}: return "kmu"
    return ""

def load_yaml(path: str) -> Any:
    import yaml  # lazy
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def build_context(data: dict, branche: str, lang: str = "de") -> dict:
    lang = _norm_lang(lang)
    context_path = f"branchenkontext/{branche}.{lang}.yaml"
    if not (BASE_DIR / context_path).exists():
        context_path = f"branchenkontext/default.{lang}.yaml"
    context = load_yaml(str(BASE_DIR / context_path)) if (BASE_DIR / context_path).exists() else {}
    context.update(data or {})
    context["lang"] = lang

    # Company size classification
    def _get_employee_count(d: dict) -> Optional[int]:
        for key in ["mitarbeiter","mitarbeiterzahl","anzahl_mitarbeiter","employees","employee_count","team_size"]:
            n = _as_int(d.get(key))
            if n is not None:
                return n
        sz = (d.get("unternehmensgroesse") or d.get("company_size") or "").strip().lower()
        if sz:
            if any(s in sz for s in ["solo", "einzel", "self"]):
                return 1
            m = re.match(r"(\d+)", sz)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    pass
        return None

    emp_count = _get_employee_count(context)
    self_emp = is_self_employed(context)
    if self_emp or (emp_count is not None and emp_count <= 1):
        cat = "solo"
    elif emp_count is None or emp_count <= 10:
        cat = "team"
    else:
        cat = "kmu"

    if lang == "de":
        label = {"solo":"Solo-Unternehmer:in","team":"Team (2–10 Mitarbeitende)","kmu":"KMU (11+ Mitarbeitende)"}[cat]
    else:
        label = {"solo":"Solo entrepreneur","team":"Small team (2–10 people)","kmu":"SME (11+ people)"}[cat]

    context["company_size_category"] = cat
    context["company_size_label"] = label
    context["unternehmensgroesse"] = label
    context["is_self_employed"] = self_emp

    # Branch
    if lang != "de":
        de2en = {
            "beratung":"consulting","bau":"construction","bildung":"education","finanzen":"finance",
            "gesundheit":"healthcare","handel":"trade","industrie":"industry","it":"IT","logistik":"logistics",
            "marketing":"marketing","medien":"media","verwaltung":"public administration","default":"other"
        }
        context["branche"] = de2en.get(branche, branche)
    else:
        context["branche"] = branche

    # convenient aliases
    context["hauptleistung"] = context.get("hauptleistung") or context.get("main_service") or context.get("hauptprodukt") or ""
    context["projektziel"] = context.get("projektziel") or context.get("ziel") or context.get("goal") or ""

    return context

def build_compliance_html(lang: str = "de") -> str:
    if lang == "de":
        return (
            "<h3>Compliance & Verantwortung</h3>"
            "<p>Dieser Bericht folgt den Grundprinzipien der DSGVO, dem ePrivacy-Rahmen, dem Digital Services Act sowie den Leitplanken des EU‑AI‑Act. "
            "Er behandelt personenbezogene Daten zurückhaltend, empfiehlt datensparsame Architekturentscheidungen und verweist auf geeignete Rechtsgrundlagen. "
            "Ethische Leitlinien wie Fairness, Transparenz, Verantwortung und menschliche Aufsicht sind integraler Bestandteil der Empfehlungen.</p>"
            "<p>Bitte verstehen Sie die Inhalte als professionelle Orientierung, nicht als Rechtsberatung. "
            "Für verbindliche Prüfungen empfehlen wir eine juristische Begleitung.</p>"
        )
    else:
        return (
            "<h3>Compliance & responsibility</h3>"
            "<p>This report aligns with the GDPR, the ePrivacy framework, the Digital Services Act and the EU AI Act. "
            "It advocates data‑minimising designs, appropriate legal bases and clear governance with human oversight, fairness and transparency.</p>"
            "<p>The content is professional guidance, not legal advice. Please consult counsel for binding assessments.</p>"
        )

def _load_csv_candidates(names: List[str]) -> str:
    # prefer data/ then project root, then nested backend path
    for n in names:
        p = BASE_DIR / "data" / n
        if p.exists():
            return str(p)
    for n in names:
        p = BASE_DIR / n
        if p.exists():
            return str(p)
    nested = BASE_DIR / "ki_backend" / "make-ki-backend-neu-main" / "data"
    for n in names:
        p = nested / n
        if p.exists():
            return str(p)
    return ""

def _read_rows(path: str) -> List[Dict[str, str]]:
    if not path:
        return []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in rd]
    except Exception:
        return []

def build_funding_details_struct(data: Dict[str, Any], lang: str = "de", max_items: int = 6) -> Tuple[List[Dict[str, str]], str]:
    path = _load_csv_candidates(["foerdermittel.csv", "foerderprogramme.csv"])
    rows = _read_rows(path)
    out: List[Dict[str, str]] = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")
    region = (str(data.get("bundesland") or data.get("state") or "")).lower().strip()
    if region == "be":
        region = "berlin"
    for r in rows:
        name = r.get("Name") or r.get("name") or r.get("Programm") or r.get("programm") or ""
        if not name:
            continue
        target = (r.get("Zielgruppe") or r.get("zielgruppe") or r.get("target") or "").lower()
        reg = (r.get("Region") or r.get("region") or r.get("bundesland") or "").lower()
        grant = r.get("Fördersumme (€)") or r.get("foerderart") or r.get("grant") or ""
        purpose = r.get("Beschreibung") or r.get("einsatz") or r.get("use_case") or ""
        link = r.get("Link") or r.get("link") or r.get("url") or ""
        # filter by size (permissive)
        if size and target:
            if size not in target and not (target == "kmu" and size in {"team","kmu"}):
                continue
        score = 0
        if region and reg == region:
            score -= 5
        if reg in {"bund","de"}:
            score -= 1
        out.append({
            "name": name, "target": target, "region": reg,
            "grant": grant, "use_case": purpose, "link": link, "_score": score
        })
    out = sorted(out, key=lambda x: x.get("_score", 0))[:max_items]
    for o in out:
        o.pop("_score", None)
    stand = ""
    try:
        ts = os.path.getmtime(path)
        stand = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        pass
    return out, stand

def build_funding_narrative(data: Dict[str, Any], lang: str = "de", max_items: int = 6) -> str:
    rows, stand = build_funding_details_struct(data, lang, max_items)
    if not rows:
        return ""
    ps: List[str] = []
    if lang == "de":
        for r in rows:
            p = f"<p><b>{r['name']}</b> – geeignet für {r.get('target','KMU')}, Region: {r.get('region','DE')}. {r.get('use_case','')}"
            if r.get("grant"):
                p += f" <i>(Förderart/-höhe: {r['grant']})</i>"
            if r.get("link"):
                p += f' <a href="{r["link"]}">Zum Programm</a>'
            p += "</p>"
            ps.append(p)
        if stand:
            ps.append(f'<p style="font-size:10px;color:#5B6B7C">Stand: {stand}</p>')
    else:
        for r in rows:
            p = f"<p><b>{r['name']}</b> – suitable for {r.get('target','SMEs')}, region: {r.get('region','DE')}. {r.get('use_case','')}"
            if r.get("grant"):
                p += f" <i>(Grant/amount: {r['grant']})</i>"
            if r.get("link"):
                p += f' <a href="{r["link"]}">Open</a>'
            p += "</p>"
            ps.append(p)
        if stand:
            ps.append(f'<p style="font-size:10px;color:#5B6B7C">Updated: {stand}</p>')
    return "".join(ps)

def build_tools_details_struct(data: Dict[str, Any], branche: str, lang: str = "de", max_items: int = 8) -> List[Dict[str, str]]:
    path = _load_csv_candidates(["tools.csv", "ki_tools.csv"])
    rows = _read_rows(path)
    out: List[Dict[str, str]] = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")
    for r in rows:
        name = r.get("Tool-Name") or r.get("Name") or r.get("Tool") or r.get("name") or ""
        if not name:
            continue
        tags = (r.get("Branche-Slugs") or r.get("Tags") or r.get("Branche") or "").lower()
        row_size = (r.get("Unternehmensgröße") or r.get("Unternehmensgroesse") or r.get("company_size") or "").lower()
        if branche and tags and branche not in tags:
            continue
        if size and row_size and row_size not in {"alle", size}:
            if not ((row_size == "kmu" and size in {"team","kmu"}) or (row_size == "team" and size == "solo")):
                continue
        out.append({
            "name": name,
            "category": r.get("Kategorie") or r.get("kategorie") or r.get("category") or "",
            "usecase": r.get("Funktion/Zweck") or r.get("Einsatz") or r.get("use_case") or "",
            "hosting": r.get("Datenschutz") or r.get("hosting") or r.get("data") or "n/a",
            "price": r.get("Kosten") or r.get("Preis") or r.get("price") or r.get("kosten") or "n/a",
            "link": r.get("Link") or r.get("Website") or r.get("URL") or ""
        })
    return out[:max_items]

def build_tools_narrative(data: Dict[str, Any], branche: str, lang: str = "de", max_items: int = 8) -> str:
    rows = build_tools_details_struct(data, branche, lang, max_items)
    if not rows:
        return ""
    ps: List[str] = []
    if lang == "de":
        for r in rows:
            p = f"<p><b>{r['name']}</b> ({r.get('category','')}) – geeignet für {r.get('usecase','Alltag')}. "                 f"Hosting/Datenschutz: {r.get('hosting','n/a')}; Preis: {r.get('price','n/a')}."
            if r.get("link"): p += f' <a href="{r["link"]}">Zur Website</a>'
            p += "</p>"
            ps.append(p)
    else:
        for r in rows:
            p = f"<p><b>{r['name']}</b> ({r.get('category','')}) – suitable for {r.get('usecase','daily work')}. "                 f"Hosting/data: {r.get('hosting','n/a')}; price: {r.get('price','n/a')}."
            if r.get("link"): p += f' <a href="{r["link"]}">Website</a>'
            p += "</p>"
            ps.append(p)
    return "".join(ps)

def _tavily_search(query: str, max_results: int = 5, days: Optional[int] = None) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    payload = {
        "api_key": key, "query": query, "max_results": max_results,
        "include_answer": False, "search_depth": os.getenv("SEARCH_DEPTH","basic")
    }
    if days:
        payload["days"] = days
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
            res: List[Dict[str, Any]] = []
            for item in data.get("results", [])[:max_results]:
                res.append({
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "published_date": item.get("published_date"),
                    "score": item.get("score"),
                })
            return res
    except Exception:
        return []

def _serpapi_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    key = os.getenv("SERPAPI_KEY", "").strip()
    if not key:
        return []
    try:
        with httpx.Client(timeout=12.0) as c:
            r = c.get("https://serpapi.com/search.json", params={"q": query, "num": max_results, "api_key": key})
            r.raise_for_status()
            data = r.json()
            res: List[Dict[str, Any]] = []
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
    if lang == "de":
        qs = [q for q in [f"Förderprogramm KI {region} {branche} {size}".strip(),
                          f"KI Tool {branche} {product} DSGVO".strip(), topic] if q]
        title = f"Neu seit {datetime.now().strftime('%B %Y')}"
    else:
        qs = [q for q in [f"AI funding {region} {branche} {size}".strip(),
                          f"GDPR-friendly AI tool {branche} {product}".strip(), topic] if q]
        title = f"New since {datetime.now().strftime('%B %Y')}"
    seen: set = set()
    items: List[str] = []
    for q in qs:
        res = _tavily_search(q, max_results=max_results, days=days) or _serpapi_search(q, max_results=max_results)
        for r in res:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            date = r.get("published_date") or ""
            li = f'<li><a href="{url}">{(r.get("title") or url)[:120]}</a>'
            if date:
                li += f' <span style="color:#5B6B7C">({date})</span>'
            snippet = (r.get("content") or "")[:240].replace("<","&lt;").replace(">","&gt;")
            if snippet:
                li += f"<br><span style='color:#5B6B7C;font-size:12px'>{snippet}</span>"
            li += "</li>"
            items.append(li)
    html = "<ul>" + "".join(items[:max_results]) + "</ul>" if items else ""
    return title, html

# --------------------------------------------------------------------------------------
# LLM prompting helpers
# --------------------------------------------------------------------------------------

def render_prompt(template_text: str, context: dict) -> str:
    def replace_join(m):
        key = m.group(1); sep = m.group(2)
        val = context.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)
    rendered = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", replace_join, template_text)
    def replace_simple(m):
        key = m.group(1); val = context.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", replace_simple, rendered)

def build_masterprompt(chapter: str, context: dict, lang: str = "de") -> str:
    primary_path = BASE_DIR / f"prompts/{lang}/{chapter}.md"
    prompt_text = load_text(str(primary_path)) if primary_path.exists() else ""
    if not prompt_text:
        prompt_text = f"[NO PROMPT FOUND for {chapter}/{lang}]\n\n"                       f"Bitte schreiben Sie dennoch warmes, narratives HTML ohne Listen und ohne Zahlen."
    prompt = render_prompt(prompt_text, context)
    if lang == "de":
        base_rules = (
            "Gib ausschließlich gültiges HTML ohne <html>-Wrapper zurück. "
            "Verwende nur <h3> und <p>. Keine Listen, keine Tabellen. "
            "Schreibe 2–3 zusammenhängende Absätze in freundlichem, motivierendem Ton. "
            "Integriere Best‑Practice‑Beispiele als kurze Geschichten. "
            "Keine Zahlen oder Prozentwerte."
        )
    else:
        base_rules = (
            "Return VALID HTML (no <html> wrapper). Use only <h3> and <p>. "
            "No lists or tables. Write 2–3 connected paragraphs in a warm, motivating tone. "
            "Integrate best‑practice stories. No numbers or percentages."
        )
    return prompt + "\n\n---\n" + base_rules

def _chat_complete(messages: List[Dict[str, str]], model_name: Optional[str], temperature: Optional[float] = None) -> str:
    if _OPENAI_CLIENT is None:
        # fallback for environments without OpenAI SDK
        return "<p>[LLM offline] – Bitte lokale Narrative verwenden.</p>"
    mdl = _resolve_model(model_name or os.getenv("GPT_MODEL_NAME", "gpt-4o-mini"))
    if temperature is None:
        temperature = float(os.getenv("GPT_TEMPERATURE", "0.3"))
    args: Dict[str, Any] = {"model": mdl, "messages": messages}
    if not str(mdl).startswith("gpt-5"):
        args["temperature"] = temperature
    resp = _OPENAI_CLIENT.chat.completions.create(**args)
    return (resp.choices[0].message.content or "").strip()

def gpt_generate_section_html(data: dict, branche: str, chapter: str, lang: str = "de") -> str:
    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    context = build_context(data, branche, lang)
    prompt = build_masterprompt(chapter, context, lang)
    sys = (
        "Sie sind TÜV‑zertifizierte:r KI‑Manager:in, KI‑Strategieberater:in sowie Datenschutz- und Fördermittel‑Expert:in. "
        "Liefern Sie präzise, umsetzbare, aktuelle und branchenrelevante Inhalte als HTML."
        if lang == "de" else
        "You are a TÜV‑certified AI manager and strategy consultant. "
        "Deliver precise, actionable, up‑to‑date, sector‑relevant content as HTML."
    )
    out = _chat_complete(
        messages=[{"role": "system", "content": sys}, {"role": "user", "content": prompt}],
        model_name=os.getenv("EXEC_SUMMARY_MODEL") if chapter == "executive_summary" else os.getenv("GPT_MODEL_NAME"),
        temperature=None,
    )
    return ensure_html(strip_code_fences(fix_encoding(out)), lang)

def fallback_vision(data: dict, lang: str = "de") -> str:
    lang = _norm_lang(lang)
    if lang == "de":
        return (
            "<h3>Strategische Leitidee</h3>"
            "<p>Ein KI‑Serviceportal für KMU bündelt Fragebögen, Arbeitsvorlagen und kuratierte Praxisbeispiele. "
            "Es erleichtert den Einstieg, schafft Orientierung und ermöglicht einen sicheren, schrittweisen Kompetenzausbau.</p>"
            "<p>Starten Sie mit einem fokussierten Prototypen, der unmittelbares Feedback bietet und den Weg zur Beratung vereinfacht. "
            "Mit der Zeit entsteht ein lebendiges Wissensökosystem, das neue Services inspiriert und Ihre Position als Vordenker stärkt.</p>"
        )
    else:
        return (
            "<h3>Strategic vision</h3>"
            "<p>An AI service portal for SMEs brings together questionnaires, working templates and curated case studies. "
            "It lowers the entry barrier, provides orientation and enables a safe, stepwise build‑up of capabilities.</p>"
            "<p>Begin with a focused prototype that offers instant feedback and smooth scheduling. "
            "Over time it grows into a living knowledge ecosystem that inspires new services and strengthens your leadership profile.</p>"
        )

# --------------------------------------------------------------------------------------
# TOC & template wiring
# --------------------------------------------------------------------------------------

def _toc_from_report(report: Dict[str, Any], lang: str) -> str:
    items: List[str] = []
    def add(key: str, label: str) -> None:
        if report.get(key):
            items.append(f"<li>{label}</li>")
    if lang == "de":
        add("exec_summary_html", "Executive Summary")
        add("quick_wins_html", "Schnelle Hebel")
        add("risks_html", "Risiken")
        add("recommendations_html", "Empfehlungen")
        add("roadmap_html", "Roadmap")
        add("vision_html", "Vision")
        add("gamechanger_html", "Innovation & Gamechanger")
        add("compliance_html", "Compliance")
        add("foerderprogramme_html", "Förderprogramme")
        add("tools_html", "KI‑Tools & Software")
    else:
        add("exec_summary_html", "Executive summary")
        add("quick_wins_html", "Quick wins")
        add("risks_html", "Key risks")
        add("recommendations_html", "Recommendations")
        add("roadmap_html", "Roadmap")
        add("vision_html", "Vision")
        add("gamechanger_html", "Innovation & Gamechanger")
        add("compliance_html", "Compliance")
        add("foerderprogramme_html", "Funding programmes")
        add("tools_html", "AI tools & software")
    return f"<ul>{''.join(items)}</ul>" if items else ""

# --------------------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------------------

def generate_full_report(data: dict, lang: str = "de") -> Dict[str, Any]:
    branche = _extract_branche(data)
    lang = _norm_lang(lang)

    # Build narrative sections via LLM with strong formatting rules
    exec_summary_html = gpt_generate_section_html(data, branche, "executive_summary", lang)
    quick_wins_html   = gpt_generate_section_html(data, branche, "quick_wins_narrative", lang)
    risks_html        = gpt_generate_section_html(data, branche, "risks_narrative", lang)
    recommendations_html = gpt_generate_section_html(data, branche, "recommendations_narrative", lang)
    roadmap_html      = gpt_generate_section_html(data, branche, "roadmap_narrative", lang)
    vision_html       = gpt_generate_section_html(data, branche, "vision", lang) or fallback_vision(data, lang)
    gamechanger_html  = gpt_generate_section_html(data, branche, "gamechanger", lang)
    compliance_html   = build_compliance_html(lang)
    foerderprogramme_html = build_funding_narrative(data, lang, max_items=6)
    tools_html        = build_tools_narrative(data, branche, lang, max_items=8)

    # Live updates block (optional)
    live_title, live_html = build_live_updates_html(data, lang, max_results=5)

    out: Dict[str, Any] = {
        "exec_summary_html": exec_summary_html,
        "quick_wins_html": quick_wins_html,
        "risks_html": risks_html,
        "recommendations_html": recommendations_html,
        "roadmap_html": roadmap_html,
        "vision_html": vision_html,
        "gamechanger_html": gamechanger_html,
        "compliance_html": compliance_html,
        "foerderprogramme_html": foerderprogramme_html,
        "tools_html": tools_html,
        "live_updates_title": live_title,
        "live_updates_html": live_html,
    }

    # Global sanitising pass (remove lists/numbers if any slipped in)
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = ensure_html(v, lang)

    return out

# --------------------------------------------------------------------------------------
# Public entrypoint used by main.py
# --------------------------------------------------------------------------------------

def analyze_briefing(body: Dict[str, Any], lang: str = "de") -> str:
    """
    Main entrypoint: build report context, render Jinja template, return HTML string.
    Expects `templates/pdf_template.html` or `templates/pdf_template_en.html`.
    """
    lang = _norm_lang(lang or body.get("lang") or body.get("language") or body.get("sprache"))
    branche = _extract_branche(body or {})
    report = generate_full_report(body or {}, lang)

    # Meta for template
    company = str(body.get("firma") or body.get("company") or "").strip()
    person  = str(body.get("name") or body.get("person") or "").strip()
    region  = str(body.get("bundesland") or body.get("state") or body.get("ort") or body.get("city") or "").strip()
    if lang == "de":
        title = "KI-Statusbericht"
        subtitle = "Narrativer KI‑Report – DSGVO & EU‑AI‑Act‑ready"
    else:
        title = "AI status report"
        subtitle = "Narrative report – GDPR & EU‑AI‑Act‑ready"

    meta = {
        "title": title,
        "subtitle": subtitle,
        "company": company,
        "person": person,
        "branche": branche,
        "region": region,
        "generated_on": datetime.now().strftime("%Y-%m-%d"),
    }

    ctx: Dict[str, Any] = {
        "lang": lang,
        "meta": meta,
        "now": datetime.now,
        "toc_html": _toc_from_report(report, lang),
        **report,
    }

    # Render template
    env = _jinja_env()
    tmpl = env.get_template(_pick_template(lang))
    html = tmpl.render(**ctx)

    # Inline local images (e.g. logo) to prevent broken links in PDF
    html = _inline_local_images(html)

    # Final safety pass
    html = strip_code_fences(fix_encoding(html))

    return html
