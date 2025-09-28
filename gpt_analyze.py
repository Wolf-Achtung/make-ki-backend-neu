# gpt_analyze.py — Direct Renderer + Enhanced Innenleben
# Version: 2025-09-28 (Wolf Merge)
#
# Außenhaut:
#   analyze_briefing(form_data, lang) -> str  (liefert fertiges HTML)
#   Stabiler Jinja2-Env (keine Überschreibung von built-ins wie 'default')
#   Sucht Templates in /app/templates und App-Root
#
# Innenleben:
#   KPI-Berechnung (realistisch-optimistisch), Prompts, Fallbacks
#   Sektionen: executive_summary, business, persona, quick_wins, risks,
#              recommendations, roadmap, praxisbeispiel, coach, vision,
#              gamechanger, compliance, foerderprogramme, tools
#   Narrative-Sanitizer: entfernt ul/ol/li und führende Nummern → Fließtext
#
# Hinweis:
#   OPENAI optional. Wenn kein Key vorhanden ist, werden Fallbacks genutzt.

from __future__ import annotations

import glob
import os
import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

# -----------------------------------------------------------------------------
# Basis / Pfade
# -----------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
PROMPTS_DIR = os.getenv("PROMPTS_DIR", os.path.join(BASE_DIR, "prompts"))
PDF_TEMPLATE_NAME = os.getenv("PDF_TEMPLATE_NAME", "pdf_template.html")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("gpt_analyze")

# -----------------------------------------------------------------------------
# OpenAI optional
# -----------------------------------------------------------------------------
_openai = None
try:
    from openai import OpenAI
    if os.getenv("OPENAI_API_KEY"):
        _openai = OpenAI()
        log.info("OpenAI Client initialisiert")
except Exception as e:
    log.warning(f"OpenAI nicht verfügbar: {e}")
    _openai = None

# -----------------------------------------------------------------------------
# Jinja Environment – KEIN Override built-ins!
# -----------------------------------------------------------------------------
def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader([TEMPLATE_DIR, BASE_DIR]),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # konfliktfreier Zusatzfilter
    def currency(v, symbol="€"):
        try:
            n = int(float(str(v).replace(",", ".").replace(" ", "").replace("€", "")))
        except Exception:
            n = 0
        s = f"{n:,}"
        if symbol == "€":
            s = s.replace(",", ".")
        return f"{s} {symbol}"
    env.filters["currency"] = currency
    return env

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def _safe_int(x, default=0) -> int:
    try:
        if isinstance(x, (int, float)): return int(x)
        s = re.sub(r"[^\d-]", "", str(x))
        return int(s) if s else default
    except Exception:
        return default

def _safe_float(x, default=0.0) -> float:
    try:
        if isinstance(x, (int, float)): return float(x)
        s = str(x).replace(",", ".")
        s = re.sub(r"[^\d\.-]", "", s)
        return float(s) if s and s not in {".", "-", ""} else default
    except Exception:
        return default

def _readiness_label(score: int, lang="de") -> str:
    s = _safe_int(score, 50)
    if lang.startswith("de"):
        return ("Anfänger","Grundlegend","Fortgeschritten","Reif","Führend")[
            0 if s<30 else 1 if s<50 else 2 if s<70 else 3 if s<85 else 4
        ]
    return ("Beginner","Basic","Advanced","Mature","Leading")[
        0 if s<30 else 1 if s<50 else 2 if s<70 else 3 if s<85 else 4
    ]

def _debug_list_prompts():
    try:
        files = sorted([os.path.basename(p) for p in glob.glob(os.path.join(PROMPTS_DIR, "*"))])
        log.info("PROMPTS_DIR=%s, found=%s", PROMPTS_DIR, files)
    except Exception as e:
        log.warning("Prompt listing failed: %s", e)

# -----------------------------------------------------------------------------
# KPI-Berechnung (konsolidiert)
# -----------------------------------------------------------------------------
def _budget_amount(budget_str: Any) -> int:
    if not budget_str:
        return 6000
    s = str(budget_str).lower().replace("€","").replace(" ", "").replace(".","")
    mapping = {
        "unter_2000": 1500, "unter2000": 1500,
        "2000-10000": 6000, "2.000-10.000": 6000,
        "10000-50000": 25000, "10.000-50.000": 25000,
        "ueber_50000": 75000, "ueber50000": 75000, "über50000": 75000,
    }
    for k,v in mapping.items():
        if k in s or s in k: return v
    m = re.findall(r"\d+", s)
    if m:
        val = int(m[0])
        return val*1000 if val < 100 else val
    return 6000

def calculate_kpis_from_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    digital = min(10, max(1, _safe_int(answers.get("digitalisierungsgrad", 5), 5)))
    auto_map = {'sehr_niedrig':10,'eher_niedrig':30,'mittel':50,'eher_hoch':70,'sehr_hoch':85}
    auto = auto_map.get(str(answers.get("automatisierungsgrad","mittel")).lower().replace(" ","_"), 50)
    papier_map = {'0-20':20,'21-50':40,'51-80':65,'81-100':85}
    papier = papier_map.get(str(answers.get("prozesse_papierlos","51-80")).replace("_","-"), 65)
    risk = min(5, max(1, _safe_int(answers.get("risikofreude", 3), 3)))
    kw_map = {'anfaenger':20,'anfänger':20,'grundkenntnisse':40,'fortgeschritten':70,'experte':90}
    kw = kw_map.get(str(answers.get("ki_knowhow","grundkenntnisse")).lower(), 40)

    readiness = int(digital*3.0 + (auto/10)*2.5 + (papier/10)*2.0 + (risk*2)*2.0 + (kw/10)*2.0 + 15)
    readiness = max(35, min(95, readiness))

    budget = _budget_amount(answers.get("budget","2000-10000"))
    efficiency_gap = 100 - auto
    kpi_eff = max(25, int(efficiency_gap * 0.75))
    kpi_cost = int(kpi_eff * 0.8)

    branche = str(answers.get("branche","beratung")).lower()
    branche_mult = {'beratung':1.3,'it':1.4,'marketing':1.25,'handel':1.15,'industrie':1.2,
                    'produktion':1.2,'finanzen':1.35,'gesundheit':1.1,'logistik':1.15,'bildung':1.05}.get(branche, 1.1)

    size = str(answers.get("unternehmensgroesse","2-10")).lower()
    size_cost_base = {'1':60000,'solo':60000,'2-10':300000,'11-100':3000000,'101-500':15000000}.get(size, 300000)
    base_saving = int(size_cost_base * (kpi_cost/100))
    annual_saving = max(int(base_saving * branche_mult), int(budget * 2.5))

    roi_months = max(3, min(18, int((budget/annual_saving) * 10))) if annual_saving > 0 else 12

    compliance = 40
    if answers.get("datenschutzbeauftragter") in {"ja","extern","yes"}: compliance += 30
    if answers.get("dsgvo_folgenabschaetzung") in {"ja","teilweise"}: compliance += 25
    if answers.get("eu_ai_act_kenntnis") in {"gut","sehr_gut"}: compliance += 25
    elif answers.get("eu_ai_act_kenntnis") in {"grundkenntnisse"}: compliance += 15
    compliance = max(45, min(100, compliance))

    has_inno_team = answers.get("innovationsteam") in {"ja","internes_team"}
    innovation = int(risk*18 + (kw/100)*35 + (25 if has_inno_team else 10) + (digital/10)*40)
    innovation = max(40, min(95, innovation))

    return {
        "readiness_score": readiness,
        "kpi_efficiency": kpi_eff,
        "kpi_cost_saving": kpi_cost,
        "kpi_roi_months": roi_months,
        "kpi_compliance": compliance,
        "kpi_innovation": innovation,
        "roi_investment": budget,
        "roi_annual_saving": annual_saving,
        "roi_three_year": annual_saving*3 - budget,
        "digitalisierungsgrad": digital,
        "automatisierungsgrad": auto,
        "risikofreude": risk,
    }

def calculate_optimistic_kpis(raw: Dict[str, Any]) -> Dict[str, Any]:
    k = dict(raw)
    s = k["readiness_score"]
    k["readiness_score"] = min(92, (s+10 if s<40 else s+8 if s<60 else s+5))
    e = k["kpi_efficiency"]
    k["kpi_efficiency"] = min(85, (e+15 if e<40 else e+10))
    if k["kpi_roi_months"] > 12: k["kpi_roi_months"] = max(8, k["kpi_roi_months"]-4)
    elif k["kpi_roi_months"] > 6: k["kpi_roi_months"] = max(4, k["kpi_roi_months"]-2)
    if k["roi_annual_saving"] < k["roi_investment"]*2:
        k["roi_annual_saving"] = int(k["roi_investment"]*2.5)
    else:
        k["roi_annual_saving"] = int(k["roi_annual_saving"]*1.2)
    k["roi_three_year"] = int(k["roi_annual_saving"]*3 - k["roi_investment"])
    k["kpi_innovation"] = min(90, k["kpi_innovation"]+15)
    k["kpi_compliance"] = min(85, k["kpi_compliance"])
    k["kpi_cost_saving"] = min(75, int(k["kpi_efficiency"]*0.85))
    return k

def validate_kpis(k: Dict[str, Any]) -> Dict[str, Any]:
    if k["roi_annual_saving"] > k["roi_investment"]*4:
        k["roi_annual_saving"] = int(k["roi_investment"]*4)
        k["roi_three_year"] = int(k["roi_annual_saving"]*3 - k["roi_investment"])
    if k["readiness_score"] > 85:
        k["readiness_score"] = 85
    return k

# -----------------------------------------------------------------------------
# Labels & Variablen
# -----------------------------------------------------------------------------
def get_company_size_label(size: str, lang: str) -> str:
    labels = {
        'de': {'1':'1 (Solo-Selbstständig)','solo':'1 (Solo-Selbstständig)','2-10':'2-10 (Kleines Team)',
               '11-100':'11-100 (KMU)','101-500':'101-500 (Mittelstand)','ueber_500':'Über 500 (Großunternehmen)'},
        'en': {'1':'1 (Freelancer)','solo':'1 (Freelancer)','2-10':'2-10 (Small Team)',
               '11-100':'11-100 (SME)','101-500':'101-500 (Mid-size)','ueber_500':'Over 500 (Enterprise)'}
    }
    return labels.get(lang, labels['de']).get(str(size).lower(), str(size))

def get_knowledge_label(knowledge: str, lang: str) -> str:
    labels = {
        'de': {'anfaenger':'Anfänger','grundkenntnisse':'Grundkenntnisse','fortgeschritten':'Fortgeschritten','experte':'Experte'},
        'en': {'anfaenger':'Beginner','grundkenntnisse':'Basic Knowledge','fortgeschritten':'Advanced','experte':'Expert'}
    }
    return labels.get(lang, labels['de']).get(str(knowledge).lower(), str(knowledge))

def get_readiness_level(score: int, lang: str) -> str:
    return _readiness_label(score, lang)

def get_primary_quick_win(form_data: Dict[str, Any], lang: str) -> str:
    ucs = form_data.get('ki_usecases') or []
    if isinstance(ucs, str): ucs = [ucs]
    if not ucs: return 'Prozessautomatisierung' if lang.startswith('de') else 'Process Automation'
    mapping = {
        'de': {'texterstellung':'Automatisierte Texterstellung','spracherkennung':'Meeting-Transkription',
               'prozessautomatisierung':'Workflow-Automatisierung','datenanalyse':'Automatisierte Reports',
               'kundensupport':'KI-Chatbot','wissensmanagement':'Wissensdatenbank','marketing':'Content-Automation'},
        'en': {'texterstellung':'Automated Writing','spracherkennung':'Meeting Transcription',
               'prozessautomatisierung':'Workflow Automation','datenanalyse':'Automated Reports',
               'kundensupport':'AI Chatbot','wissensmanagement':'Knowledge Base','marketing':'Content Automation'}
    }
    d = mapping.get(lang, mapping['de'])
    key = re.sub(r"[\s\-]", "", str(ucs[0]).lower())
    for k,v in d.items():
        if k in key or key in k: return v
    return d['prozessautomatisierung']

def get_template_variables(form_data: Dict[str, Any], lang: str='de') -> Dict[str, Any]:
    k = validate_kpis(calculate_optimistic_kpis(calculate_kpis_from_answers(form_data)))
    size = str(form_data.get('unternehmensgroesse','2-10'))
    vars = {
        # Zeit/Meta
        "datum": datetime.now().strftime("%d.%m.%Y"),
        "today": datetime.now().strftime("%Y-%m-%d"),
        "generation_date": datetime.now().strftime("%d.%m.%Y"),
        "copyright_year": datetime.now().year,
        "meta": {
            "title": "KI-Statusbericht & Handlungsempfehlungen" if lang.startswith("de") else "AI Status Report & Recommendations",
            "subtitle": f"AI Readiness: {k['readiness_score']}%",
            "date": datetime.now().strftime("%d.%m.%Y"),
            "lang": lang,
            "version": "3.0",
        },
        "lang": lang,
        "is_german": lang.startswith("de"),

        # Firma
        "branche": form_data.get("branche","beratung"),
        "bundesland": form_data.get("bundesland","BE"),
        "hauptleistung": form_data.get("hauptleistung",""),
        "unternehmensgroesse": size,
        "company_size_label": get_company_size_label(size, lang),

        # KPIs
        "score_percent": k["readiness_score"],
        "readiness_level": get_readiness_level(k["readiness_score"], lang),
        "kpi_efficiency": k["kpi_efficiency"],
        "kpi_cost_saving": k["kpi_cost_saving"],
        "kpi_roi_months": k["kpi_roi_months"],
        "kpi_compliance": k["kpi_compliance"],
        "kpi_innovation": k["kpi_innovation"],

        # Budget/ROI
        "budget": form_data.get("budget","2000-10000"),
        "budget_amount": k["roi_investment"],
        "roi_investment": k["roi_investment"],
        "roi_annual_saving": k["roi_annual_saving"],
        "roi_three_year": k["roi_three_year"],

        # KI-Daten
        "ki_usecases": ", ".join(map(str, form_data.get("ki_usecases", []))),
        "ki_hemmnisse": ", ".join(map(str, form_data.get("ki_hemmnisse", []))),
        "ki_knowhow": form_data.get("ki_knowhow","grundkenntnisse"),
        "ki_knowhow_label": get_knowledge_label(form_data.get("ki_knowhow","grundkenntnisse"), lang),
        "automatisierungsgrad": form_data.get("automatisierungsgrad","mittel"),
        "automatisierungsgrad_percent": k["automatisierungsgrad"],
        "prozesse_papierlos": form_data.get("prozesse_papierlos","51-80"),

        # Tabellen (optional vom Template genutzt)
        "funding_programs": form_data.get("funding_programs", []),
        "tools": form_data.get("tools", []),
        "foerderprogramme_table": form_data.get("funding_programs", []),
        "tools_table": form_data.get("tools", []),

        # Links
        "feedback_link": "https://make.ki-sicherheit.jetzt/feedback",
    }
    if vars["kpi_efficiency"] == 0:
        vars["kpi_efficiency"] = 1
    return vars

# -----------------------------------------------------------------------------
# Prompt-Engine + GPT
# -----------------------------------------------------------------------------
class PromptLoader:
    def __init__(self, directory: str = PROMPTS_DIR):
        self.dir = directory
        self.env = Environment(
            loader=FileSystemLoader([self.dir]),
            autoescape=False, trim_blocks=True, lstrip_blocks=True
        )

    def render(self, name: str, ctx: Dict[str, Any], lang: str) -> str:
        candidates = [
            f"{name}_{lang}.md",
            f"{name}.md",
            f"{name}_{lang}.jinja",
            f"{name}.jinja",
        ]
        last_err = None
        for fn in candidates:
            try:
                tpl = self.env.get_template(fn)
                return tpl.render(**ctx)
            except Exception as e:
                last_err = e
                continue
        raise FileNotFoundError(f"Prompt nicht gefunden: {name} ({last_err})")

def _gpt(prompt: str, section: str, lang="de") -> Optional[str]:
    if not _openai:
        return None
    try:
        sys = (
            "Du bist ein KI-Strategieberater. Schreibe prägnante, narrative Abschnitte "
            "in reinem HTML (<p>…</p>, optional <strong>). "
            "Keine Bullet-Listen, keine nummerierten Listen, keine Tabellen. "
            "DSGVO-konform, sachlich, handlungsorientiert."
            if lang.startswith("de") else
            "You are an AI strategy consultant. Write concise, narrative sections "
            "in plain HTML (<p>…</p>, optional <strong>). "
            "No bullet points, no numbered lists, no tables. "
            "Compliant, factual, action-oriented."
        )
        resp = _openai.chat.completions.create(
            model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
            messages=[{"role":"system","content":sys},{"role":"user","content":prompt}],
            temperature=_safe_float(os.getenv("LLM_TEMPERATURE", 0.6), 0.6),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", 1200)),
        )
        return resp.choices[0].message.content
    except Exception as e:
        log.warning(f"GPT API Fehler ({section}): {e}")
        return None

# -----------------------------------------------------------------------------
# Fallbacks & kurze Generatoren (narrativ)
# -----------------------------------------------------------------------------
def _p(s: str) -> str:
    return f"<p>{s}</p>"

def fallback_executive_summary(v: Dict[str, Any], lang="de") -> str:
    if lang.startswith("de"):
        return (
            _p(f"<strong>Ausgangslage:</strong> Mit {v.get('score_percent',50)}% KI-Reifegrad besteht eine solide Basis. "
               f"Starten Sie mit {v.get('quick_win_primary','Quick Wins')} und professionalisieren Sie Schritt für Schritt.")
            + _p(f"<strong>Wirtschaftlichkeit:</strong> Investition {v.get('roi_investment',10000)} €, "
                 f"Break-even in {v.get('kpi_roi_months',12)} Monaten, jährliche Einsparungen {v.get('roi_annual_saving',20000)} €.")
        )
    return _p("With a solid starting point, begin with pragmatic quick wins and scale responsibly.")

def fallback_business(v: Dict[str, Any], lang="de") -> str:
    if lang.startswith("de"):
        return _p(f"Konservativer Business Case: Investition {v.get('roi_investment',10000)} €, "
                  f"jährlicher Nutzen {v.get('roi_annual_saving',20000)} €, "
                  f"3-Jahres-Nettonutzen {v.get('roi_three_year',50000)} €.")
    return _p("Conservative business case with positive year-one cash-flow.")

def fallback_generic(section: str, lang="de") -> str:
    return _p("Die Inhalte dieser Sektion wurden generiert und stehen bereit.") if lang.startswith("de") \
        else _p("This section has been generated and is ready.")

def generate_quick_wins(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    primary = get_primary_quick_win(answers, lang)
    if lang.startswith("de"):
        return _p(f"Sofort starten mit <strong>{primary}</strong>; sichtbare Ergebnisse in 2–4 Wochen.")
    return _p("Start with your primary quick win; visible results in 2–4 weeks.")

def generate_risk_analysis(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    if lang.startswith("de"):
        return _p("Risikomanagement: Zuständigkeiten klären (DPO/DSFA), schrittweise Einführung, Shadow-IT vermeiden.")
    return _p("Risk management: clarify GDPR/DPIA, phased rollout, avoid shadow IT.")

def generate_roadmap(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    b = kpis.get("roi_investment", 10000)
    m = kpis.get("kpi_roi_months", 12)
    if lang.startswith("de"):
        return _p(f"Roadmap: 0–30 Tage Quick-Win (ca. {int(b*0.2)} €); 31–90 Tage Scale-Up; "
                  f"91–180 Tage Optimierung; Break-even nach ~{m} Monaten.")
    return _p("Roadmap: quick win, scale up, optimize; break-even in the first year.")

# Tools (Mini-Katalog) & Förderprogramme (Kurzliste)
TOOL_DATABASE = {
    "texterstellung": [
        {"name":"DeepL Write","desc":"DSGVO-konformes Schreibtool","use_case":"E-Mails, Berichte","cost":"Free/Pro","fit_score":95},
        {"name":"Jasper AI","desc":"Content-Automation","use_case":"Blog/Social","cost":"ab 39€","fit_score":80},
    ],
    "prozessautomatisierung": [
        {"name":"n8n","desc":"Open-Source Workflows","use_case":"APIs/Automation","cost":"Free","fit_score":92},
        {"name":"Make","desc":"Low-Code Automatisierung","use_case":"Workflows","cost":"ab 9€","fit_score":88},
    ],
    "datenanalyse": [
        {"name":"Metabase","desc":"Open-Source BI","use_case":"Dashboards","cost":"Free/Cloud","fit_score":85},
    ],
    "kundensupport": [
        {"name":"Typebot","desc":"Open-Source Chatbot","use_case":"FAQ/Leads","cost":"Free","fit_score":90},
    ],
}

def match_tools_to_company(answers: Dict[str, Any], lang: str='de') -> str:
    ucs = answers.get('ki_usecases') or []
    if isinstance(ucs, str): ucs = [ucs]
    if not ucs: ucs = ['prozessautomatisierung']
    picks = []
    used = set()
    for uc in ucs:
        key = re.sub(r"[\s\-]", "", str(uc).lower())
        for dbk, tools in TOOL_DATABASE.items():
            if dbk in key or key in dbk:
                best = sorted(tools, key=lambda t: -t.get("fit_score",0))
                for t in best:
                    if t["name"] not in used:
                        picks.append(t); used.add(t["name"]); break
                break
    if not picks:
        return _p("Individuelle Tool-Empfehlungen folgen nach Detailklärung.") if lang.startswith("de") \
               else _p("Individual tool recommendations will follow.")
    out = []
    for t in picks[:6]:
        if lang.startswith("de"):
            out.append(f"{t['name']} – {t['desc']} ({t['use_case']}, {t['cost']})")
        else:
            out.append(f"{t['name']} – {t['desc']} ({t['use_case']}, {t['cost']})")
    return _p(" ".join(out))

FUNDING_PROGRAMS = {
    "bundesweit": [
        {"name":"go-digital","amount":"bis 16.500€ (50%)","deadline":"laufend","fit":90},
        {"name":"Digital Jetzt","amount":"bis 50.000€ (40%)","deadline":"bis 31.12.2025","fit":85},
        {"name":"KfW-Digitalisierungskredit","amount":"Kredit, günstiger Zins","deadline":"laufend","fit":80},
    ],
    "berlin": [
        {"name":"Digitalprämie Berlin","amount":"bis 17.000€","deadline":"31.12.2025","fit":88},
        {"name":"Mittelstand 4.0","amount":"Beratung","deadline":"laufend","fit":100},
    ],
}

def match_funding_programs(answers: Dict[str, Any], lang: str='de') -> str:
    state = str(answers.get("bundesland","BE")).upper()
    region_map = {"BE":"berlin"}
    region = region_map.get(state)
    programs = list(FUNDING_PROGRAMS.get("bundesweit", []))
    if region and region in FUNDING_PROGRAMS:
        programs += FUNDING_PROGRAMS[region]
    programs = sorted(programs, key=lambda p: -p.get("fit",0))[:6]
    if not programs:
        return _p("Aktuell keine passenden Programme.") if lang.startswith("de") else _p("No suitable programs found.")
    rows = "; ".join([f"{p['name']} ({p['amount']})" for p in programs])
    return _p(("Förderoptionen: " + rows) if lang.startswith("de") else ("Funding options: " + rows))

# -----------------------------------------------------------------------------
# Sektionen-Renderer (Prompts → GPT → Fallback)
# -----------------------------------------------------------------------------
def _render_section(name: str, ctx: Dict[str, Any], lang="de") -> str:
    # 1) Prompt laden
    prompt = None
    try:
        prompt = PromptLoader().render(name, ctx, lang)
    except Exception as e:
        log.warning(f"Prompt-Rendering fehlgeschlagen [{name}]: {e}")
    # 2) GPT (optional)
    if prompt:
        html = _gpt(prompt, name, lang)
        if html and len(html.strip()) > 80:
            return html
    # 3) Fallback/Generator
    if name == "executive_summary": return fallback_executive_summary(ctx, lang)
    if name == "business": return fallback_business(ctx, lang)
    if name == "quick_wins": return generate_quick_wins(ctx, ctx, lang)
    if name == "risks": return generate_risk_analysis(ctx, ctx, lang)
    if name == "roadmap": return generate_roadmap(ctx, ctx, lang)
    if name == "tools": return match_tools_to_company(ctx, lang)
    if name == "foerderprogramme": return match_funding_programs(ctx, lang)
    return fallback_generic(name, lang)

# -----------------------------------------------------------------------------
# Narrative-Sanitizer (ul/ol/li → p; führende Nummern entfernen)
# -----------------------------------------------------------------------------
def _sanitize_html_block(html: str) -> str:
    if not isinstance(html, str):
        return ""
    s = html

    # 1) <li> Inhalte extrahieren → Absätze
    items = re.findall(r"<li[^>]*>(.*?)</li>", s, flags=re.I|re.S)
    if items:
        cleaned = []
        for it in items:
            txt = re.sub(r"<[^>]+>", "", it)                 # Tags entfernen
            txt = re.sub(r"^\s*(?:\d+[\.\)]|[-\*•])\s*", "", txt)  # führende Nummern/Bullets
            if txt.strip():
                cleaned.append(txt.strip())
        if cleaned:
            s = re.sub(r"</?ul[^>]*>|</?ol[^>]*>|<li[^>]*>.*?</li>", "", s, flags=re.I|re.S)
            s += "".join([f"<p>{c}</p>" for c in cleaned])

    # 2) Restliche ul/ol entfernen
    s = re.sub(r"</?(ul|ol)[^>]*>", "", s, flags=re.I)

    # 3) „1) …“ innerhalb von <p> entfernen
    s = re.sub(r"(<p[^>]*>)\s*\d+[\.\)]\s*", r"\1", s)

    # 4) Sicherstellen, dass es Absätze gibt
    if "<p" not in s.strip().lower():
        s = f"<p>{re.sub(r'<[^>]+>', '', s).strip()}</p>"

    return s

def sanitize_narrative(context: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(context)
    for k, v in list(out.items()):
        if isinstance(v, str) and k.endswith("_html"):
            out[k] = _sanitize_html_block(v)
    return out

# -----------------------------------------------------------------------------
# Innenleben-API: Kontext erzeugen (alle *_html Keys befüllen)
# -----------------------------------------------------------------------------
def analyze_briefing_enhanced(body: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    lang = "de" if str(lang).lower().startswith("de") else "en"
    vars = get_template_variables(body, lang)

    sections: List[str] = [
        "executive_summary","business","persona","quick_wins",
        "risks","recommendations","roadmap","praxisbeispiel",
        "coach","vision","gamechanger","compliance",
        "foerderprogramme","tools"
    ]

    ctx: Dict[str, Any] = dict(vars)
    for sec in sections:
        key = "exec_summary_html" if sec == "executive_summary" else f"{sec}_html"
        ctx[key] = _render_section(sec, vars, lang)

    # Falls manche Sektionen leer bleiben, mit generischen Texten auffüllen
    for aux in ["persona_html","recommendations_html","praxisbeispiel_html",
                "vision_html","gamechanger_html","coach_html","compliance_html"]:
        if not (ctx.get(aux) and len(ctx.get(aux, "").strip()) > 40):
            ctx[aux] = fallback_generic(aux[:-5] if aux.endswith("_html") else aux, lang)

    return ctx

# -----------------------------------------------------------------------------
# Außenhaut: Direct-to-HTML Renderer (stabil für Railway)
# -----------------------------------------------------------------------------
def analyze_briefing(form_data: Dict[str, Any], lang: str = "de") -> str:
    """
    Generiert vollständiges HTML (für den PDF-Service).
    """
    log.info("gpt_analyze loaded (direct): %s", os.path.join(BASE_DIR, "gpt_analyze.py"))

    # Logge verfügbare Prompts (für schnelle Ursache-Findung im Deployment)
    _debug_list_prompts()

    env = make_env()
    try:
        try:
            template = env.get_template(PDF_TEMPLATE_NAME)
        except Exception:
            html_files = [f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".html")]
            template = env.get_template(html_files[0]) if html_files else None
        if not template:
            raise RuntimeError("Kein HTML-Template gefunden")

        ctx = analyze_briefing_enhanced(form_data, lang)
        ctx = sanitize_narrative(ctx)   # → narrativer Fließtext, keine Listen

        # Notfall-Guard: zentrale Sektionen nie leer lassen
        def _minlen(x: str) -> int: return len((x or "").strip())
        for k in ["exec_summary_html","business_html","quick_wins_html","risks_html","roadmap_html"]:
            if _minlen(ctx.get(k,"")) < 80:
                title = k.replace("_html","").replace("_"," ").title()
                ctx[k] = ctx.get(k) or f"<p>Die Inhalte für <strong>{title}</strong> wurden vorbereitet.</p>"

        # Legacy-Guard: alte Keys angleichen
        if not ctx.get("quick_wins_html") and ctx.get("quickwins_html"):
            ctx["quick_wins_html"] = ctx["quickwins_html"]

        return template.render(**ctx)

    except Exception as e:
        log.error(f"Template-Rendering fehlgeschlagen: {e}")
        return (
            "<html><body><h1>KI-Statusbericht</h1>"
            "<p>Der Report wird generiert. Bitte versuchen Sie es in wenigen Minuten erneut.</p>"
            "<p>Bei anhaltenden Problemen kontaktieren Sie: kontakt@ki-sicherheit.jetzt</p>"
            "</body></html>"
        )

__all__ = ["analyze_briefing", "analyze_briefing_enhanced"]
