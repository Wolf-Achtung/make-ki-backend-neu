# gpt_analyze.py — Template-Only + Story‑Killer + Whitelist‑Only
# Version: 2025-09-21T22:00Z
# This module returns a **dict** only; final HTML must be rendered by Jinja templates
# (ENV: TEMPLATE_DE / TEMPLATE_EN). No direct HTML strings are returned.
from __future__ import annotations
import os, re, json
from pathlib import Path
from datetime import datetime as _dt
from typing import Dict, Any, List, Optional

# Optional: OpenAI client (for short, sanitized paragraphs only)
try:
    from openai import OpenAI
    _OPENAI = OpenAI()
except Exception:
    _OPENAI = None

BASE_DIR = Path(__file__).resolve().parent
PARTIAL_DIRS = [BASE_DIR / "templates" / "partials", BASE_DIR / "partials"]
DATA_DIRS = [BASE_DIR / "data", BASE_DIR]

# ---------------- Story‑Killer (ban anecdotes, metaphors, "Mehr erfahren", fantasy-tools) ----------------
_STORY_PATTERNS = [
    r"\bIn\s+einem\s+kleinen\s+Familienunternehmen\b",
    r"\bStellen\s+Sie\s+sich\b",
    r"\bPraxisbeispiel\b",
    r"\bDer\s+Beratungswald\b",
    r"\bEs\s+war\s+einmal\b",
    r"\bMehr\s+erfahren\b",
]
_FANTASY_TOOL_PATTERNS = [
    r"\bIdeation\s+Assistant\b", r"\bProject\s+Harmony\b", r"\bComms\s+Connect\b",
    r"\bPrivacyGuard\s+AI\b", r"\bSecureChat\s+AI\b", r"\bDataSafe\s+AI\b"
]

def _kill_story(html: str) -> str:
    if not html: return ""
    t = re.sub(r"<[^>]+>", " ", html or "")
    for pat in _STORY_PATTERNS + _FANTASY_TOOL_PATTERNS:
        if re.search(pat, t, flags=re.IGNORECASE):
            return ""
    # ban bare % / € without digits
    if re.search(r"%(?!\d)|€(?!\d)", t):
        return ""
    return html.strip()

# ---------------- Helpers ----------------
def _read_text(p: Path) -> str:
    try: return p.read_text(encoding="utf-8")
    except Exception: return ""

def _find_in(dirs: List[Path], name: str) -> Optional[Path]:
    for d in dirs:
        p = d / name
        if p.exists(): return p
    return None

def _load_json_any(name: str) -> List[Dict[str,Any]]:
    p = _find_in(DATA_DIRS, name)
    if not p: return []
    try: return json.loads(_read_text(p)) or []
    except Exception: return []

def _load_partial(name: str, fallback="") -> str:
    p = _find_in(PARTIAL_DIRS, name)
    return _read_text(p) if p else fallback

# ---------------- Whitelist renderers ----------------
def render_tools_from_whitelist(max_items: int = 12) -> str:
    rows = _load_json_any("tool_whitelist.json")
    if not rows:
        return "<p>— (keine kuratierten Einträge)</p>"
    head = "<tr><th>Kategorie</th><th>Option</th><th>Daten/Deployment</th><th>Hinweise</th></tr>"
    body = []
    for r in rows[:max_items]:
        name = r.get("name","—")
        if r.get("sovereign"):
            name += " <span class='badge'>souverän</span>"
        body.append(
            f"<tr><td>{r.get('category','—')}</td>"
            f"<td>{name}</td>"
            f"<td>{r.get('data_residency','—')}</td>"
            f"<td>{r.get('notes','')}</td></tr>"
        )
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def render_funding_from_whitelist(max_items: int = 8) -> str:
    rows = _load_json_any("funding_whitelist.json")
    if not rows:
        return "<p>— (keine kuratierten Einträge)</p>"
    head = "<tr><th>Programm</th><th>Region</th><th>Zielgruppe</th><th>Leistung/Status</th><th>Quelle</th></tr>"
    body = []
    for r in rows[:max_items]:
        perf = r.get("benefit","—")
        status = r.get("status","")
        if status and status not in ("aktiv","laufend","kontingentabhängig"):
            perf = f"{perf} ({status})"
        body.append(
            f"<tr><td>{r.get('name','—')}</td><td>{r.get('region','—')}</td>"
            f"<td>{r.get('target','—')}</td><td>{perf}</td><td>{r.get('source','—')}</td></tr>"
        )
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

# ---------------- Optional LLM (short, sanitized) ----------------
def _llm_html(chapter: str, ctx: Dict[str,Any], lang: str) -> str:
    if _OPENAI is None or os.getenv("ENABLE_LLM_SECTIONS","0") != "1":
        return ""
    sys_de = ("Sie sind TÜV‑zertifizierte:r KI‑Manager:in. "
              "Antwort immer als VALID HTML (<p>, <h3>) in kurzen Absätzen. "
              "Keine Anekdoten/Metaphern/'Mehr erfahren'. Keine Tool-/Förder‑Namen. "
              "Wenn Info fehlt: leer.")
    sys_en = ("You are a TÜV‑certified AI manager. "
              "Return VALID HTML (<p>, <h3>) with short paragraphs. "
              "No anecdotes/metaphors/'learn more'. No tool/funding names. "
              "If info missing: return empty.")
    sys = sys_de if lang=="de" else sys_en
    try:
        from openai import OpenAI
        client = OpenAI()
        r = client.chat.completions.create(
            model=os.getenv("GPT_MODEL_NAME","gpt-4o-mini"),
            temperature=float(os.getenv("GPT_TEMPERATURE","0.2")),
            messages=[{"role":"system","content":sys},
                      {"role":"user","content":json.dumps({"chapter":chapter, "ctx":ctx}, ensure_ascii=False)}]
        )
        html = (r.choices[0].message.content or "").strip()
        # strip lists/tables
        html = re.sub(r"</?(ul|ol|li|table|thead|tbody|tr|th|td)[^>]*>", "", html, flags=re.I)
        return _kill_story(html)
    except Exception:
        return ""

# ---------------- Context helpers ----------------
def _company(body: Dict[str,Any]) -> Dict[str,Any]:
    return {
        "name": str(body.get("company") or body.get("unternehmen") or body.get("firma") or "—"),
        "industry": str(body.get("branche") or body.get("industry") or "—"),
        "size": str(body.get("unternehmensgroesse") or body.get("company_size") or "—"),
        "location": str(body.get("bundesland") or body.get("ort") or body.get("city") or body.get("location") or "—"),
    }

def _safe_summary() -> Dict[str,List[str]]:
    return {"opportunities": [], "risks": []}

def _safe_roadmap() -> Dict[str,List[str]]:
    return {"q90": [], "q180": [], "q365": []}

# ---------------- PUBLIC: analyze_briefing (dict only) ----------------
def analyze_briefing(body: Dict[str,Any], lang: str="de") -> Dict[str,Any]:
    """Return a normalized report dict. Final HTML is rendered by file templates (ENV)."""
    if not isinstance(body, dict):
        try: body = json.loads(str(body))
        except Exception: body = {}
    lang = "de" if str(lang).lower().startswith("de") else "en"

    company = _company(body)
    meta = {
        "date": _dt.now().strftime("%d.%m.%Y") if lang=="de" else _dt.now().strftime("%Y-%m-%d"),
        "stand": _dt.now().strftime("%Y-%m-%d"),
        "year": _dt.now().year,
        "owner": "Wolf Hohl"
    }

    # Deterministic sections
    quick_wins_html = _load_partial("quick_wins_de.html" if lang=="de" else "quick_wins_en.html", "<p>—</p>")
    eu_ai_act_html  = _load_partial("eu_ai_act_de.html"  if lang=="de" else "eu_ai_act_en.html",  "<p>—</p>")
    tools_html      = render_tools_from_whitelist()
    funding_html    = render_funding_from_whitelist()

    # Optional LLM (sanitized, can be disabled)
    ctx = {"company": company, "inputs": body}
    executive_summary_html = _llm_html("executive_summary", ctx, lang)
    risks_html             = _llm_html("risks", ctx, lang)
    recommendations_html   = _llm_html("recommendations", ctx, lang)
    roadmap_html           = _llm_html("roadmap", ctx, lang)
    vision_html            = _llm_html("vision", ctx, lang)

    return {
        "company": company,
        "meta": meta,
        "summary": _safe_summary(),
        "roadmap": _safe_roadmap(),
        "quick_wins_html": quick_wins_html,
        "eu_ai_act_html": eu_ai_act_html,
        "tools_html": tools_html,
        "funding_html": funding_html,
        "executive_summary_html": executive_summary_html,
        "risks_html": risks_html,
        "recommendations_html": recommendations_html,
        "roadmap_html": roadmap_html,
        "vision_html": vision_html or ""
    }
