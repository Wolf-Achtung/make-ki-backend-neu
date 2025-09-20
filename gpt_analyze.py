
# gpt_analyze.py — Gold-Standard, fully repaired
# Version: 2025-09-20
# Notes:
# - Fixes "return outside function", "unexpected indent", missing helpers, and 'meta' undefined in template.
# - Enforces narrative, list-free HTML (<h3>, <p>) across chapters.
# - Integrates optional business prompts (business-prompt_de.txt / business-prompt_en.txt).
# - Provides robust fallbacks if prompts/templates/data files are missing.
# - Keeps compatibility with main.py calling analyze_briefing(body, lang).

from __future__ import annotations

import os
import re
import json
import csv
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

try:
    # openai>=1.0 client
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    _OPENAI_AVAILABLE = False

# Optional post-processing hook (if present alongside this module)
try:
    from postprocess_report import postprocess_report_dict  # type: ignore[attr-defined]
except Exception:
    postprocess_report_dict = None

# --------------------------------------------------------------------------------------
# Paths & constants
BASE_DIR: Path = Path(__file__).resolve().parent
TEMPLATES_DIR: Path = BASE_DIR / "templates"
PROMPTS_DIR: Path = BASE_DIR / "prompts"

# Unpack known archives once to ensure prompts/data are available
def _ensure_unzipped(zip_name: str, dest_dir: str) -> None:
    try:
        z = BASE_DIR / zip_name
        d = BASE_DIR / dest_dir
        if z.exists() and not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(z), "r") as zf:
                zf.extractall(str(d))
    except Exception:
        # Never block startup because of ZIP issues
        pass

_ensure_unzipped("prompts.zip", "prompts")
_ensure_unzipped("branchenkontext.zip", "branchenkontext")
_ensure_unzipped("data.zip", "data")
_ensure_unzipped("aus-Data.zip", "data")

# --------------------------------------------------------------------------------------
# Text sanitation and formatting helpers
def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").lower().strip()
    return "de" if l.startswith("de") else "en"

def _sanitize_text(value: str) -> str:
    """Remove invisible chars and vendor-specific phrasing; keep content readable."""
    if not value:
        return value
    bad = ["\uFFFE", "\uFEFF", "\u200B", "\u00AD"]
    t = str(value)
    for ch in bad:
        t = t.replace(ch, "")
    replacements = {
        "GPT‑": "LLM‑", "GPT-": "LLM-", "GPT basierte": "LLM-gestützte",
        "GPT‑basierte": "LLM-gestützte", "GPT-gestützt": "LLM-gestützte",
        "GPT‑gestützt": "LLM-gestützte"
    }
    for k, v in replacements.items():
        t = t.replace(k, v)
    return t

def strip_code_fences(text: str) -> str:
    if not text:
        return text
    t = text.replace("\r", "")
    t = t.replace("```html", "```").replace("```HTML", "```")
    while "```" in t:
        t = t.replace("```", "")
    return t.replace("`", "")

def ensure_html(text: str, lang: str = "de") -> str:
    """If no tags present, wrap each non-empty line in <p> and headings in <h3>."""
    t = (text or "").strip()
    if "<" in t and ">" in t:
        return t
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    html: List[str] = []
    for ln in lines:
        if ln.startswith("#"):
            level = min(3, max(1, len(ln) - len(ln.lstrip("#"))))
            txt = ln[level:].strip()
            html.append(f"<h{level}>{txt}</h{level}>")
        else:
            # remove leading bullets
            html.append("<p>" + re.sub(r"^[-*•]\s*", "", ln) + "</p>")
    return "\n".join(html)

def _strip_lists_and_numbers(html: str) -> str:
    """Collapse lists and numeric markers into narrative paragraphs."""
    if not html:
        return html
    t = html
    # Convert list items to sentences
    t = re.sub(r"</?ul[^>]*>", "", t, flags=re.I)
    t = re.sub(r"</?ol[^>]*>", "", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "<p>", t, flags=re.I)
    t = re.sub(r"</li>", "</p>", t, flags=re.I)
    # Remove simple numeric markers at line starts (e.g., "1. ", "2) ")
    t = re.sub(r"(?m)^\s*\d+[\.)]\s*", "", t)
    # Remove Markdown-style bullets if any slipped through
    t = re.sub(r"(?m)^\s*[-*•]\s*", "", t)
    # Enforce allowed tags only (<h3>, <p>, <a>, <i>, <b>, <span>)
    t = re.sub(r"<(?!/?(h3|p|a|i|b|span)\b)[^>]*>", "", t)
    return t

def _collapse_ws(html: str) -> str:
    if not html:
        return html
    # Collapse 3+ newlines to one
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html

def _as_int(x: Any) -> Optional[int]:
    try:
        return int(str(x).strip())
    except Exception:
        return None

# --------------------------------------------------------------------------------------
# Domain helpers
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
    for k, v in m.items():
        if k in raw:
            return v
    return "default"

def _norm_size(x: str) -> str:
    x = (x or "").lower()
    if x in {"solo","einzel","einzelunternehmer","freelancer","soloselbstständig","soloselbststaendig"}: return "solo"
    if x in {"team","small"}: return "team"
    if x in {"kmu","sme","mittelstand"}: return "kmu"
    return ""

# --------------------------------------------------------------------------------------
# Live updates (optional; resilient when keys are missing)
def _tavily_search(query: str, max_results: int = 5, days: Optional[int] = None) -> List[Dict[str, Any]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "search_depth": os.getenv("SEARCH_DEPTH","basic"),
    }
    if days is not None:
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
            out: List[Dict[str, Any]] = []
            for item in data.get("organic_results", [])[:max_results]:
                out.append({"title": item.get("title"), "url": item.get("link"), "content": item.get("snippet")})
            return out
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
    if lang.startswith("de"):
        queries = [q for q in [base_de, t_de, topic] if q]
        title = f"Neu seit {datetime.now():%B %Y}"
    else:
        queries = [q for q in [base_en, t_en, topic] if q]
        title = f"New since {datetime.now():%B %Y}"
    seen: set[str] = set()
    items: List[str] = []
    for q in queries:
        res = _tavily_search(q, max_results=max_results, days=days) or _serpapi_search(q, max_results=max_results)
        for r in res:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            date = r.get("published_date") or ""
            title_txt = (r.get("title") or url)[:120]
            li = '<li><a href="{u}">{t}</a>'.format(u=url, t=title_txt)
            if date:
                li += ' <span style="color:#5B6B7C">({d})</span>'.format(d=date)
            snippet = (r.get("content") or "")[:240].replace("<","&lt;").replace(">","&gt;")
            if snippet:
                li += "<br><span style='color:#5B6B7C;font-size:12px'>{s}</span>".format(s=snippet)
            li += "</li>"
            items.append(li)
    html = "<ul>" + "".join(items[:max_results]) + "</ul>" if items else ""
    return title, html

# --------------------------------------------------------------------------------------
# Data loaders
def _load_csv_candidates(names: List[str]) -> str:
    # prefer ./data/name, fallback to ./name, then nested ./ki_backend/... paths
    for n in names:
        p = BASE_DIR / "data" / n
        if p.exists():
            return str(p)
    for n in names:
        p2 = BASE_DIR / n
        if p2.exists():
            return str(p2)
    nested = BASE_DIR / "ki_backend" / "make-ki-backend-neu-main" / "data"
    for n in names:
        p3 = nested / n
        if p3.exists():
            return str(p3)
    return ""

def _read_rows(path: str) -> List[Dict[str, str]]:
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in rd]
    except Exception:
        return []

# --------------------------------------------------------------------------------------
# Funding & Tools narratives
def build_funding_details_struct(data: Dict[str, Any], lang: str = "de", max_items: int = 8) -> Tuple[List[Dict[str, str]], str]:
    path = _load_csv_candidates(["foerdermittel.csv","foerderprogramme.csv"])
    rows = _read_rows(path) if path else []
    out: List[Dict[str, str]] = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")
    region = (str(data.get("bundesland") or data.get("state") or "")).lower()
    if region in {"be"}:
        region = "berlin"
    for r in rows:
        name = r.get("name") or r.get("programm") or r.get("Program") or ""
        if not name:
            continue
        target = (r.get("zielgruppe") or r.get("target") or "").lower()
        reg = (r.get("region") or r.get("bundesland") or r.get("land") or "").lower()
        grant = r.get("foerderart") or r.get("grant") or r.get("quote") or r.get("kosten") or ""
        use_case = r.get("einsatz") or r.get("zweck") or r.get("beschreibung") or r.get("use_case") or ""
        link = r.get("link") or r.get("url") or ""
        if size and target:
            if size not in target and not (target == "kmu" and size in {"team","kmu"}):
                continue
        score = 0
        if region and reg == region:
            score -= 5
        if reg in {"bund","deutschland","de"}:
            score -= 1
        out.append({"name":name, "target":r.get("zielgruppe") or r.get("target") or "",
                    "region":r.get("region") or r.get("bundesland") or r.get("land") or "",
                    "grant":grant, "use_case":use_case, "link":link, "_score": score})
    out = sorted(out, key=lambda x: x.get("_score",0))[:max_items]
    stand = ""
    try:
        ts = os.path.getmtime(path)
        stand = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        pass
    for o in out:
        o.pop("_score", None)
    return out, stand

def build_funding_narrative(data: Dict[str, Any], lang: str = "de", max_items: int = 5) -> str:
    rows, _ = build_funding_details_struct(data, lang, max_items)
    if not rows:
        return ""
    ps: List[str] = []
    if lang.startswith("de"):
        for r in rows:
            p = "<p><b>{name}</b> – geeignet für {target}, Region: {region}. {uc} ".format(
                name=r.get("name",""),
                target=r.get("target","KMU") or "KMU",
                region=r.get("region","DE") or "DE",
                uc=r.get("use_case",""),
            )
            if r.get("grant"):
                p += "<i>Förderart/Kosten: {g}</i> ".format(g=r.get("grant"))
            if r.get("link"):
                p += '<a href="{u}">Zum Programm</a>'.format(u=r["link"])
            p += "</p>"
            ps.append(p)
    else:
        for r in rows:
            p = "<p><b>{name}</b> – suitable for {target}, region: {region}. {uc} ".format(
                name=r.get("name",""),
                target=r.get("target","SMEs") or "SMEs",
                region=r.get("region","DE") or "DE",
                uc=r.get("use_case",""),
            )
            if r.get("grant"):
                p += "<i>Grant/Costs: {g}</i> ".format(g=r.get("grant"))
            if r.get("link"):
                p += '<a href="{u}">Open</a>'.format(u=r["link"])
            p += "</p>"
            ps.append(p)
    return "\n".join(ps)

def build_tools_details_struct(data: Dict[str, Any], branche: str, lang: str = "de", max_items: int = 12) -> Tuple[List[Dict[str, str]], str]:
    path = _load_csv_candidates(["tools.csv","ki_tools.csv"])
    rows = _read_rows(path) if path else []
    out: List[Dict[str, str]] = []
    size = _norm_size(data.get("unternehmensgroesse") or data.get("company_size") or "")
    for r in rows:
        name = r.get("name") or r.get("Tool") or r.get("Tool-Name")
        if not name:
            continue
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

def build_tools_narrative(data: Dict[str, Any], branche: str, lang: str = "de", max_items: int = 6) -> str:
    rows, _ = build_tools_details_struct(data, branche, lang, max_items)
    if not rows:
        return ""
    ps: List[str] = []
    if lang.startswith("de"):
        for r in rows:
            p = "<p><b>{name}</b> ({cat}) – geeignet für {suit}. Hosting/Datenschutz: {host}; Preis: {pr}. ".format(
                name=r.get("name",""), cat=r.get("category",""), suit=r.get("suitable_for","Alltag"),
                host=r.get("hosting","n/a"), pr=r.get("price","n/a")
            )
            if r.get("link"):
                p += '<a href="{u}">Zur Website</a>'.format(u=r["link"])
            p += "</p>"
            ps.append(p)
    else:
        for r in rows:
            p = "<p><b>{name}</b> ({cat}) – suitable for {suit}. Hosting/data: {host}; price: {pr}. ".format(
                name=r.get("name",""), cat=r.get("category",""), suit=r.get("suitable_for","daily work"),
                host=r.get("hosting","n/a"), pr=r.get("price","n/a")
            )
            if r.get("link"):
                p += '<a href="{u}">Website</a>'.format(u=r["link"])
            p += "</p>"
            ps.append(p)
    return "\n".join(ps)

# --------------------------------------------------------------------------------------
# Compliance narrative
def build_compliance_html(lang: str = "de") -> str:
    if lang.startswith("de"):
        return (
            "<h3>Compliance</h3>"
            "<p>Ihr Report wurde so formuliert, dass er mit der DSGVO, dem ePrivacy‑Rahmen, dem Digital Services Act "
            "und dem EU AI Act kompatibel ist. Statt Zahlen und KPI‑Listen erhalten Sie qualitative Aussagen, "
            "die Verantwortlichkeiten, Risiken und klare nächste Schritte beschreiben.</p>"
            "<p>Für produktive KI‑Einsätze empfehlen wir Mindeststandards: Datenklassifikation und ‑minimierung, "
            "ein übersichtliches Einwilligungs- und Löschkonzept, dokumentierte Modellnutzung inklusive Prompt‑Versionierung "
            "sowie menschliche Aufsicht (Human‑in‑the‑Loop) für kritische Entscheidungen.</p>"
        )
    else:
        return (
            "<h3>Compliance</h3>"
            "<p>This report is worded to align with the GDPR, the ePrivacy framework, the Digital Services Act "
            "and the EU AI Act. Instead of numeric KPIs, you receive qualitative guidance covering responsibilities, "
            "risks and clear next steps.</p>"
            "<p>For production use we recommend minimum standards: data classification and minimisation, a clear consent "
            "and deletion concept, documented model usage with prompt versioning, and human‑in‑the‑loop oversight for "
            "high‑impact decisions.</p>"
        )

# --------------------------------------------------------------------------------------
# LLM integration (with optional business prompt injection)
def _load_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None

def _load_business_prompt(lang: str) -> str:
    if lang.startswith("de"):
        for p in [BASE_DIR / "business-prompt_de.txt", Path("/app/business-prompt_de.txt")]:
            txt = _load_text(p)
            if txt:
                return txt.strip()
    else:
        for p in [BASE_DIR / "business-prompt_en.txt", Path("/app/business-prompt_en.txt")]:
            txt = _load_text(p)
            if txt:
                return txt.strip()
    return ""

def _resolve_model(wanted: Optional[str]) -> str:
    fallbacks = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    w = (wanted or "").strip().lower()
    if not w or w.startswith("gpt-5"):
        return fallbacks[0]
    known = set(fallbacks) | {"gpt-4o-audio-preview", "gpt-4.1", "gpt-4.1-mini"}
    return w if w in known else fallbacks[0]

def _render_prompt_file(chapter: str, ctx: Dict[str, Any], lang: str) -> str:
    # canonical location
    p = PROMPTS_DIR / lang / f"{chapter}.md"
    prompt = _load_text(p) or f"[NO PROMPT FOUND for {chapter}/{lang}]"
    # simple {{ var }} plus {{ list|join(', ') }} replacement
    def repl_join(m):
        key, sep = m.group(1), m.group(2)
        val = ctx.get(key.strip(), "")
        return sep.join(str(v) for v in val) if isinstance(val, list) else str(val)
    prompt = re.sub(r"\{\{\s*(\w+)\s*\|\s*join\(\s*['\"]([^'\"]*)['\"]\s*\)\s*\}\}", repl_join, prompt)
    def repl_simple(m):
        key = m.group(1)
        val = ctx.get(key.strip(), "")
        return ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
    prompt = re.sub(r"\{\{\s*(\w+)\s*\}\}", repl_simple, prompt)
    return prompt

def _chat_complete(messages: List[Dict[str, str]], model_name: Optional[str]) -> str:
    if not _OPENAI_AVAILABLE:
        # Offline/dev mode: return a simple echo for diagnostics
        body = messages[-1]["content"] if messages else ""
        return "<h3>LLM offline</h3><p>{}</p>".format(re.sub(r"<[^>]+>", "", body)[:800])
    client = OpenAI()
    args: Dict[str, Any] = {
        "model": model_name or os.getenv("GPT_MODEL_NAME", "gpt-5"),
        "messages": messages,
    }
    # Temperature only for non gpt-5 models
    if not str(args["model"]).startswith("gpt-5"):
        try:
            args["temperature"] = float(os.getenv("GPT_TEMPERATURE", "0.3"))
        except Exception:
            args["temperature"] = 0.3
    resp = client.chat.completions.create(**args)
    return (resp.choices[0].message.content or "").strip()

def gpt_generate_section_html(data: Dict[str, Any], branche: str, chapter: str, lang: str = "de") -> str:
    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    # Build a lean context for prompt rendering
    ctx: Dict[str, Any] = dict(data or {})
    ctx["lang"] = lang
    ctx["branche"] = branche
    ctx["company_size_label"] = data.get("unternehmensgroesse") or data.get("company_size") or ""
    ctx["hauptleistung"] = data.get("hauptleistung") or data.get("main_service") or data.get("hauptprodukt") or ""
    # Compose the prompt: prompt file + global narrative rules
    prompt = _render_prompt_file(chapter, ctx, lang)
    if lang == "de":
        base_rules = (
            "Gib ausschließlich gültiges HTML ohne <html>-Wrapper zurück. "
            "Verwende nur <h3> und <p>. Keine Listen, keine Tabellen, keine Aufzählungen. "
            "Schreibe 2–3 zusammenhängende Absätze in warmem, motivierendem Ton. "
            "Integriere Best‑Practice‑Beispiele narrativ. Keine Zahlen oder Prozentwerte."
        )
    else:
        base_rules = (
            "Return VALID HTML only, no <html> wrapper. Use only <h3> and <p>. "
            "No lists or tables. Write 2–3 connected paragraphs in a warm, motivating tone. "
            "Integrate best‑practice examples narratively. No numbers or percentages."
        )
    business_prompt = _load_business_prompt(lang)
    system_msg = business_prompt.strip() if business_prompt else (
        "You are a TÜV‑certified AI manager and strategy consultant; generate precise, actionable, sector‑relevant HTML."
        if lang == "en" else
        "Sie sind TÜV‑zertifizierte:r KI‑Manager:in und Strategieberater:in; liefern Sie präzises, umsetzbares, branchenrelevantes HTML."
    )
    full_user = prompt + "\n\n---\n" + base_rules
    model_name = os.getenv("EXEC_SUMMARY_MODEL", os.getenv("GPT_MODEL_NAME")) if chapter == "executive_summary" else os.getenv("GPT_MODEL_NAME")
    model_name = _resolve_model(model_name)
    html = _chat_complete(
        messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": full_user}],
        model_name=model_name,
    )
    html = strip_code_fences(_sanitize_text(html))
    html = ensure_html(html, lang)
    html = _strip_lists_and_numbers(html)
    return _collapse_ws(html)

# --------------------------------------------------------------------------------------
# Context & report assembly
def _build_context(data: Dict[str, Any], lang: str) -> Dict[str, Any]:
    branche = _extract_branche(data)
    size_label = data.get("unternehmensgroesse") or data.get("company_size") or ""
    location = data.get("ort") or data.get("city") or data.get("bundesland") or data.get("state") or ""
    meta = {
        "title": "KI-Statusbericht" if lang == "de" else "AI Status Report",
        "date": datetime.now().strftime("%d.%m.%Y") if lang == "de" else datetime.now().strftime("%Y-%m-%d"),
        "branche": branche,
        "size": size_label,
        "location": location,
        "lang": lang,
    }
    return {"meta": meta, "branche": branche, "size_label": size_label, "location": location}

def generate_full_report(data: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    lang = _norm_lang(lang or data.get("lang") or "")
    ctx = _build_context(data, lang)
    branche = ctx["branche"]

    chapters = [
        ("executive_summary", "Executive Summary" if lang == "en" else "Executive Summary"),
        ("quick_wins", "Quick Wins" if lang == "en" else "Schnelle Hebel"),
        ("risks", "Risks" if lang == "en" else "Risiken"),
        ("recommendations", "Recommendations" if lang == "en" else "Empfehlungen"),
        ("roadmap", "Roadmap"),
        ("vision", "Vision"),
        ("innovation", "Innovation & Gamechanger"),
    ]

    out: Dict[str, Any] = {"meta": ctx["meta"]}

    # LLM-generated narrative sections
    for key, _title in chapters:
        try:
            html = gpt_generate_section_html(data, branche, key, lang=lang)
        except Exception:
            if key == "vision":
                html = "<h3>Vision</h3><p>Ein KI‑Serviceportal verbindet Fragebögen, Tools und Praxisbeispiele zu einem "
                html += "freundlichen Einstiegsort für KMU. So entsteht Schritt für Schritt eine tragfähige Roadmap.</p>"
            else:
                html = "<h3>–</h3><p>Dieses Kapitel konnte nicht generiert werden. Wir liefern narrative Platzhaltertexte.</p>"
        out[key] = html

    # Compliance (static narrative)
    out["compliance"] = build_compliance_html(lang)

    # Funding & Tools narratives
    out["funding_html"] = build_funding_narrative(data, lang=lang, max_items=6)
    out["tools_html"] = build_tools_narrative(data, branche=branche, lang=lang, max_items=8)

    # Live updates (if keys configured)
    try:
        title, html_list = build_live_updates_html(data, lang=lang, max_results=5)
    except Exception:
        title, html_list = ("", "")
    out["live_updates_title"] = title
    out["live_updates_html"] = html_list

    # Optional post-processing
    try:
        if callable(postprocess_report_dict):
            out = postprocess_report_dict(out, lang=lang)  # type: ignore[func-returns-value]
    except Exception:
        pass

    # Enforce narrative style on all string fields
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = _strip_lists_and_numbers(v)

    return out

# --------------------------------------------------------------------------------------
# Templating and public entry point
def _load_template() -> Optional[Any]:
    if TEMPLATES_DIR.exists():
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=False,
        )
        try:
            return env.get_template("pdf_template.html")
        except Exception:
            return None
    return None

def _fallback_html(out: Dict[str, Any]) -> str:
    m = out.get("meta", {})
    parts: List[str] = []
    def add(title_key: str, content_key: str):
        title = title_key
        content = out.get(content_key, "")
        if content:
            # If content already contains <h3>, use as is; else wrap
            if "<h3" not in content:
                parts.append("<h3>{}</h3>".format(title))
                parts.append("<p>{}</p>".format(re.sub(r"<[^>]+>", "", content)))
            else:
                parts.append(content)
    header = "<h3>{}</h3><p>{}</p>".format(
        "Narrativer KI‑Report – DSGVO & EU‑AI‑Act‑ready" if m.get("lang") == "de" else "Narrative AI Report – GDPR & EU AI Act ready",
        "Dieser Report setzt auf warmes, narratives Storytelling statt KPIs." if m.get("lang") == "de" else
        "This report favours warm, narrative storytelling over KPIs."
    )
    parts.append(header)
    add("Executive Summary", "executive_summary")
    add("Schnelle Hebel", "quick_wins")
    add("Risiken", "risks")
    add("Empfehlungen", "recommendations")
    add("Roadmap", "roadmap")
    add("Vision", "vision")
    add("Innovation & Gamechanger", "innovation")
    add("Compliance", "compliance")
    if out.get("funding_html"):
        parts.append("<h3>Förderprogramme</h3>")
        parts.append(out["funding_html"])
    if out.get("tools_html"):
        parts.append("<h3>KI‑Tools & Software</h3>")
        parts.append(out["tools_html"])
    if out.get("live_updates_html"):
        parts.append("<h3>{}</h3>".format(out.get("live_updates_title","Aktuelles")))
        parts.append(out["live_updates_html"])
    footer = "<p style='margin-top:40px;font-size:12px;color:#5B6B7C'>&copy; {y} KI‑Sicherheit.jetzt</p>".format(y=datetime.now().year)
    parts.append(footer)
    return "\n".join(parts)

def analyze_briefing(body: Any, lang: str = "de") -> str:
    """
    Public entry point called by main.py. Accepts a dict or a JSON string with the
    questionnaire answers, generates the report sections and renders them into the
    PDF template. Returns the final HTML string.
    """
    # Parse body
    data: Dict[str, Any]
    if isinstance(body, (str, bytes)):
        try:
            data = json.loads(body if isinstance(body, str) else body.decode("utf-8"))
        except Exception:
            data = {}
    elif isinstance(body, dict):
        data = dict(body)
    else:
        data = {}

    lang = _norm_lang(data.get("lang") or data.get("language") or data.get("sprache") or lang)
    out = generate_full_report(data, lang=lang)
    out["lang"] = lang  # convenience for templates

    tmpl = _load_template()
    if tmpl is None:
        # Template missing -> return a simple concatenated HTML
        return _fallback_html(out)

    # Build comprehensive context expected by pdf_template.html
    meta = out.get("meta", {})
    ctx: Dict[str, Any] = {
        "meta": meta,
        "executive_summary": out.get("executive_summary", ""),
        "quick_wins": out.get("quick_wins", ""),
        "risks": out.get("risks", ""),
        "recommendations": out.get("recommendations", ""),
        "roadmap": out.get("roadmap", ""),
        "vision": out.get("vision", ""),
        "innovation": out.get("innovation", ""),
        "compliance": out.get("compliance", ""),
        "funding_html": out.get("funding_html", ""),
        "tools_html": out.get("tools_html", ""),
        "live_updates_title": out.get("live_updates_title", ""),
        "live_updates_html": out.get("live_updates_html", ""),
        "now": datetime.now,
        "lang": lang,
    }

    try:
        html = tmpl.render(**ctx)
    except Exception as ex:
        # If template rendering fails (e.g., unknown variables), fall back
        # to a self-contained HTML while logging a minimal error notice.
        msg = "<p style='color:#B00020'>Template error: {}</p>".format(str(ex))
        return msg + _fallback_html(out)

    return html
