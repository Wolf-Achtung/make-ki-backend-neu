
# gpt_analyze.py — Gold‑Standard (Wolf Edition)
# Version: 2025-09-25 (FULL, UPDATED)
# Highlights in this build:
# - Number/Slider Sanitizer (robust: clamps, handles NaN/empty/strings)
# - Coaching mode: integrates coach prompts (de/en) with graceful fallback
# - Tools chapter: CSV/MD fallback + mini-criteria badges (“EU‑Hosting”, “Open Source”, “Low‑Code”)
# - Funding chapter: CSV fallback + Tavily live search with optional deadline parsing (“Frist”)
# - Live updates box (optional) via Tavily; SERPAPI optional fallback
# - Prompt resolver: loads ALL *.txt in /app/prompts (and local ./prompts) to comply with “alle Prompts nutzen”
# - Template‑first return: we return a context dict (no HTML string), so main.py renders pdf_template(_en).html
# - No stray artifacts: strips code fences, list markers, residual placeholders
# - Compatible entrypoint: analyze_briefing(body, lang='de')

from __future__ import annotations

import os, re, json, csv, mimetypes
from pathlib import Path
from datetime import datetime as _dt
from typing import Dict, Any, Optional, List, Tuple

import httpx

# OpenAI (v1 client)
try:
    from openai import OpenAI  # type: ignore
    _openai_client = OpenAI()
except Exception:  # library not present in local tests
    _openai_client = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIRS = [BASE_DIR / "data", BASE_DIR, Path("/app/data")]
PROMPT_DIRS = [BASE_DIR / "prompts", Path("/app/prompts")]

# ----------------------------- Utilities -----------------------------

def _strip_code_fences(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s.strip(), flags=re.MULTILINE)
    s = re.sub(r"\s*```$", "", s, flags=re.MULTILINE)
    return s.strip()

def _sanitize_text(s: str) -> str:
    if not s:
        return s or ""
    s = _strip_code_fences(s)
    # remove stray checklist markers like "[] **" or "[] **Text"
    s = re.sub(r"\[\]\s*\*\*", "", s)
    # collapse bullets left-overs
    s = re.sub(r"^[\-\*\•]\s*", "", s, flags=re.MULTILINE)
    # normalize whitespace
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _dedupe(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        k = x.strip().lower()
        if k in seen: 
            continue
        seen.add(k); out.append(x)
    return out

def _find_data_file(candidates: List[str]) -> Optional[Path]:
    for d in DATA_DIRS:
        for name in candidates:
            p = d / name
            if p.exists() and p.is_file():
                return p
    return None

def _read_csv_rows(path: Optional[Path]) -> List[Dict[str, str]]:
    if not path:
        return []
    out: List[Dict[str, str]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            # dialect-safe
            sample = f.read(4096)
            f.seek(0)
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            for row in reader:
                out.append({k.strip(): (v or "").strip() for k, v in row.items()})
    except Exception:
        return []
    return out

# ----------------------------- Answer normalization -----------------------------

def _to_int(x: Any, default: int, lo: int, hi: int) -> int:
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            v = int(round(float(x)))
        else:
            # accept strings like "5", "7.0", "—", "undefined"
            s = str(x).strip().replace(",", ".")
            if not s or s.lower() in {"nan", "none", "null", "undefined", "—", "-"}:
                return default
            v = int(round(float(re.findall(r"[-+]?\d*\.?\d+", s)[0])))
        if v < lo:
            return lo
        if v > hi:
            return hi
        return v
    except Exception:
        return default

def _map_range_bucket(val: str, mapping: Dict[str, int], default: int) -> int:
    if not val:
        return default
    s = str(val).strip().lower()
    return mapping.get(s, default)

def _norm_size(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in {"1", "solo", "einzel", "freelancer", "freiberuflich"}:
        return "solo"
    if v in {"2–10", "2-10", "2_10", "team", "small", "small team"}:
        return "team"
    if v in {"11–100", "11-100", "kmu", "sme"}:
        return "kmu"
    return v or "kmu"

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
    return "beratung"

# ----------------------------- Prompts -----------------------------

def _scan_prompt_files() -> Dict[str, str]:
    """
    Loads ALL *.txt under known prompt folders.
    Returns dict {name_without_ext: content}.
    Supports aliases:
      - business_coach_(de|en).txt
      - business_prompt_(de|en).txt  (alias)
      - persona_(de|en).txt
      - section_*.txt    (optional per-chapter)
    """
    found: Dict[str, str] = {}
    seen_paths: set[str] = set()
    for d in PROMPT_DIRS:
        if not d.exists():
            continue
        for p in d.glob("*.txt"):
            if p.as_posix() in seen_paths:
                continue
            try:
                txt = p.read_text(encoding="utf-8")
                name = p.stem
                found[name] = txt
                seen_paths.add(p.as_posix())
            except Exception:
                pass

    # Alias: if one exists, mirror to the other key
    for lang in ("de","en"):
        a = f"business_coach_{lang}"
        b = f"business_prompt_{lang}"
        if a in found and b not in found:
            found[b] = found[a]
        if b in found and a not in found:
            found[a] = found[b]
    return found

def _prompt_for(lang: str, *keys: str, prompts: Optional[Dict[str, str]] = None) -> str:
    """
    Tries: exact key, then key_lang, then fallback without lang.
    keys can be 'persona', 'business_coach', 'section_recommendations', etc.
    """
    if prompts is None:
        prompts = _scan_prompt_files()
    lang = "de" if str(lang).lower().startswith("de") else "en"
    for key in keys:
        candidates = [f"{key}_{lang}", key]
        for c in candidates:
            if c in prompts:
                return prompts[c]
    return ""  # okay: we are robust to empty coach/persona

# ----------------------------- Live search (Tavily / SerpAPI) -----------------------------

def _tavily_search(query: str, days: int = 30, max_results: int = 5) -> List[Dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "include_domains": [],
        "exclude_domains": [],
        "max_results": max_results,
        "days": days
    }
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            return data.get("results", []) or []
    except Exception:
        return []

def _serpapi_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    key = os.getenv("SERPAPI_KEY") or os.getenv("GOOGLE_SEARCH_API_KEY")
    if not key:
        return []
    url = "https://serpapi.com/search.json"
    params = {"q": query, "api_key": key, "num": max_results, "engine": "google"}
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            j = r.json()
            out = []
            for item in (j.get("organic_results") or [])[:max_results]:
                out.append({
                    "title": item.get("title"),
                    "url": item.get("link"),
                    "content": item.get("snippet")
                })
            return out
    except Exception:
        return []

def _make_link(url: str, title: str) -> str:
    title = _sanitize_text(title or url)
    url = (url or "").strip()
    return f'<a href="{url}">{title}</a>' if url else title

def _parse_deadline(text: str) -> Optional[str]:
    """
    Tries to parse a deadline from arbitrary text.
    Supports dd.mm.yyyy / yyyy-mm-dd and German month names.
    """
    if not text:
        return None
    t = text.strip()

    # 1) explicit ISO
    m = re.search(r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", t)
    if m:
        y, mo, d = m.groups()
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except Exception:
            pass

    # 2) German style: 31.12.2025
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", t)
    if m:
        d, mo, y = m.groups()
        y = int(y); y = (2000 + y) if y < 100 else y
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except Exception:
            pass

    # 3) Month name (German/English), naive
    months = {
        "januar":1, "februar":2, "märz":3, "maerz":3, "april":4, "mai":5, "juni":6, "juli":7,
        "august":8, "september":9, "oktober":10, "november":11, "dezember":12,
        "january":1, "february":2, "march":3, "april":4, "may":5, "june":6, "july":7,
        "august":8, "september":9, "october":10, "november":11, "december":12
    }
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\s*(\d{2,4})", t)
    if m:
        d, mon, y = m.groups()
        mon = mon.lower()
        mon = mon.replace("ä","ae").replace("ö","oe").replace("ü","ue")
        mo = months.get(mon)
        try:
            y = int(y); y = (2000 + y) if y < 100 else y
            if mo:
                return f"{y:04d}-{mo:02d}-{int(d):02d}"
        except Exception:
            pass
    return None

# ----------------------------- Domain mapping & labels -----------------------------

_SIZE_LABELS_DE = {"solo":"1 (Solo)","team":"2–10","kmu":"11–100"}
_SIZE_LABELS_EN = {"solo":"1 (solo)","team":"2–10","kmu":"11–100"}

def _labels_for_size(size: str, lang: str) -> str:
    if lang == "de":
        return _SIZE_LABELS_DE.get(size, size)
    return _SIZE_LABELS_EN.get(size, size)

# ----------------------------- Tool details (CSV fallback + badges) -----------------------------

def _badge_html(text: str) -> str:
    text = _sanitize_text(text)
    return f'<span class="chip">{text}</span>'

def _tool_badges(row: Dict[str, str]) -> List[str]:
    badges: List[str] = []
    val = (row.get("eu_hosting") or row.get("eu") or "").strip().lower()
    if val in {"1","true","yes","ja","y"}:
        badges.append("EU‑Hosting")
    val = (row.get("open_source") or row.get("oss") or "").strip().lower()
    if val in {"1","true","yes","ja","y"}:
        badges.append("Open Source")
    val = (row.get("low_code") or row.get("nocode") or "").strip().lower()
    if val in {"1","true","yes","ja","y"}:
        badges.append("Low‑Code")
    # optional: source badge (domain hint)
    src = (row.get("source") or row.get("vendor") or "").strip()
    if src:
        badges.append(f"Quelle: {src}")
    return badges

def build_tools_html(answers: Dict[str, Any], branche: str, lang: str, max_items: int = 12) -> str:
    rows = _read_csv_rows(_find_data_file(["tools.csv","ki_tools.csv","tools_de.csv","tools_en.csv"]))
    items: List[Dict[str,str]] = []

    if rows:
        for r in rows:
            # optional filtering by industry / size
            ind = (r.get("industry") or r.get("branche") or "").strip().lower()
            if ind and ind not in {"*", "all", "any"} and branche and (branche not in ind):
                continue
            items.append(r)
    else:
        # minimal curated fallback (safe, generic)
        items = [
            {"name":"n8n", "link":"https://n8n.io", "open_source":"1", "low_code":"1", "eu_hosting":"1", "source":"n8n"},
            {"name":"Make", "link":"https://www.make.com", "low_code":"1", "eu_hosting":"1", "source":"Make"},
            {"name":"Hugging Face", "link":"https://huggingface.co", "open_source":"1", "source":"HF"},
            {"name":"Odoo", "link":"https://www.odoo.com", "low_code":"1", "eu_hosting":"1", "source":"Odoo"},
            {"name":"Aleph Alpha", "link":"https://www.aleph-alpha.com", "eu_hosting":"1", "source":"Aleph Alpha"},
        ]

    out = []
    for r in items[:max_items]:
        name = _sanitize_text(r.get("name") or r.get("tool") or r.get("title") or "Tool")
        link = r.get("link") or r.get("url") or ""
        badges = " ".join(_badge_html(b) for b in _tool_badges(r))
        out.append(f"<p><b>{_make_link(link, name)}</b><br/>{badges}</p>")
    return "\n".join(out)

# ----------------------------- Funding (CSV + Tavily, w/ deadline) -----------------------------

def build_funding_html(answers: Dict[str, Any], lang: str, max_items: int = 8) -> str:
    rows = _read_csv_rows(_find_data_file(["foerderung.csv","foerderprogramme.csv","funding.csv"]))
    bundesland = (answers.get("bundesland") or answers.get("state") or "").strip()
    out = []

    def _row_to_html(r: Dict[str,str]) -> str:
        title = _sanitize_text(r.get("name") or r.get("title") or "Programm")
        link = r.get("link") or r.get("url") or ""
        region = r.get("region") or r.get("bundesland") or "DE"
        grant = r.get("grant") or r.get("zuschuss") or ""
        deadline = r.get("deadline") or r.get("frist") or ""
        if not deadline:
            deadline = _parse_deadline(" ".join([r.get("content",""), r.get("desc","") or ""]) or "") or "–"
        parts = [f"<b>{_make_link(link, title)}</b>"]
        if region: parts.append(f"({region})")
        if grant: parts.append(f" – {grant}")
        parts.append(f" · <b>Frist:</b> {deadline}")
        return "<p>" + " ".join(parts) + "</p>"

    if rows:
        for r in rows[:max_items]:
            out.append(_row_to_html(r))

    # Live augmentation via Tavily
    TAVILY_DAYS_FUNDING = int(os.getenv("TAVILY_DAYS_FUNDING") or os.getenv("SEARCH_DAYS_FUNDING") or 14)
    queries_de = [
        f"Förderprogramm Digitalisierung KI KMU {bundesland} aktuelle Ausschreibung Frist",
        f"Förderung Beratung Digitalisierung KMU {bundesland} Frist",
        "go-digital KMU Frist",
    ]
    queries_en = [
        f"funding program digitalisation AI SMEs {bundesland} Germany deadline",
        "grant consulting digitization SMEs Germany deadline",
    ]
    queries = queries_de if lang == "de" else queries_en

    live = []
    for q in queries:
        res = _tavily_search(q, days=TAVILY_DAYS_FUNDING, max_results=4) or _serpapi_search(q, max_results=3)
        for r in res:
            title = _sanitize_text(r.get("title") or "")
            url = r.get("url") or ""
            content = (r.get("content") or "")[:400]
            deadline = _parse_deadline(" ".join([title, content])) or "–"
            if not title or not url:
                continue
            live.append({
                "title": title,
                "url": url,
                "deadline": deadline
            })
    # de-dupe by title/url
    uniq = []
    seen = set()
    for r in live:
        k = (r["title"].lower(), r["url"])
        if k in seen:
            continue
        seen.add(k); uniq.append(r)
    for r in uniq[:max_items - len(out)]:
        out.append(_row_to_html(r))
    return "\n".join(out)

# ----------------------------- Live updates box -----------------------------

def build_live_updates_html(answers: Dict[str,Any], lang: str) -> str:
    state = (answers.get("bundesland") or answers.get("state") or "").strip()
    branche = _extract_branche(answers)
    TAVILY_DAYS_TOOLS = int(os.getenv("TAVILY_DAYS_TOOLS") or os.getenv("SEARCH_DAYS_TOOLS") or 30)
    qs_de = [
        f"EU AI Act Umsetzung Leitfaden {state} KMU",
        f"neue KI-Tools Update 2025 {branche}",
        f"Fördermittel Digitalisierung {state} Frist 2025"
    ]
    qs_en = [
        f"EU AI Act implementation guide {state} SMEs",
        f"new AI tools update 2025 {branche}",
        f"funding digitalisation {state} deadline 2025"
    ]
    qs = qs_de if lang == "de" else qs_en
    items = []
    for q in qs:
        res = _tavily_search(q, days=TAVILY_DAYS_TOOLS, max_results=4) or _serpapi_search(q, max_results=3)
        for r in (res or [])[:3]:
            t = _sanitize_text(r.get("title") or "")
            u = r.get("url") or ""
            c = (r.get("content") or "").strip()
            if not t or not u:
                continue
            items.append(f"<li>{_make_link(u, t)}</li>")
    items = _dedupe(items)[:7]
    if not items:
        return ""
    return "<ul>" + "\n".join(items) + "</ul>"

# ----------------------------- LLM helpers -----------------------------

def _resolve_model() -> str:
    # keep conservative defaults; main.py already posts to chat/completions (as per logs)
    env_model = os.getenv("OPENAI_MODEL") or ""
    if env_model:
        return env_model
    return "gpt-4.1-mini"

def _chat_complete(system_prompt: str, user_prompt: str, lang: str) -> str:
    if _openai_client is None:
        # local test fallback: return user_prompt trimmed
        return _sanitize_text(user_prompt)[:1800]

    model = _resolve_model()
    try:
        resp = _openai_client.chat.completions.create(
            model=model,
            temperature=0.2,
            max_tokens=1200,
            messages=[
                {"role":"system","content":system_prompt},
                {"role":"user","content":user_prompt}
            ]
        )
        txt = (resp.choices[0].message.content or "").strip()
        return _sanitize_text(txt)
    except Exception:
        return ""

def _render_context_snippet(answers: Dict[str, Any], lang: str) -> str:
    # compact, ordered context for the LLM
    size = _norm_size(answers.get("unternehmensgroesse"))
    main_prod = answers.get("hauptleistung") or answers.get("main_product") or ""
    bundesland = answers.get("bundesland") or ""
    ziele = ", ".join(answers.get("projektziel") or answers.get("project_goals") or [])
    usecases = ", ".join(answers.get("ki_usecases") or answers.get("usecases") or [])
    hemmnisse = ", ".join(answers.get("ki_hemmnisse") or [])
    risikofreude = _to_int(answers.get("risikofreude"), 3, 1, 5)
    digital = _to_int(answers.get("digitalisierungsgrad"), 5, 1, 10)
    papierlos_map = {"0-20":10,"21-50":40,"51-80":70,"81-100":90}
    papierlos = _map_range_bucket(answers.get("prozesse_papierlos") or "", papierlos_map, 40)
    auto_map = {"sehr_niedrig":10,"eher_niedrig":25,"mittel":50,"eher_hoch":70,"sehr_hoch":85}
    auto = _map_range_bucket(answers.get("automatisierungsgrad") or "", auto_map, 40)

    if lang == "de":
        return (
            f"Branche: { _extract_branche(answers) }\n"
            f"Größe: { size }\n"
            f"Bundesland: { bundesland }\n"
            f"Hauptleistung: { main_prod }\n"
            f"Ziele: { ziele }\n"
            f"Use‑Cases: { usecases }\n"
            f"Hemmnisse: { hemmnisse }\n"
            f"Digitalisierungsgrad: { digital }/10; Papierlos: { papierlos }/100; Automatisierung: { auto }/100; Risikofreude: { risikofreude }/5\n"
        ).strip()
    else:
        return (
            f"Industry: { _extract_branche(answers) }\n"
            f"Size: { size }\n"
            f"State: { bundesland }\n"
            f"Main product: { main_prod }\n"
            f"Goals: { ziele }\n"
            f"Use‑cases: { usecases }\n"
            f"Barriers: { hemmnisse }\n"
            f"Digitalisation: { digital }/10; Paperless: { papierlos }/100; Automation: { auto }/100; Risk appetite: { risikofreude }/5\n"
        ).strip()

def _build_system_prompt(lang: str, persona: str, coach: str) -> str:
    base = "Warm, friendly, optimistic, jargon‑free. Concise paragraphs, no bullets unless asked."
    if lang == "de":
        base = "Warm, freundschaftlich, optimistisch, jargonfrei. Prägnante Absätze, nur dort Listen, wo sinnvoll."
    parts = [
        base,
        "Cover DSGVO, ePrivacy, Digital Services Act und EU AI Act mit klaren, verständlichen Hinweisen (keine Rechtsberatung).",
        "Nutze die branchenspezifischen Antworten, generiere Executive Summary, Quick Wins, Empfehlungen, Roadmap, Risiken.",
        "Wenn Coaching‑Prompt vorhanden, hänge ein kurzes Coaching‑Kapitel an (Fragen/Impulse, 6–10 Zeilen).",
        "Keine Platzhaltertexte, keine Code‑Fences, keine Marker wie [] **."
    ]
    if persona:
        parts.append(persona.strip())
    if coach:
        # Keep coach content short; we will call it only for its tone and scaffolding.
        parts.append(("Coach:\n" + coach.strip())[:1800])
    return "\n\n".join(parts)

def _build_user_prompt(answers: Dict[str, Any], section: str, lang: str, extra: str = "") -> str:
    ctx = _render_context_snippet(answers, lang)
    if lang == "de":
        head = f"Erzeuge das Kapitel: {section} (de)."
    else:
        head = f"Generate the chapter: {section} (en)."
    return f"{head}\n\nKontext:\n{ctx}\n\n{extra}".strip()

def gpt_generate_section_html(answers: Dict[str, Any], section: str, lang: str, persona: str, coach: str) -> str:
    # Build prompts
    sys_prompt = _build_system_prompt(lang, persona, coach)
    user_prompt = _build_user_prompt(answers, section, lang)
    out = _chat_complete(sys_prompt, user_prompt, lang)
    return _sanitize_text(out)

# ----------------------------- Score & charts -----------------------------

def _score_percent(answers: Dict[str,Any]) -> int:
    # Weighted aggregate from sliders/choices
    digital = _to_int(answers.get("digitalisierungsgrad"), 5, 1, 10) / 10.0
    risikofreude = _to_int(answers.get("risikofreude"), 3, 1, 5) / 5.0
    papierlos_map = {"0-20":0.1,"21-50":0.4,"51-80":0.7,"81-100":0.9}
    papierlos = papierlos_map.get((answers.get("prozesse_papierlos") or "").strip().lower(), 0.4)
    auto_map = {"sehr_niedrig":0.1,"eher_niedrig":0.3,"mittel":0.5,"eher_hoch":0.7,"sehr_hoch":0.85}
    auto = auto_map.get((answers.get("automatisierungsgrad") or "").strip().lower(), 0.4)

    # Simple weighted average
    score = 0.35*digital + 0.25*auto + 0.2*papierlos + 0.2*risikofreude
    pct = max(0,min(100,int(round(100*score))))
    return pct

# ----------------------------- Public entrypoint -----------------------------

def analyze_briefing(body: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """
    Main entrypoint called by main.py. Returns a context dict for the Jinja PDF templates.
    """
    # 1) normalize language
    lang = "de" if str(lang).lower().startswith("de") else "en"

    # 2) answers = body (formbuilder posts flat dict)
    answers = dict(body)

    # 3) sanitize critical numeric fields (robust against bad strings)
    answers["digitalisierungsgrad"] = _to_int(answers.get("digitalisierungsgrad"), 5, 1, 10)
    answers["risikofreude"] = _to_int(answers.get("risikofreude"), 3, 1, 5)

    # 4) basic meta & theme chips
    branche = _extract_branche(answers)
    size = _norm_size(answers.get("unternehmensgroesse"))
    size_label = _labels_for_size(size, lang)
    main_product = answers.get("hauptleistung") or answers.get("main_product") or ""
    bundesland = answers.get("bundesland") or ""

    chips = []
    if bundesland: chips.append(("Bundesland: " if lang=="de" else "State: ")+bundesland.upper())
    chips.append("DSGVO/EU‑AI‑Act")
    if os.getenv("TAVILY_API_KEY"): chips.append("Live via Tavily")
    chips = _dedupe(chips)

    # 5) prompts (persona + coach + optional per‑chapter in folder)
    prompts = _scan_prompt_files()
    persona = _prompt_for(lang, "persona", prompts=prompts)
    coach = _prompt_for(lang, "business_coach", "business_prompt", prompts=prompts)

    # 6) generate main narrative sections via LLM
    sections = [
        ("Executive Summary","executive_summary") if lang=="en" else ("Executive Summary","Executive Summary"),
        ("Quick Wins","quick_wins") if lang=="en" else ("Schnelle Hebel","quick_wins"),
        ("Risks","risks") if lang=="en" else ("Risiken","risks"),
        ("Recommendations","recommendations") if lang=="en" else ("Empfehlungen","recommendations"),
        ("Roadmap","roadmap") if lang=="en" else ("Roadmap","roadmap"),
        ("Compliance","compliance") if lang=="en" else ("Compliance","compliance"),
        ("Vision","vision") if lang=="en" else ("Vision","vision"),
        ("Gamechanger","gamechanger") if lang=="en" else ("Gamechanger","gamechanger"),
    ]

    html_parts: Dict[str, str] = {}
    for title, key in sections:
        html_parts[f"{key}_html"] = gpt_generate_section_html(answers, key, lang, persona, coach)

    # 7) short coaching appendix (behind recommendations)
    coaching_html = ""
    if coach.strip():
        extra = ("Bitte als kurzes Coaching‑Kapitel mit konkreten Fragen/Impulsen, 6–10 Sätze." if lang=="de"
                 else "Add a short coaching appendix with concrete prompts and reflection questions, ~6–10 sentences.")
        coaching_html = gpt_generate_section_html(answers, "coaching", lang, persona, coach + "\n" + extra)
        coaching_html = _sanitize_text(coaching_html)

    # 8) tools & funding (CSV + live)
    tools_html = build_tools_html(answers, branche, lang, max_items=12)
    funding_html = build_funding_html(answers, lang, max_items=8)

    # 9) optional live box
    live_html = build_live_updates_html(answers, lang)
    live_title = "Neu & relevant" if lang=="de" else "New & relevant"

    # 10) overall score
    score = _score_percent(answers)

    # 11) meta for template
    meta = {
        "title": "KI‑Statusbericht" if lang=="de" else "AI Readiness Report",
        "version": "2025‑09‑25",
        "author": "KI‑Sicherheit.jetzt"
    }

    # 12) assemble context for templates
    ctx: Dict[str, Any] = {
        "meta": meta,
        "branche": branche,
        "unternehmensgroesse": size,
        "company_size_label": size_label,
        "main_product": main_product,
        "hauptleistung": main_product,
        "bundesland": bundesland,
        "chips": chips,
        "score_percent": score,

        # narrative sections
        "exec_summary_html": html_parts.get("Executive Summary_html") or html_parts.get("executive_summary_html",""),
        "quick_wins_html": html_parts.get("quick_wins_html",""),
        "risks_html": html_parts.get("risks_html",""),
        "recommendations_html": html_parts.get("recommendations_html",""),
        "roadmap_html": html_parts.get("roadmap_html",""),
        "compliance_html": html_parts.get("compliance_html",""),
        "vision_html": html_parts.get("vision_html",""),
        "gamechanger_html": html_parts.get("gamechanger_html",""),
        "coaching_html": coaching_html,  # will be used by updated templates
        "coach_html": coaching_html,

        # data-driven sections
        "funding_html": funding_html,
        "tools_html": tools_html,
        "live_html": live_html,
        "live_title": live_title,

        # footer
        "copyright_owner": "Wolf Hohl",
        "copyright_year": _dt.now().year
    }
    # Final safety pass: clean accidental artifacts
    for k, v in list(ctx.items()):
        if isinstance(v, str):
            ctx[k] = _sanitize_text(v)
    return ctx

# End of file
