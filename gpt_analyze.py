# gpt_analyze.py — Gold‑Standard (language folders de/en; order preserved; all prompts)
from __future__ import annotations
import os, re, json, zipfile, csv
from pathlib import Path
from datetime import datetime as _dt
from typing import Dict, Any, List, Optional

try:
    from openai import OpenAI
    _OPENAI = OpenAI()
except Exception:
    _OPENAI = None

BASE_DIR = Path(__file__).resolve().parent
PARTIAL_DIRS = [BASE_DIR / "templates" / "partials", BASE_DIR / "partials"]
PROMPTS_DIR = BASE_DIR / "prompts"
PROMPTS_DE = PROMPTS_DIR / "de"
PROMPTS_EN = PROMPTS_DIR / "en"
DATA_DIRS = [BASE_DIR / "data", BASE_DIR]

_STORY_PATTERNS = [r"\bIn\s+einem\s+kleinen\s+Familienunternehmen\b", r"\bStellen\s+Sie\s+sich\b",
                   r"\bPraxisbeispiel\b", r"\bEs\s+war\s+einmal\b", r"\bMehr\s+erfahren\b"]
_FANTASY_TOOL_PATTERNS = [r"\bIdeation\s+Assistant\b", r"\bProject\s+Harmony\b", r"\bComms\s+Connect\b",
                          r"\bPrivacyGuard\s+AI\b", r"\bSecureChat\s+AI\b", r"\bDataSafe\s+AI\b"]

def _kill_story(html: str) -> str:
    if not html: return ""
    t = re.sub(r"<[^>]+>", " ", html or "")
    for pat in _STORY_PATTERNS + _FANTASY_TOOL_PATTERNS:
        if re.search(pat, t, flags=re.IGNORECASE): return ""
    if re.search(r"%(?!\d)|€(?!\d)", t): return ""
    html = re.sub(r"</?(ul|ol|li|table|thead|tbody|tr|th|td|code|pre|blockquote)[^>]*>", "", html, flags=re.I)
    return html.strip()

def _read_text(p: Path) -> str:
    try: return p.read_text(encoding="utf-8")
    except Exception: return ""

def _load_partial(name: str, fallback="") -> str:
    for d in PARTIAL_DIRS:
        p = d / name
        if p.exists(): return _read_text(p)
    return fallback

def _list_files(dirpath: Path) -> List[Path]:
    if dirpath.exists() and dirpath.is_dir():
        return sorted([p for p in dirpath.glob("*.md") if not p.name.startswith("._")], key=lambda x: x.name)
    return []

def _load_prompt(name: str, lang: str) -> str:
    # explicit language folder preferred
    p = (PROMPTS_DE if lang=="de" else PROMPTS_EN) / name
    if p.exists(): return _read_text(p)
    # try other language
    alt = (PROMPTS_EN if lang=="de" else PROMPTS_DE) / name
    if alt.exists(): return _read_text(alt)
    # try root (legacy) or zip (legacy)
    p_legacy = PROMPTS_DIR / name
    if p_legacy.exists(): return _read_text(p_legacy)
    zf = BASE_DIR / "prompts.zip"
    if zf.exists():
        try:
            with zipfile.ZipFile(zf, "r") as z:
                if name in z.namelist():
                    with z.open(name) as f:
                        return f.read().decode("utf-8")
        except Exception:
            return ""
    return ""

def _list_appendix(lang: str) -> List[str]:
    # collect ordered names from language folder
    items = [p.name for p in _list_files(PROMPTS_DE if lang=="de" else PROMPTS_EN)]
    # remove known core names; keep order
    core = {"system.md","exec_summary.md","risks.md","recommendations.md","roadmap.md","vision.md"}
    return [n for n in items if n not in core]

def _load_json_any(name: str) -> List[Dict[str,Any]]:
    # try json files
    for d in DATA_DIRS:
        p = d / name
        if p.exists():
            try:
                data = json.loads(_read_text(p))
                if isinstance(data, list): return data
            except Exception:
                pass
    # csv fallback by stem
    stem = os.path.splitext(name)[0]
    for d in DATA_DIRS:
        p = d / f"{stem}.csv"
        if p.exists():
            with p.open("r", encoding="utf-8", errors="ignore") as f:
                return [ { (k or '').strip().lower().replace(' ','_').replace('-','_') : (v or '').strip() for k,v in row.items() if k } for row in csv.DictReader(f) ]
    # zip legacy
    zf = BASE_DIR / "data.zip"
    if zf.exists():
        try:
            with zipfile.ZipFile(zf,"r") as z:
                if name in z.namelist():
                    with z.open(name) as f:
                        data = json.loads(f.read().decode("utf-8"))
                        if isinstance(data, list): return data
                cand = f"{stem}.csv"
                for n in z.namelist():
                    if n.endswith(cand):
                        with z.open(n) as f:
                            txt = f.read().decode("utf-8","ignore").splitlines()
                        return [ { (k or '').strip().lower().replace(' ','_').replace('-','_') : (v or '').strip() for k,v in row.items() if k } for row in csv.DictReader(txt) ]
        except Exception:
            return []
    return []

def render_tools_from_whitelist(max_items: int = 16) -> str:
    rows = _load_json_any("tool_whitelist.json")
    if not rows: return "<p>— (keine kuratierten Eintr\u00E4ge)</p>"
    head_cols = ["Kategorie","Option","Daten/Deployment","Hinweise"]
    if any("as_of" in r for r in rows): head_cols.append("Stand")
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in head_cols) + "</tr>"
    body = []
    for r in rows[:max_items]:
        name = r.get("name","—")
        if str(r.get("sovereign","")).lower() in ("1","true","yes","x","ja","wahr"): 
            name += " <span class='badge'>souver\u00E4n</span>"
        cols = [r.get('category','—'), name, r.get('data_residency','—') or r.get('hosting','—'), r.get('notes','')]
        if "as_of" in r: cols.append(r.get('as_of',''))
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def render_funding_from_whitelist(max_items: int = 12, bundesland: str = "") -> str:
    rows = _load_json_any("funding_whitelist.json")
    if not rows: return "<p>— (keine kuratierten Eintr\u00E4ge)</p>"
    bundesland_norm = (bundesland or "").strip().lower()
    def _keep(r):
        reg = (r.get("region","") or "").strip().lower()
        if not bundesland_norm:
            return True
        if reg in ("bund","de","deutschland","eu","europe","europa"):
            return True
        return bundesland_norm in reg
    filtered = [r for r in rows if _keep(r)]
    head_cols = ["Programm","Region","Zielgruppe","Leistung/Status","Quelle"]
    if any("as_of" in r for r in filtered): head_cols.append("Stand")
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in head_cols) + "</tr>"
    body = []
    for r in filtered[:max_items]:
        perf = r.get("benefit","—")
        status = r.get("status","")
        if status and status not in ("aktiv","laufend","kontingentabhängig"):
            perf = f"{perf} ({status})"
        cols = [r.get('name','—'), r.get('region','—'), r.get('target','—'), perf, r.get('source','—')]
        if "as_of" in r: cols.append(r.get('as_of',''))
        body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>")
    return f"<table class='table'><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"

def _llm_html(prompt_name: str, ctx: Dict[str,Any], lang: str) -> str:
    if _OPENAI is None: return ""
    system_prompt = _load_prompt("system.md", lang) or ("Sie sind TÜV‑zertifizierte:r KI‑Manager:in. VALID HTML, 1–2 Absätze, per Sie." if lang=="de" else "You are a TÜV‑certified AI manager. VALID HTML, 1–2 paragraphs.")
    user_prompt = _load_prompt(prompt_name, lang)
    if not user_prompt: return ""
    repl = user_prompt
    for k,v in (("{{company.name}}", ctx.get("company",{}).get("name","—")),
               ("{{company.industry}}", ctx.get("company",{}).get("industry","—")),
               ("{{company.size}}", ctx.get("company",{}).get("size","—")),
               ("{{company.location}}", ctx.get("company",{}).get("location","—"))):
        repl = repl.replace(k, v)
    try:
        client = OpenAI()
        r = client.chat.completions.create(
            model=os.getenv("GPT_MODEL_NAME","gpt-4o-mini"),
            temperature=float(os.getenv("GPT_TEMPERATURE","0.2")),
            messages=[{"role":"system","content":system_prompt},
                      {"role":"user","content":repl}]
        )
        return _kill_story((r.choices[0].message.content or "").strip())
    except Exception:
        return ""

def _company(body: Dict[str,Any]) -> Dict[str,Any]:
    return {"name": str(body.get("company") or body.get("unternehmen") or body.get("firma") or "—"),
            "industry": str(body.get("branche") or body.get("industry") or "—"),
            "size": str(body.get("unternehmensgroesse") or body.get("company_size") or "—"),
            "location": str(body.get("bundesland") or body.get("ort") or body.get("city") or body.get("location") or "—")}

def analyze_briefing(body: Dict[str,Any], lang: str="de") -> Dict[str,Any]:
    if not isinstance(body, dict):
        try: body = json.loads(str(body))
        except Exception: body = {}
    lang = "de" if str(lang).lower().startswith("de") else "en"

    company = _company(body)
    meta = {"date": _dt.now().strftime("%d.%m.%Y") if lang=="de" else _dt.now().strftime("%Y-%m-%d"),
            "stand": _dt.now().strftime("%Y-%m-%d"), "year": _dt.now().year, "owner": "Wolf Hohl"}

    quick_wins_html = _load_partial("quick_wins_de.html" if lang=="de" else "quick_wins_en.html", "<p>—</p>")
    eu_ai_act_html  = _load_partial("eu_ai_act_de.html"  if lang=="de" else "eu_ai_act_en.html",  "<p>—</p>")
    tools_html      = render_tools_from_whitelist()
    funding_html    = render_funding_from_whitelist(bundesland=company.get("location",""))

    ctx = {"company": company, "inputs": body}
    # Core prompts by canonical names in language folders
    core = {
        "executive_summary_html": "exec_summary.md",
        "risks_html": "risks.md",
        "recommendations_html": "recommendations.md",
        "roadmap_html": "roadmap.md",
        "vision_html": "vision.md"
    }
    out = {}
    for key, fname in core.items():
        out[key] = _llm_html(fname, ctx, lang)

    # Appendix: every *.md in language folder except core/system, in filename order
    appendix_names = _list_appendix(lang)
    extras = []
    for name in appendix_names:
        html = _llm_html(name, ctx, lang)
        if html:
            title = os.path.splitext(name)[0].replace("_"," ").title()
            extras.append(f"<h3>{title}</h3>\n{html}")
    extras_html = _kill_story("\n".join(extras)) if extras else ""

    return {"company": company, "meta": meta,
            "quick_wins_html": quick_wins_html, "eu_ai_act_html": eu_ai_act_html,
            "tools_html": tools_html, "funding_html": funding_html,
            "executive_summary_html": out.get("executive_summary_html",""),
            "risks_html": out.get("risks_html",""),
            "recommendations_html": out.get("recommendations_html",""),
            "roadmap_html": out.get("roadmap_html",""),
            "vision_html": out.get("vision_html",""),
            "extras_html": extras_html}
