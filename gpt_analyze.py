# -*- coding: utf-8 -*-
"""
KI-Status-Report Analyzer – Gold-Standard+ Version 2.0
Vollständige Integration mit garantierter Nutzung der kritischen Variablen:
- Branche (IMMER berücksichtigt)
- Unternehmensgröße (IMMER berücksichtigt) 
- Hauptleistung/Produkt (IMMER berücksichtigt)
- Bundesland (für Förderprogramme)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional
from pathlib import Path
from functools import lru_cache
import json, re, os, logging, httpx

# Optional hybrid search
try:
    import websearch_utils
except Exception:
    websearch_utils = None

# Source helpers
try:
    from utils_sources import classify_source, filter_and_rank
except Exception:
    def classify_source(url: str, domain: str):
        return ("web", "Web", "badge-web", 0)
    def filter_and_rank(items: List) -> List:
        return items[:10]

LOG_LEVEL = os.getenv("LOG_LEVEL","INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), 
                   format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gpt_analyze")

# Verzeichnisse
BASE_DIR = Path(os.getenv("APP_BASE") or os.getcwd()).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data").resolve()
PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR") or BASE_DIR / "prompts").resolve()
TEMPLATES_DIR = Path(os.getenv("TEMPLATE_DIR") or BASE_DIR / "templates").resolve()
CONTENT_DIR = Path(os.getenv("CONTENT_DIR") or BASE_DIR / "content").resolve()

TEMPLATE_DE = os.getenv("TEMPLATE_DE", "pdf_template.html")
TEMPLATE_EN = os.getenv("TEMPLATE_EN", "pdf_template_en.html")
ASSETS_BASE_URL = os.getenv("ASSETS_BASE_URL", "/assets")

# API Keys und Modelle
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
OPENAI_MODEL = os.getenv("OPENAI_MODEL_DEFAULT","gpt-4o")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT","45"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS","1500"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY","")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL","claude-3-5-sonnet-20241022")
ANTHROPIC_TIMEOUT = float(os.getenv("ANTHROPIC_TIMEOUT","45"))
OVERLAY_PROVIDER = os.getenv("OVERLAY_PROVIDER","auto").lower()

GPT_TEMPERATURE = float(os.getenv("GPT_TEMPERATURE","0.2"))

# Live-Daten Fenster
SEARCH_DAYS_NEWS = int(os.getenv("SEARCH_DAYS_NEWS","30"))
SEARCH_DAYS_TOOLS = int(os.getenv("SEARCH_DAYS_TOOLS","60"))
SEARCH_DAYS_FUNDING = int(os.getenv("SEARCH_DAYS_FUNDING","60"))
LIVE_MAX_ITEMS = int(os.getenv("LIVE_MAX_ITEMS","8"))

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY","")
SERPAPI_KEY = os.getenv("SERPAPI_KEY","")

ROI_BASELINE_MONTHS = float(os.getenv("ROI_BASELINE_MONTHS","4"))

# ============== HELPER FUNKTIONEN ==============

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("read failed %s: %s", path, exc)
        return ""

@lru_cache(maxsize=32)
def _template_cached(lang_key: str) -> str:
    if lang_key == "de":
        p = TEMPLATES_DIR / TEMPLATE_DE
    else:
        p = TEMPLATES_DIR / TEMPLATE_EN
    if not p.exists():
        p = TEMPLATES_DIR / "pdf_template.html"
    return _read_text(p)

def _template(lang: str) -> str:
    return _template_cached("de" if lang.lower().startswith("de") else "en")

@lru_cache(maxsize=128)
def _load_prompt_cached(lang: str, name: str) -> str:
    cand = [
        PROMPTS_DIR / lang / f"{name}_{lang}.md",
        PROMPTS_DIR / lang / f"{name}.md",
        PROMPTS_DIR / f"{name}_{lang}.md",
        PROMPTS_DIR / f"{name}.md",
    ]
    for p in cand:
        if p.exists():
            log.info("Loaded prompt: %s", p.relative_to(PROMPTS_DIR))
            return _read_text(p)
    log.info("Prompt missing for '%s' (%s) – using fallback", name, lang)
    return ""

def _as_fragment(html: str) -> str:
    if not html:
        return ""
    s = html
    s = re.sub(r"(?is)<!doctype.*?>", "", s)
    s = re.sub(r"(?is)<\s*html[^>]*>|</\s*html\s*>", "", s)
    s = re.sub(r"(?is)<\s*head[^>]*>.*?</\s*head\s*>", "", s)
    s = re.sub(r"(?is)<\s*body[^>]*>|</\s*body\s*>", "", s)
    s = re.sub(r"(?is)<\s*style[^>]*>.*?</\s*style\s*>", "", s)
    return s.strip()

def _minify_html_soft(s: str) -> str:
    if not s:
        return s
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r">\s+<", "><", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()

def _strip_llm(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"```[a-zA-Z0-9]*\s*", "", text).replace("```","")
    return text.strip()

# ============== NORMALISIERUNG & VALIDIERUNG ==============

def _parse_percent_bucket(val: Any) -> int:
    s = str(val or "").lower()
    if "81" in s: return 90
    if "61" in s: return 70
    if "41" in s: return 50
    if "21" in s: return 30
    if "0"  in s: return 10
    try:
        return int(max(0,min(100,float(s))))
    except Exception:
        return 50

@dataclass
class Normalized:
    # KRITISCHE FELDER - müssen immer vorhanden sein
    branche: str = "beratung"
    branche_label: str = "Beratung & Dienstleistungen"
    unternehmensgroesse: str = "solo"
    unternehmensgroesse_label: str = "Solo-Selbstständig"
    hauptleistung: str = "Beratung"
    bundesland_code: str = "DE-BE"
    
    # KPIs
    kpi_digitalisierung: int = 60
    kpi_automatisierung: int = 55
    kpi_compliance: int = 60
    kpi_prozessreife: int = 55
    kpi_innovation: int = 60
    
    # Zusätzliche Daten
    pull_kpis: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str,Any] = field(default_factory=dict)

def validate_and_extract_critical_fields(data: Dict[str, Any]) -> Dict[str, str]:
    """
    WICHTIG: Extrahiert und validiert die 3 kritischen Felder
    Diese MÜSSEN in jedem Report verwendet werden!
    """
    # Verschachtelte answers berücksichtigen
    if 'answers' in data and isinstance(data['answers'], dict):
        data = {**data, **data['answers']}
    
    # 1. BRANCHE (KRITISCH!)
    branche = data.get('branche') or data.get('branche_code') or data.get('industry') or "Beratung & Dienstleistungen"
    branche_label = data.get('branche_label') or branche
    
    # 2. UNTERNEHMENSGRÖSSE (KRITISCH!)
    groesse = data.get('unternehmensgroesse') or data.get('company_size') or data.get('size') or "solo"
    groesse_label = data.get('unternehmensgroesse_label') or groesse
    
    # 3. HAUPTLEISTUNG/PRODUKT (KRITISCH!)
    hauptleistung = (
        data.get('hauptleistung') or 
        data.get('main_service') or 
        data.get('produkt') or 
        data.get('product') or
        data.get('hauptdienstleistung') or
        "Nicht spezifiziert"
    )
    
    # 4. BUNDESLAND (für Förderprogramme)
    bundesland = data.get('bundesland') or data.get('state') or "Berlin"
    bundesland_code = data.get('bundesland_code') or data.get('state_code') or "DE-BE"
    
    log.info(f"KRITISCHE FELDER extrahiert: Branche={branche}, Größe={groesse}, Hauptleistung={hauptleistung[:50]}, Bundesland={bundesland_code}")
    
    return {
        "branche": branche,
        "branche_label": branche_label,
        "unternehmensgroesse": groesse,
        "unternehmensgroesse_label": groesse_label,
        "hauptleistung": hauptleistung,
        "bundesland": bundesland,
        "bundesland_code": bundesland_code
    }

def normalize_briefing(raw: Dict[str,Any], lang: str = "de") -> Normalized:
    """Normalisiert Briefing-Daten mit Fokus auf kritische Felder"""
    b: Dict[str,Any] = dict(raw or {})
    if isinstance(raw, dict) and isinstance(raw.get("answers"), dict):
        b = {**raw, **raw["answers"]}
    
    # Kritische Felder extrahieren
    critical = validate_and_extract_critical_fields(b)
    
    # KPIs berechnen
    def _derive_kpis(bb: Dict[str,Any]) -> Dict[str,int]:
        digi = _parse_percent_bucket(bb.get("digitalisierungsgrad"))
        papier = _parse_percent_bucket(bb.get("prozesse_papierlos"))
        digitalisierung = int(round(0.6*digi + 0.4*papier))
        
        auto = 70 if str(bb.get("automatisierungsgrad","")).lower() in ("eher_hoch","sehr_hoch") else 50
        if isinstance(bb.get("ki_einsatz"), list) and bb["ki_einsatz"]:
            auto = min(100, auto + 5)
        
        comp = 40
        if str(bb.get("datenschutzbeauftragter","")).lower() in ("ja","true","1"): 
            comp += 15
        if str(bb.get("folgenabschaetzung","")).lower() == "ja": 
            comp += 10
        if str(bb.get("loeschregeln","")).lower() == "ja": 
            comp += 10
        if str(bb.get("meldewege","")).lower() in ("ja","teilweise"): 
            comp += 5
        if str(bb.get("governance","")).lower() == "ja": 
            comp += 10
        comp = max(0,min(100,comp))
        
        proz = 30 + (10 if str(bb.get("governance","")).lower()=="ja" else 0) + int(0.2*papier)
        proz = max(0,min(100,proz))
        
        know = 70 if str(bb.get("ki_knowhow","")).lower()=="fortgeschritten" else 55
        inn = int(0.6*know + 0.4*65)
        
        return {
            "digitalisierung": digitalisierung,
            "automatisierung": auto,
            "compliance": comp,
            "prozessreife": proz,
            "innovation": inn
        }
    
    k = _derive_kpis(b)
    
    pull = {
        "umsatzziel": b.get("umsatzziel") or b.get("jahresumsatz") or "",
        "top_use_case": b.get("usecase_priority") or (b.get("ki_usecases") or [""])[0] if b.get("ki_usecases") else "",
        "zeitbudget": b.get("zeitbudget") or "",
    }
    
    return Normalized(
        branche=critical["branche"],
        branche_label=critical["branche_label"],
        unternehmensgroesse=critical["unternehmensgroesse"],
        unternehmensgroesse_label=critical["unternehmensgroesse_label"],
        hauptleistung=critical["hauptleistung"],
        bundesland_code=critical["bundesland_code"],
        kpi_digitalisierung=k["digitalisierung"],
        kpi_automatisierung=k["automatisierung"],
        kpi_compliance=k["compliance"],
        kpi_prozessreife=k["prozessreife"],
        kpi_innovation=k["innovation"],
        pull_kpis=pull,
        raw=b
    )

# ============== SCORING & BENCHMARKS ==============

def _load_benchmarks(branche: str, groesse: str) -> Dict[str, float]:
    """Lädt branchenspezifische Benchmarks"""
    # Versuche spezifische Benchmarks zu laden
    patterns = [
        f"benchmarks_{branche}_{groesse}",
        f"benchmarks_{branche}",
        f"benchmarks_{groesse}",
        "benchmarks_default"
    ]
    
    for base in patterns:
        p = DATA_DIR / f"{base}.json"
        if p.exists():
            try:
                data = json.loads(_read_text(p))
                log.info(f"Benchmarks geladen für {branche}/{groesse} aus {p.name}")
                return data
            except Exception as e:
                log.warning(f"Benchmark-Datei konnte nicht geladen werden: {e}")
    
    # Default Benchmarks
    return {
        "digitalisierung": 60.0,
        "automatisierung": 55.0,
        "compliance": 60.0,
        "prozessreife": 55.0,
        "innovation": 60.0
    }

@dataclass
class ScorePack:
    total: int
    badge: str
    kpis: Dict[str, Dict[str,float]]
    weights: Dict[str, float]
    benchmarks: Dict[str, float]

def compute_scores(n: Normalized) -> ScorePack:
    """Berechnet Scores mit Branchenbenchmarks"""
    weights = {
        "digitalisierung": 0.2,
        "automatisierung": 0.2,
        "compliance": 0.2,
        "prozessreife": 0.2,
        "innovation": 0.2
    }
    
    bm = _load_benchmarks(n.branche, n.unternehmensgroesse)
    
    vals = {
        "digitalisierung": n.kpi_digitalisierung,
        "automatisierung": n.kpi_automatisierung,
        "compliance": n.kpi_compliance,
        "prozessreife": n.kpi_prozessreife,
        "innovation": n.kpi_innovation
    }
    
    kpis: Dict[str, Dict[str,float]] = {}
    total = 0.0
    
    for k, v in vals.items():
        m = float(bm.get(k, 60.0))
        d = float(v) - m
        kpis[k] = {"value": float(v), "benchmark": m, "delta": d}
        total += weights[k] * float(v)
    
    t = int(round(total))
    badge = "EXCELLENT" if t >= 85 else "GOOD" if t >= 70 else "FAIR" if t >= 55 else "BASIC"
    
    return ScorePack(total=t, badge=badge, kpis=kpis, weights=weights, benchmarks=bm)

# ============== BUSINESS CASE ==============

@dataclass
class BusinessCase:
    invest_eur: float
    save_year_eur: float
    payback_months: float
    roi_year1_pct: float

def business_case(n: Normalized) -> BusinessCase:
    """Berechnet Business Case basierend auf Unternehmensgröße"""
    # Größenabhängiges Investment
    size_investments = {
        "solo": 3000.0,
        "2-10": 10000.0,
        "11-100": 50000.0,
        "100+": 100000.0
    }
    
    invest = size_investments.get(n.unternehmensgroesse, 10000.0)
    
    # Branchenspezifische Savings-Multiplikatoren
    branch_multipliers = {
        "beratung": 4.0,
        "it": 5.0,
        "handel": 3.5,
        "produktion": 6.0,
        "gesundheit": 3.0
    }
    
    multiplier = branch_multipliers.get(n.branche, 4.0)
    monthly = invest / max(1.0, ROI_BASELINE_MONTHS) * multiplier
    save_year = monthly * 12.0
    payback_m = invest / max(1.0, monthly)
    roi_y1 = (save_year - invest) / invest * 100.0
    
    return BusinessCase(
        round(invest, 2),
        round(save_year, 2),
        round(payback_m, 1),
        round(roi_y1, 1)
    )

# ============== LLM INTEGRATION ==============

def _openai_chat(messages: List[Dict[str,str]], model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    """OpenAI API Aufruf"""
    if not OPENAI_API_KEY:
        log.warning("OpenAI API Key fehlt")
        return ""
    
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model or OPENAI_MODEL,
        "messages": messages,
        "max_tokens": int(max_tokens or OPENAI_MAX_TOKENS),
        "temperature": GPT_TEMPERATURE,
        "top_p": 0.95
    }
    
    try:
        with httpx.Client(timeout=OPENAI_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return _strip_llm(content)
    except Exception as exc:
        log.warning("OpenAI call failed: %s", exc)
        return ""

def _anthropic_chat(messages: List[Dict[str,str]], model: Optional[str] = None, max_tokens: int = 1500) -> str:
    """Anthropic API Aufruf"""
    if not ANTHROPIC_API_KEY:
        return ""
    
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    sys = ""
    user_content = ""
    for m in messages:
        role = m.get("role","")
        if role == "system":
            sys = m.get("content","")
        elif role == "user":
            user_content += m.get("content","") + "\n"
    
    payload = {
        "model": model or CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": sys,
        "messages": [{"role":"user","content": user_content}]
    }
    
    try:
        with httpx.Client(timeout=ANTHROPIC_TIMEOUT) as cli:
            r = cli.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json() or {}
            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block.get("text","")
            return _strip_llm(content)
    except Exception as exc:
        log.warning("Anthropic call failed: %s", exc)
        return ""

def render_overlay(name: str, lang: str, ctx: Dict[str,Any], critical_fields: Dict[str, str]) -> str:
    """
    WICHTIG: Rendert Overlay mit GARANTIERTER Nutzung der kritischen Felder
    """
    prompt = _load_prompt_cached(lang, name)
    if not prompt:
        return ""
    
    # KRITISCHE FELDER EXTRAHIEREN
    branche = critical_fields.get("branche", "Beratung")
    groesse = critical_fields.get("unternehmensgroesse", "KMU")  
    hauptleistung = critical_fields.get("hauptleistung", "Service")
    bundesland = critical_fields.get("bundesland_code", "DE-BE")
    
    # KRITISCHE FELDER IN PROMPT EINSETZEN
    prompt = (prompt
        .replace("{{BRANCHE}}", branche)
        .replace("{{UNTERNEHMENSGROESSE}}", groesse)
        .replace("{{HAUPTLEISTUNG}}", hauptleistung)
        .replace("{{BUNDESLAND}}", bundesland)
        .replace("{{BRIEFING_JSON}}", json.dumps(ctx.get("briefing", {}), ensure_ascii=False))
        .replace("{{SCORING_JSON}}", json.dumps(ctx.get("scoring", {}), ensure_ascii=False))
        .replace("{{BENCHMARKS_JSON}}", json.dumps(ctx.get("benchmarks", {}), ensure_ascii=False))
        .replace("{{TOOLS_JSON}}", json.dumps(ctx.get("tools", []), ensure_ascii=False))
        .replace("{{FUNDING_JSON}}", json.dumps(ctx.get("funding", []), ensure_ascii=False))
        .replace("{{BUSINESS_JSON}}", json.dumps(ctx.get("business", {}), ensure_ascii=False))
        .replace("{{INDUSTRY_SNIPPET}}", ctx.get("industry_snippet", ""))
    )
    
    # SYSTEM PROMPT MIT KRITISCHEN FELDERN
    if lang.startswith("de"):
        system = f"""Du bist ein KI-Berater spezialisiert auf {branche}.
KRITISCH - Diese Parameter MÜSSEN in deiner Antwort berücksichtigt werden:
- Branche: {branche}
- Unternehmensgröße: {groesse}
- Hauptleistung: {hauptleistung}
- Region: {bundesland}

Alle Empfehlungen müssen spezifisch für {branche} und passend für {groesse} sein.
Antworte als sauberes HTML-Fragment ohne <html>/<head>/<body> Tags."""
    else:
        system = f"""You are an AI consultant specialized in {branche}.
CRITICAL - These parameters MUST be considered in your response:
- Industry: {branche}
- Company size: {groesse}
- Main service: {hauptleistung}
- Region: {bundesland}

All recommendations must be specific to {branche} and appropriate for {groesse}.
Answer as clean HTML fragment without <html>/<head>/<body> tags."""
    
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}
    ]
    
    # Provider-Auswahl
    provider = OVERLAY_PROVIDER
    if provider == "auto":
        provider = "anthropic" if ANTHROPIC_API_KEY else "openai"
    
    if provider == "anthropic":
        out = _anthropic_chat(messages, CLAUDE_MODEL if name != "executive_summary" else EXEC_SUMMARY_MODEL)
        if not out and OPENAI_API_KEY:
            out = _openai_chat(messages, OPENAI_MODEL, OPENAI_MAX_TOKENS)
    else:
        out = _openai_chat(messages, EXEC_SUMMARY_MODEL if name == "executive_summary" else OPENAI_MODEL, OPENAI_MAX_TOKENS)
        if not out and ANTHROPIC_API_KEY:
            out = _anthropic_chat(messages, CLAUDE_MODEL)
    
    return _minify_html_soft(_as_fragment(out))

# ============== LIVE-DATEN INTEGRATION ==============

def fetch_live_data(n: Normalized, lang: str = "de") -> Dict[str, List[Dict[str, Any]]]:
    """Holt Live-Daten mit Fokus auf kritische Felder"""
    news = []
    tools = []
    funding = []
    
    # Nur wenn APIs verfügbar
    if not (TAVILY_API_KEY or SERPAPI_KEY):
        log.info("Keine Live-Daten APIs konfiguriert")
        return {"news": news, "tools": tools, "funding": funding}
    
    try:
        # Tavily Integration
        if TAVILY_API_KEY:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=TAVILY_API_KEY)
            
            # Queries mit kritischen Feldern
            queries = [
                f"KI News {n.branche_label} {n.hauptleistung[:30]}",
                f"AI tools {n.branche_label} {n.unternehmensgroesse_label}",
                f"Förderprogramme {n.bundesland_code} KI Digitalisierung {n.branche_label}"
            ]
            
            for query in queries:
                try:
                    results = tavily.search(query=query, search_depth="advanced", max_results=5)
                    for r in results.get("results", []):
                        item = {
                            "title": r.get("title"),
                            "url": r.get("url"),
                            "date": r.get("published_date", ""),
                            "domain": r.get("domain", ""),
                            "score": r.get("score", 0)
                        }
                        
                        # Kategorisierung
                        if "förder" in query.lower() or "funding" in query.lower():
                            funding.append(item)
                        elif "tool" in query.lower():
                            tools.append(item)
                        else:
                            news.append(item)
                            
                except Exception as e:
                    log.warning(f"Tavily Fehler für '{query}': {e}")
        
        # SerpAPI Integration
        if SERPAPI_KEY:
            from serpapi import GoogleSearch
            
            params = {
                "api_key": SERPAPI_KEY,
                "engine": "google",
                "q": f"{n.branche_label} {n.hauptleistung} KI tools",
                "location": "Germany",
                "hl": "de",
                "gl": "de",
                "num": 10
            }
            
            search = GoogleSearch(params)
            results = search.get_dict()
            
            for r in results.get("organic_results", [])[:5]:
                tools.append({
                    "title": r.get("title"),
                    "url": r.get("link"),
                    "date": "",
                    "domain": r.get("displayed_link", ""),
                    "score": 0
                })
                
    except Exception as e:
        log.error(f"Live-Daten Fehler: {e}")
    
    log.info(f"Live-Daten gefunden: {len(news)} News, {len(tools)} Tools, {len(funding)} Förderungen")
    
    return {
        "news": news[:LIVE_MAX_ITEMS],
        "tools": tools[:LIVE_MAX_ITEMS],
        "funding": funding[:LIVE_MAX_ITEMS]
    }

# ============== HTML GENERATION ==============

def _kpi_bars_html(score: ScorePack, n: Normalized) -> str:
    """KPI Bars mit Branchenbezug"""
    order = ["digitalisierung","automatisierung","compliance","prozessreife","innovation"]
    labels = {
        "digitalisierung": "Digitalisierung",
        "automatisierung": "Automatisierung",
        "compliance": "Compliance",
        "prozessreife": "Prozessreife",
        "innovation": "Innovation"
    }
    
    rows = []
    for k in order:
        v = score.kpis[k]["value"]
        m = score.kpis[k]["benchmark"]
        d = score.kpis[k]["delta"]
        spark_class = "spark-pos" if d >= 0 else "spark-neg"
        
        # Branchenbezug im Tooltip
        tooltip = f"Branchenschnitt {n.branche_label}: {int(m)}%"
        
        rows.append(
            f'<div class="bar" title="{tooltip}">'
            f'<div class="label">{labels[k]}</div>'
            f'<div class="bar__track">'
            f'<div class="bar__fill" style="width:{max(0,min(100,int(round(v))))};"></div>'
            f'<div class="bar__median" style="left:{max(0,min(100,int(round(m))))};"></div>'
            f'</div>'
            f'<div class="bar__delta"><span class="spark {spark_class}" data-delta="{int(round(d))}"></span> '
            f'{("+" if d>=0 else "")}{int(round(d))} pp</div>'
            f'</div>'
        )
    
    return '<div class="kpi">' + "".join(rows) + '</div>'

def _profile_html(n: Normalized) -> str:
    """Unternehmensprofil mit ALLEN kritischen Feldern"""
    pl = n.pull_kpis or {}
    pills = []
    
    if pl.get("umsatzziel"):
        pills.append(f'<span class="pill">Umsatzziel: {pl["umsatzziel"]}</span>')
    if pl.get("top_use_case"):
        pills.append(f'<span class="pill">Top Use-Case: {pl["top_use_case"]}</span>')
    if pl.get("zeitbudget"):
        pills.append(f'<span class="pill">Zeitbudget: {pl["zeitbudget"]}</span>')
    
    pills_html = " ".join(pills) if pills else '<span class="muted">–</span>'
    
    return (
        '<div class="card">'
        '<h2>Unternehmensprofil & Ziele</h2>'
        f'<p><span class="hl">Hauptleistung:</span> <strong>{n.hauptleistung}</strong></p>'
        f'<p><span class="muted">Branche:</span> {n.branche_label} '
        f'<span class="muted">&middot; Größe:</span> {n.unternehmensgroesse_label} '
        f'<span class="muted">&middot; Standort:</span> {n.bundesland_code}</p>'
        f'<p>{pills_html}</p>'
        '</div>'
    )

def generate_tool_recommendations(n: Normalized) -> List[Dict[str, Any]]:
    """Generiert größen- und branchenspezifische Tool-Empfehlungen"""
    tools = []
    
    # GRÖSSENSPEZIFISCHE EMPFEHLUNGEN
    if "solo" in n.unternehmensgroesse.lower() or "1" in n.unternehmensgroesse:
        tools = [
            {"name": "Claude (Free)", "cost": "Kostenlos", "complexity": "Niedrig", "use_case": "Textgenerierung"},
            {"name": "Canva", "cost": "Kostenlos/12€", "complexity": "Niedrig", "use_case": "Design"},
            {"name": "Notion", "cost": "Kostenlos/8€", "complexity": "Niedrig", "use_case": "Projektmanagement"}
        ]
    elif "2-10" in n.unternehmensgroesse or "klein" in n.unternehmensgroesse.lower():
        tools = [
            {"name": "ChatGPT Team", "cost": "25€/User", "complexity": "Niedrig", "use_case": "Team-KI"},
            {"name": "Make.com", "cost": "Ab 9€", "complexity": "Mittel", "use_case": "Automation"},
            {"name": "Slack", "cost": "7,25€/User", "complexity": "Niedrig", "use_case": "Kommunikation"}
        ]
    else:
        tools = [
            {"name": "MS 365 Copilot", "cost": "30€/User", "complexity": "Mittel", "use_case": "Office-KI"},
            {"name": "Salesforce", "cost": "25€/User", "complexity": "Hoch", "use_case": "CRM"},
            {"name": "Power BI", "cost": "10€/User", "complexity": "Mittel", "use_case": "Analytics"}
        ]
    
    # BRANCHENSPEZIFISCHE ERGÄNZUNGEN
    if "beratung" in n.branche.lower():
        tools.append({"name": "Calendly", "cost": "Kostenlos/10€", "complexity": "Niedrig", "use_case": "Terminplanung"})
    elif "handel" in n.branche.lower():
        tools.append({"name": "Shopify", "cost": "Ab 27€", "complexity": "Mittel", "use_case": "E-Commerce"})
    elif "it" in n.branche.lower() or "software" in n.branche.lower():
        tools.append({"name": "GitHub Copilot", "cost": "10$/Monat", "complexity": "Niedrig", "use_case": "Code-Assistent"})
    
    return tools

def get_funding_programs(n: Normalized) -> List[Dict[str, Any]]:
    """Holt bundeslandspezifische Förderprogramme"""
    programs = []
    
    # Bundesweite Programme
    programs.extend([
        {
            "name": "Digital Jetzt",
            "max_funding": "50.000€",
            "eligibility": f"Perfekt für {n.unternehmensgroesse_label}",
            "url": "https://www.bmwk.de/digital-jetzt"
        },
        {
            "name": "go-digital",
            "max_funding": "16.500€",
            "eligibility": "KMU bis 100 Mitarbeiter",
            "url": "https://www.bmwk.de/go-digital"
        }
    ])
    
    # Bundeslandspezifische Programme
    if "BE" in n.bundesland_code or "Berlin" in n.bundesland_code:
        programs.append({
            "name": "Digitalprämie Berlin",
            "max_funding": "17.000€",
            "eligibility": "Berliner KMU",
            "url": "https://www.ibb.de/digitalpraemie"
        })
    elif "BY" in n.bundesland_code or "Bayern" in n.bundesland_code:
        programs.append({
            "name": "Digitalbonus Bayern",
            "max_funding": "10.000€",
            "eligibility": "Bayerische KMU",
            "url": "https://www.stmwi.bayern.de/digitalbonus"
        })
    elif "NW" in n.bundesland_code:
        programs.append({
            "name": "Mittelstand Innovativ NRW",
            "max_funding": "15.000€",
            "eligibility": "NRW KMU",
            "url": "https://www.mittelstand-innovativ.nrw"
        })
    
    return programs

# ============== HAUPTFUNKTIONEN ==============

def build_html_report(raw: Dict[str,Any], lang: str = "de") -> Dict[str,Any]:
    """
    Hauptfunktion: Erstellt vollständigen HTML-Report
    GARANTIERT Nutzung der kritischen Felder!
    """
    log.info("=== Starte Report-Generierung ===")
    
    # 1. KRITISCHE FELDER VALIDIEREN
    critical_fields = validate_and_extract_critical_fields(raw)
    
    # 2. Normalisierung mit kritischen Feldern
    n = normalize_briefing(raw, lang=lang)
    
    # 3. Scoring & Business Case
    score = compute_scores(n)
    case = business_case(n)
    
    # 4. Live-Daten abrufen (wenn APIs verfügbar)
    live_data = fetch_live_data(n, lang)
    news = live_data["news"]
    tools = live_data["tools"] or generate_tool_recommendations(n)
    funding = live_data["funding"] or get_funding_programs(n)
    
    # 5. Kontext für Overlays aufbauen
    ctx = {
        "briefing": {
            "branche": n.branche,
            "branche_label": n.branche_label,
            "unternehmensgroesse": n.unternehmensgroesse,
            "unternehmensgroesse_label": n.unternehmensgroesse_label,
            "hauptleistung": n.hauptleistung,
            "bundesland_code": n.bundesland_code,
            "pull_kpis": n.pull_kpis
        },
        "scoring": {
            "score_total": score.total,
            "badge": score.badge,
            "kpis": score.kpis,
            "weights": score.weights
        },
        "benchmarks": score.benchmarks,
        "tools": tools,
        "funding": funding,
        "business": {
            "invest_eur": case.invest_eur,
            "save_year_eur": case.save_year_eur,
            "payback_months": case.payback_months,
            "roi_year1_pct": case.roi_year1_pct
        },
        "industry_snippet": f"Spezifisch für {n.branche_label} mit Fokus auf {n.hauptleistung}"
    }
    
    # 6. Overlays mit kritischen Feldern rendern
    overlays = {}
    overlay_names = [
        "executive_summary", "quick_wins", "roadmap", "risks",
        "compliance", "business", "recommendations"
    ]
    
    for name in overlay_names:
        overlays[name] = render_overlay(name, lang, ctx, critical_fields)
    
    # 7. Template laden und befüllen
    tpl = _template(lang)
    report_date = date.today().isoformat()
    
    # 8. HTML zusammenbauen
    html = (tpl
        .replace("{{LANG}}", "de" if lang.startswith("de") else "en")
        .replace("{{ASSETS_BASE}}", ASSETS_BASE_URL)
        .replace("{{REPORT_DATE}}", report_date)
        .replace("{{PROFILE_HTML}}", _profile_html(n))
        .replace("{{KPI_BARS_HTML}}", _kpi_bars_html(score, n))
        .replace("{{EXEC_SUMMARY_HTML}}", overlays.get("executive_summary", ""))
        .replace("{{QUICK_WINS_HTML}}", overlays.get("quick_wins", ""))
        .replace("{{ROADMAP_HTML}}", overlays.get("roadmap", ""))
        .replace("{{RISKS_HTML}}", overlays.get("risks", ""))
        .replace("{{COMPLIANCE_HTML}}", overlays.get("compliance", ""))
        .replace("{{BUSINESS_CASE_HTML}}", overlays.get("business", ""))
        .replace("{{RECOMMENDATIONS_HTML}}", overlays.get("recommendations", ""))
    )
    
    # 9. Metadaten mit kritischen Feldern
    meta = {
        "score": score.total,
        "badge": score.badge,
        "date": report_date,
        "critical_fields": critical_fields,  # WICHTIG: Kritische Felder in Meta
        "branche": n.branche,
        "unternehmensgroesse": n.unternehmensgroesse,
        "hauptleistung": n.hauptleistung,
        "bundesland": n.bundesland_code,
        "kpis": score.kpis,
        "benchmarks": score.benchmarks,
        "live_data_available": bool(news or tools or funding)
    }
    
    log.info(f"=== Report generiert für {n.branche}/{n.unternehmensgroesse} ===")
    log.info(f"Score: {score.total}, Badge: {score.badge}")
    log.info(f"Kritische Felder verwendet: {critical_fields}")
    
    return {
        "html": html,
        "meta": meta,
        "normalized": n.__dict__,
        "raw": raw
    }

def analyze_briefing(raw: Dict[str,Any], lang: str = "de") -> str:
    """Wrapper für Kompatibilität - gibt nur HTML zurück"""
    return build_html_report(raw, lang)["html"]

def build_report(raw: Dict[str,Any], lang: str = "de") -> Dict[str,Any]:
    """Alias für build_html_report"""
    return build_html_report(raw, lang)

# Für Debugging
def analyze_briefing_enhanced(raw: Dict[str,Any], lang: str = "de", *, as_dict: bool = False):
    """Legacy-kompatibler Wrapper"""
    result = build_html_report(raw, lang)
    return result if as_dict else result["html"]

# ============== EXPORTS ==============

__all__ = [
    "analyze_briefing",
    "build_report", 
    "build_html_report",
    "normalize_briefing",
    "compute_scores",
    "business_case",
    "validate_and_extract_critical_fields"
]

if __name__ == "__main__":
    # Test mit kritischen Feldern
    test_data = {
        "branche": "Beratung & Dienstleistungen",
        "unternehmensgroesse": "2-10 (Kleines Team)",
        "hauptleistung": "KI-Beratung für Mittelstand",
        "bundesland": "Berlin",
        "bundesland_code": "DE-BE",
        "digitalisierungsgrad": "61-80%",
        "automatisierungsgrad": "eher_hoch"
    }
    
    result = build_report(test_data)
    print(f"Report generiert: {len(result['html'])} Zeichen")
    print(f"Kritische Felder: {result['meta']['critical_fields']}")
    print(f"Score: {result['meta']['score']}, Badge: {result['meta']['badge']}")