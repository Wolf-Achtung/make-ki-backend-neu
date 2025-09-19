# -*- coding: utf-8 -*-
"""
Gold-Standard gpt_analyze.py
- Erzählerischer Report (DE/EN), ohne Tabellenzwang
- Robuste Helper (kein harter Abbruch bei Einzelfehlern)
- Optionale Funding/Tools (CSV/HTML-Fallback)
- Optionaler Live-Layer (defensiv, kann leer bleiben)
- Liefert ein vollständiges Ergebnis-Dict; Main kann entweder
  direkt 'html' nehmen oder Template-Render via Kontext.
"""

from __future__ import annotations

import os
import re
import json
import base64
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ------------------------------------------------------------
# Konfiguration / Konstanten
# ------------------------------------------------------------
DEFAULT_LANG = "de"
MAX_FUNDING   = 6
MAX_TOOLS     = 8
MAX_LIVE_NEWS = 5

# ------------------------------------------------------------
# Hilfsfunktionen (robust, defensive)
# ------------------------------------------------------------
def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or DEFAULT_LANG).strip().lower()
    return "de" if l.startswith("de") else "en"

def _get(d: Dict[str, Any], key: str, default: Any = "") -> Any:
    v = d.get(key)
    return v if v is not None else default

def _text(d: Dict[str, Any], key: str, default: str = "") -> str:
    v = _get(d, key, default)
    if v is None:
        return default
    return str(v).strip()

def _boolish(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    s = str(x or "").strip().lower()
    return s in {"1","true","yes","ja","y","j","on"}

def _html_escape(s: str) -> str:
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def _safe_join(items: List[str], sep: str = " · ") -> str:
    return sep.join([s for s in items if s])

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

# ------------------------------------------------------------
# Static Assets → Data-URI (optional, toleriert fehlende Files)
# ------------------------------------------------------------
def _data_uri_for(filename: str) -> str:
    try:
        p = os.path.join(os.path.dirname(__file__), "assets", filename)
        if not os.path.exists(p):
            return ""
        with open(p, "rb") as f:
            b = base64.b64encode(f.read()).decode("ascii")
        # MIME minimal raten
        if filename.endswith(".svg"):
            mime = "image/svg+xml"
        elif filename.endswith(".png"):
            mime = "image/png"
        elif filename.endswith(".webp"):
            mime = "image/webp"
        else:
            mime = "application/octet-stream"
        return f"data:{mime};base64,{b}"
    except Exception:
        return ""

# ------------------------------------------------------------
# Live-Updates (defensiv: darf leer sein)
# ------------------------------------------------------------
def build_live_updates_html(data: Dict[str, Any], lang: str="de", max_results: int=MAX_LIVE_NEWS) -> Tuple[str, str]:
    """
    Placeholder/defensiver Live-Layer.
    Integriere hier Tavily/SerpAPI, wenn du möchtest. Rückgabe: (Titel, HTML)
    """
    try:
        if _boolish(_get(data, "live_layer")):
            if lang == "de":
                title = "Aktuelle Entwicklungen"
            else:
                title = "Latest Developments"
            # Hier könntest du echte Ergebnisse einhängen
            items = _get(data, "live_items", [])[:max_results]
            if not items:
                return title, ""
            li = "".join(f"<li>{_html_escape(str(x))}</li>" for x in items)
            return title, f"<ul>{li}</ul>"
        return "", ""
    except Exception:
        return "", ""

# ------------------------------------------------------------
# Compliance-Fallback (erzählerisch)
# ------------------------------------------------------------
def build_compliance_fallback(lang: str="de") -> str:
    if lang == "de":
        return (
            "<p>Berücksichtigen Sie bei der Einführung von KI-Systemen die "
            "maßgeblichen europäischen Regelwerke: DSGVO (Datenminimierung, Zweckbindung, "
            "Transparenz), ePrivacy (Einwilligungen und Endgeräte-Schutz), den Digital Services "
            "Act (Transparenz & Plattformverantwortung) sowie den EU AI Act mit seinem "
            "risikobasierten Ansatz. Etablieren Sie klare Prozesse für Datenqualität, "
            "Zugriffsrechte, Löschkonzepte und Nachvollziehbarkeit von Modellen, und führen Sie "
            "regelmäßige Audits & Schulungen durch.</p>"
        )
    else:
        return (
            "<p>When adopting AI systems, consider the key European frameworks: GDPR (data "
            "minimisation, purpose limitation, transparency), the ePrivacy rules (consent and "
            "device protection), the Digital Services Act (transparency & platform responsibility) "
            "and the EU AI Act with its risk-based approach. Establish sound processes for data "
            "quality, access control, deletion policies and model traceability, and conduct "
            "regular audits and training.</p>"
        )
# ------------------------------------------------------------
# Funding/Tools – Tabellen & Narrative
# ------------------------------------------------------------
def build_funding_table(data: Dict[str, Any], lang: str="de") -> List[Dict[str,str]]:
    """
    Erwartet optional strukturierte Einträge in data["funding_raw"].
    Fällt ansonsten auf leere Liste zurück (kein Abbruch).
    """
    try:
        rows = []
        raw = _get(data, "funding_raw", [])
        for it in (raw or []):
            rows.append({
                "name": _text(it, "name"),
                "zielgruppe": _text(it, "target" if lang!="de" else "zielgruppe"),
                "foerderhoehe": _text(it, "amount"),
                "link": _text(it, "link"),
            })
        return rows[:MAX_FUNDING]
    except Exception:
        return []

def build_tools_table(data: Dict[str, Any], branche: str="", lang: str="de") -> List[Dict[str,str]]:
    try:
        rows = []
        raw = _get(data, "tools_raw", [])
        for it in (raw or []):
            rows.append({
                "name": _text(it, "name"),
                "usecase": _text(it, "usecase"),
                "cost": _text(it, "cost"),
                "link": _text(it, "link"),
            })
        return rows[:MAX_TOOLS]
    except Exception:
        return []

def build_funding_narrative(data: Dict[str, Any], lang: str="de", max_items: int=5) -> str:
    """
    Wendelt strukturierte Förderdaten in kurze Absätze um.
    """
    try:
        table = build_funding_table(data, lang=lang)
        if not table:
            return ""
        out = []
        for r in table[:max_items]:
            if lang == "de":
                out.append(
                    f"<p><b>{_html_escape(r['name'])}</b> – Zielgruppe: "
                    f"{_html_escape(r.get('zielgruppe',''))}; mögliche Fördersumme: "
                    f"{_html_escape(r.get('foerderhoehe',''))}. "
                    f"<a href='{_html_escape(r.get('link',''))}' target='_blank' rel='noopener'>Link</a></p>"
                )
            else:
                out.append(
                    f"<p><b>{_html_escape(r['name'])}</b> – Target: "
                    f"{_html_escape(r.get('zielgruppe',''))}; possible funding: "
                    f"{_html_escape(r.get('foerderhoehe',''))}. "
                    f"<a href='{_html_escape(r.get('link',''))}' target='_blank' rel='noopener'>Link</a></p>"
                )
        return "".join(out)
    except Exception:
        return ""

def build_tools_narrative(data: Dict[str, Any], branche: str="", lang: str="de", max_items: int=6) -> str:
    try:
        table = build_tools_table(data, branche=branche, lang=lang)
        if not table:
            return ""
        out = []
        for r in table[:max_items]:
            if lang == "de":
                out.append(
                    f"<p><b>{_html_escape(r['name'])}</b> – Einsatz: "
                    f"{_html_escape(r.get('usecase',''))}; grobe Kosten: "
                    f"{_html_escape(r.get('cost',''))}. "
                    f"<a href='{_html_escape(r.get('link',''))}' target='_blank' rel='noopener'>Website</a></p>"
                )
            else:
                out.append(
                    f"<p><b>{_html_escape(r['name'])}</b> – Use case: "
                    f"{_html_escape(r.get('usecase',''))}; approx. cost: "
                    f"{_html_escape(r.get('cost',''))}. "
                    f"<a href='{_html_escape(r.get('link',''))}' target='_blank' rel='noopener'>Website</a></p>"
                )
        return "".join(out)
    except Exception:
        return ""

def build_funding_details_struct(data: Dict[str, Any], lang: str="de", max_items: int=8) -> Tuple[List[Dict[str,str]], str]:
    try:
        table = build_funding_table(data, lang=lang)[:max_items]
        stand = _now_str()
        return table, stand
    except Exception:
        return [], _now_str()

def build_tools_details_struct(data: Dict[str, Any], branche: str="", lang: str="de", max_items: int=12) -> Tuple[List[Dict[str,str]], str]:
    try:
        table = build_tools_table(data, branche=branche, lang=lang)[:max_items]
        stand = _now_str()
        return table, stand
    except Exception:
        return [], _now_str()
# ------------------------------------------------------------
# Kernanalyse (Gold-Standard)
# ------------------------------------------------------------
def analyze_briefing(payload: Dict[str, Any], lang: Optional[str]=None) -> Dict[str, Any]:
    """
    Baut den narrativen Report. Gibt ein Dict zurück, das sowohl
    'html' (direktes Render) als auch Kontextfelder (für Templates)
    enthalten kann.
    """
    lang = _norm_lang(lang or _get(payload, "lang") or _get(payload, "language"))
    company = _text(payload, "unternehmen", _text(payload, "company", "Ihr Unternehmen"))
    branche = _text(payload, "branche", _text(payload, "industry", ""))
    size    = _text(payload, "unternehmensgroesse", _text(payload, "size", ""))
    city    = _text(payload, "standort", _text(payload, "location", ""))

    # Basis-Kontext
    out: Dict[str, Any] = {
        "company": company,
        "branche": branche,
        "size": size,
        "city": city,
        "lang": lang,
        "date": _now_str(),
    }

    # Preface / Executive Summary (einfacher Narrativ-Fallback)
    if lang == "de":
        preface = (
            f"<p>Dieser Bericht fasst den aktuellen Stand zum Einsatz von KI in der Organisation "
            f"<b>{_html_escape(company)}</b> zusammen und zeigt konkrete nächste Schritte. "
            f"Branche: {_html_escape(branche or '—')} · Größe: {_html_escape(size or '—')} · "
            f"Standort: {_html_escape(city or '—')}.</p>"
        )
    else:
        preface = (
            f"<p>This report summarises the current state of AI use at "
            f"<b>{_html_escape(company)}</b> and outlines concrete next steps. "
            f"Industry: {_html_escape(branche or '—')} · Size: {_html_escape(size or '—')} · "
            f"Location: {_html_escape(city or '—')}.</p>"
        )

    free = _text(payload, "hauptleistung")
    if free:
        if lang == "de":
            preface += f"<p><b>Fokusleistung:</b> {_html_escape(free)}</p>"
        else:
            preface += f"<p><b>Main offering:</b> {_html_escape(free)}</p>"

    # Inhalte aus Payload (falls vorhanden) – ansonsten Defaulttexte
    exec_summary = _text(payload, "exec_summary", "Die wichtigsten Punkte in knapper, verständlicher Form." if lang=="de" else "Key points in a concise, accessible style.")
    quick_wins   = _text(payload, "quick_wins", "2–3 kurzfristig umsetzbare Maßnahmen mit hohem Nutzen." if lang=="de" else "2–3 short-term actions with high impact.")
    risks        = _text(payload, "risks", "Wesentliche Risiken & organisatorische Leitplanken." if lang=="de" else "Key risks and organisational guardrails.")
    recs         = _text(payload, "recommendations", "Priorisierte Empfehlungen für 90 Tage." if lang=="de" else "Prioritised 90-day recommendations.")
    roadmap      = _text(payload, "roadmap", "T30 / T90 / T365 – kurze Roadmap mit Verantwortlichkeiten." if lang=="de" else "T30 / T90 / T365 – short roadmap with ownership.")
    compliance   = _text(payload, "compliance", "")
    if not compliance:
        compliance = build_compliance_fallback(lang)

    vision       = _text(payload, "vision", "Ein inspirierendes Zielbild plus 1 Gamechanger-Idee." if lang=="de" else "An inspiring vision plus one gamechanger idea.")

    # Narrative HTML der Hauptkapitel
    if lang == "de":
        sections_html = (
            f"<h2>Executive Summary</h2><p>{_html_escape(exec_summary)}</p>"
            f"<h2>Schnelle Erfolge (Quick Wins)</h2><p>{_html_escape(quick_wins)}</p>"
            f"<h2>Risiken & Leitplanken</h2><p>{_html_escape(risks)}</p>"
            f"<h2>Empfehlungen</h2><p>{_html_escape(recs)}</p>"
            f"<h2>Roadmap</h2><p>{_html_escape(roadmap)}</p>"
            f"<h2>Compliance (DSGVO · ePrivacy · DSA · EU AI Act)</h2>{compliance}"
            f"<h2>Vision & Gamechanger</h2><p>{_html_escape(vision)}</p>"
        )
        report_title = "KI-Statusbericht"
    else:
        sections_html = (
            f"<h2>Executive Summary</h2><p>{_html_escape(exec_summary)}</p>"
            f"<h2>Quick Wins</h2><p>{_html_escape(quick_wins)}</p>"
            f"<h2>Risks & Guardrails</h2><p>{_html_escape(risks)}</p>"
            f"<h2>Recommendations</h2><p>{_html_escape(recs)}</p>"
            f"<h2>Roadmap</h2><p>{_html_escape(roadmap)}</p>"
            f"<h2>Compliance (GDPR · ePrivacy · DSA · EU AI Act)</h2>{compliance}"
            f"<h2>Vision & Gamechanger</h2><p>{_html_escape(vision)}</p>"
        )
        report_title = "AI Status Report"

    out["preface"] = preface
    out["sections_html"] = sections_html

    # --------------------------------------------------------
    # Diagramm/Score – Gold-Standard: kein Zwangs-Score
    # --------------------------------------------------------
    out["score_percent"] = None
    out["chart_data"] = {}
    out["chart_data_json"] = json.dumps(out["chart_data"], ensure_ascii=False)

    # --------------------------------------------------------
    # Tabellen (CSV)
    # (KRITISCHER BEREICH – sauberer Block, keine Dedent-Brüche)
    # --------------------------------------------------------
    try:
        out["foerderprogramme_table"] = build_funding_table(payload, lang=lang)
    except Exception:
        out["foerderprogramme_table"] = []

    try:
        out["tools_table"] = build_tools_table(payload, branche=branche, lang=lang)
    except Exception:
        out["tools_table"] = []

    # --- Narrative + Details + Live-Layer (robust) ---
    try:
        out["foerderprogramme_html"] = build_funding_narrative(payload, lang=lang, max_items=5)
        out["tools_html"]            = build_tools_narrative(payload, branche=branche, lang=lang, max_items=6)

        out["funding_details"], out["funding_stand"] = build_funding_details_struct(payload, lang=lang, max_items=8)
        out["tools_details"],   out["tools_stand"]   = build_tools_details_struct(payload, branche=branche, lang=lang, max_items=12)

        _title, _html = build_live_updates_html(payload, lang=lang, max_results=MAX_LIVE_NEWS)
        out["live_updates_title"] = _title
        out["live_updates_html"]  = _html
        out["live_box_html"]      = _html
    except Exception:
        # Defensive Defaults
        out["foerderprogramme_html"] = out.get("foerderprogramme_html","")
        out["tools_html"]            = out.get("tools_html","")
        out["funding_details"]       = out.get("funding_details", [])
        out["tools_details"]         = out.get("tools_details", [])
        out["funding_stand"]         = out.get("funding_stand") or out.get("date")
        out["tools_stand"]           = out.get("tools_stand") or out.get("date")
        out["live_updates_title"]    = out.get("live_updates_title","")
        out["live_updates_html"]     = out.get("live_updates_html","")
        out["live_box_html"]         = out.get("live_box_html","")

    # Fallbacks aus HTML, wenn CSV leer blieb
    if not out.get("foerderprogramme_table"):
        teaser = out.get("foerderprogramme_html") or out.get("sections_html","")
        rows: List[Dict[str,str]] = []
        # Sehr toleranter Regex – greift, wenn <b>Name</b> ... (Fördersumme|amount): X ... <a href="...">
        for m in re.finditer(
            r'(?:<b>)?([^<]+?)(?:</b>)?\s*(?:Fö(r|e)derh(ö|o)he|Fördersumme|amount)[:\s]*([^<]+).*?<a[^>]*href="([^"]+)"',
            teaser, re.I|re.S
        ):
            name, _, _, amount, link = m.groups()
            rows.append({
                "name": (name or "").strip(),
                "zielgruppe": "",
                "foerderhoehe": (amount or "").strip(),
                "link": link
            })
        out["foerderprogramme_table"] = rows[:MAX_FUNDING]

    if not out.get("tools_table"):
        html_tools = out.get("tools_html") or out.get("sections_html","")
        rows = []
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', html_tools, re.I):
            link, name = m.group(1), m.group(2)
            if name and link:
                rows.append({"name": name.strip(), "usecase": "", "cost": "", "link": link})
        out["tools_table"] = rows[:MAX_TOOLS]
    # --------------------------------------------------------
    # Finales HTML (direkt renderbar) – minimaler, sauberer Stil
    # --------------------------------------------------------
    title = f"{report_title} – {company}"
    intro = out.get("preface", "")
    body  = out.get("sections_html", "")
    today = out.get("date", _now_str())

    html = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{_html_escape(title)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 28px; line-height: 1.45; }}
  h1, h2 {{ margin: 0 0 10px; }}
  h1 {{ font-size: 22px; }}
  h2 {{ font-size: 18px; margin-top: 22px; }}
  p {{ margin: 8px 0; }}
  .meta {{ color:#555; font-size: 12px; margin-bottom: 12px; }}
  .sep {{ border-top: 1px solid #ddd; margin: 16px 0; }}
</style>
</head>
<body>
  <h1>{_html_escape(report_title)} – {_html_escape(company)}</h1>
  <div class="meta">{_html_escape(today)}</div>
  {intro}
  <div class="sep"></div>
  {body}
  {"<div class='sep'></div><h2>"+_html_escape(out.get('live_updates_title',''))+"</h2>"+out.get('live_box_html','') if out.get('live_box_html') else ""}
</body>
</html>"""

    # Kontext (falls Templates genutzt werden sollen)
    meta = {
        "title": report_title,
        "report_title": report_title,
        "language": lang,
        "month_year": today[:7],
        "company": company,
    }

    result = {
        "html": html,                 # Direkt nutzbar
        "meta": meta,                 # Für Template-Renderer
        "sections": {                 # Optional nach Kapiteln
            "executive_summary": exec_summary,
            "quick_wins": quick_wins,
            "risks": risks,
            "recommendations": recs,
            "roadmap": roadmap,
            "compliance": compliance,
            "vision": vision,
        },
        "score_percent": out.get("score_percent"),
        "chart_data_json": out.get("chart_data_json","{}"),
        "foerderprogramme_table": out.get("foerderprogramme_table", []),
        "foerderprogramme_html": out.get("foerderprogramme_html", ""),
        "tools_table": out.get("tools_table", []),
        "tools_html": out.get("tools_html",""),
        "dynamic_funding_html": out.get("dynamic_funding_html",""),
        "live_updates_title": out.get("live_updates_title",""),
        "live_updates_html": out.get("live_updates_html",""),
        "live_box_html": out.get("live_box_html",""),
    }
    return result
