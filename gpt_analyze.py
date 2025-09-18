# gpt_analyze.py — Block 1/5
import os
import csv
import json
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

# Live-Suche (Tavily/SerpAPI)
try:
    import websearch_utils as ws
except Exception:
    ws = None  # Fallback ohne Live-Layer

DATE_DE = {"months": ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]}
DATE_EN = {"months": ["January","February","March","April","May","June","July","August","September","October","November","December"]}

ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "data")
TOOLS_CSV = os.path.join(DATA_DIR, "tools.csv")
FUNDING_CSV = os.path.join(DATA_DIR, "foerderprogramme.csv")

def _month_year(lang: str="de") -> str:
    now = dt.date.today()
    if str(lang).lower().startswith("de"):
        return f"{DATE_DE['months'][now.month-1]} {now.year}"
    return f"{DATE_EN['months'][now.month-1]} {now.year}"

def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

def _get(body: Dict[str, Any], *keys: str, default: str="") -> str:
    for k in keys:
        if k in body and isinstance(body[k], str):
            v = _norm(body[k])
            if v: return v
    # in payloads vom Formbuilder: body["answers"] oder body["form"]
    answers = body.get("answers") or body.get("form") or {}
    if isinstance(answers, dict):
        for k in keys:
            for key in (k, k.upper(), k.lower(), k.capitalize()):
                v = answers.get(key)
                if isinstance(v, str) and _norm(v):
                    return _norm(v)
    return default

def _lang(body_lang: Optional[str]) -> str:
    l = (body_lang or "").lower()
    if l.startswith("en"): return "en"
    return "de"

def _read_csv(path: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    try:
        if os.path.exists(path):
            with open(path, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    out.append({k: (v or "").strip() for k, v in row.items()})
    except Exception:
        pass
    return out

def _filter_by_context(items: List[Dict[str, str]], industry: str, size: str, location: str) -> List[Dict[str, str]]:
    if not items: return []
    key_ind = industry.lower()
    key_loc = location.lower()
    key_size = size.lower()
    out = []
    for it in items:
        ok = True
        ind = (it.get("industry") or it.get("branch") or "*").lower()
        reg = (it.get("region") or "*").lower()
        siz = (it.get("company_size") or "*").lower()
        if ind != "*" and ind not in key_ind:
            ok = False
        if ok and reg != "*" and reg not in key_loc:
            ok = False
        if ok and siz != "*" and siz not in key_size:
            ok = False
        if ok:
            out.append(it)
    return out

def _mk_table_html(rows: List[Dict[str, str]], lang: str, cols: List[Tuple[str, str]]) -> str:
    if not rows: return ""
    thead = "".join([f"<th>{title}</th>" for _, title in cols])
    trs = []
    for r in rows:
        tds = []
        for k, _title in cols:
            val = (r.get(k) or "").strip()
            if k.endswith("_url") and val:
                val = f'<a href="{val}" target="_blank" rel="noopener">{val}</a>'
            tds.append(f"<td>{val}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return f"""
    <div class="table-wrap">
      <table class="compact">
        <thead><tr>{thead}</tr></thead>
        <tbody>{"".join(trs)}</tbody>
      </table>
    </div>
    """

def _narrative_for_tools(tools: List[Dict[str, str]], lang: str) -> str:
    if not tools:
        return "" if lang == "en" else ""
    parts = []
    for t in tools[:6]:
        name = t.get("name","").strip()
        use = t.get("use_case","").strip()
        price = t.get("cost_tier","").strip()
        who = t.get("target","").strip()
        one = t.get("one_liner","").strip()
        s = (f"<p><strong>{name}</strong> – {one or use}. "
             f"{'Suitable' if lang=='en' else 'Geeignet'} für {who}. "
             f"{'Cost' if lang=='en' else 'Kosten'}: {price}.</p>")
        parts.append(s)
    return "\n".join(parts)

def _narrative_for_funding(items: List[Dict[str, str]], lang: str) -> str:
    parts = []
    for it in items[:6]:
        name = it.get("name","").strip()
        who = it.get("target","").strip()
        what = it.get("what","").strip()
        region = it.get("region","").strip()
        amount = it.get("amount","").strip()
        info = it.get("info_url","").strip()
        sent = (f"<p><strong>{name}</strong> – {what}. "
                f"{'Target' if lang=='en' else 'Zielgruppe'}: {who}. "
                f"{'Region' if lang=='en' else 'Region'}: {region}. "
                f"{'Potential funding' if lang=='en' else 'Förderhöhe'}: {amount}. ")
        if info:
            sent += f'<a href="{info}" target="_blank" rel="noopener">Details</a>.'
        sent += "</p>"
        parts.append(sent)
    return "\n".join(parts)
# gpt_analyze.py — Block 2/5
def _live_box(industry: str, size: str, location: str, lang: str, topic: str) -> str:
    """
    topic: "tools" | "funding"
    """
    if ws is None:
        return ""
    q = ""
    if topic == "tools":
        q = f"{industry} AI tools best practice {location}"
    else:
        q = f"{industry} AI funding grants {location}"

    try:
        items = ws.live_snippets(
            query=q,
            days=int(os.getenv("SEARCH_DAYS", "90")),
            max_results=int(os.getenv("SEARCH_MAX_RESULTS", "5")),
            include_domains=(os.getenv("SEARCH_INCLUDE_DOMAINS") or "").split(","),
            exclude_domains=(os.getenv("SEARCH_EXCLUDE_DOMAINS") or "").split(","),
            depth=os.getenv("SEARCH_DEPTH","basic")
        )
    except Exception:
        items = []

    if not items:
        return ""
    month = _month_year(lang)
    title = f"New since {month}" if lang=="en" else f"Neu seit {month}"
    li = []
    for it in items:
        date = (it.get("date") or "").split("T")[0]
        src  = (it.get("source") or "").strip()
        url  = (it.get("url") or "").strip()
        txt  = (it.get("snippet") or "").strip()
        safe = txt.replace("<","&lt;").replace(">","&gt;")
        li.append(f'<div class="live-item"><div class="live-meta">{date} · {src}</div><a href="{url}" target="_blank" rel="noopener">{safe}</a></div>')
    return f"""
    <section class="live-box">
      <div class="live-title">{title}</div>
      {''.join(li)}
    </section>
    """

def _compliance_html(lang: str) -> str:
    if lang == "en":
        return (
            "<p><strong>Compliance first.</strong> All recommendations are designed to align with "
            "the GDPR, the ePrivacy Directive, the Digital Services Act and the EU AI Act. "
            "Data minimisation, purpose limitation, transparency and human oversight are treated as "
            "non‑negotiables. For high‑risk AI systems, document risk management, "
            "data governance and technical monitoring from day one.</p>"
        )
    return (
        "<p><strong>Compliance zuerst.</strong> Alle Empfehlungen orientieren sich an "
        "DSGVO, ePrivacy‑Richtlinie, Digital Services Act und EU‑AI‑Act. "
        "Datenminimierung, Zweckbindung, Transparenz und menschliche Aufsicht sind gesetzt. "
        "Bei Hochrisiko‑Systemen werden Risikomanagement, Datengovernance und technisches "
        "Monitoring von Beginn an dokumentiert.</p>"
    )

def _build_exec_summary(industry: str, main_offer: str, size: str, lang: str) -> str:
    if lang == "en":
        return (f"{industry} companies with a core offer around “{main_offer}” can achieve fast, "
                "visible wins by combining secure data foundations, trustworthy automation and "
                "focused pilot use‑cases. The following pages translate this into a practical sequence.")
    return (f"{industry}‑Unternehmen mit dem Schwerpunkt „{main_offer}“ erzielen schnelle, "
            "sichtbare Erfolge, wenn sichere Datenbasen, vertrauenswürdige Automatisierung "
            "und fokussierte Pilotfälle zusammenspielen. Die folgenden Seiten übersetzen das "
            "in eine machbare Abfolge.")

def _hook(industry: str, lang: str) -> str:
    if lang == "en":
        return f"Context: {industry} – tailored insights at a glance."
    return f"Kontext: {industry} – maßgeschneiderte Hinweise auf einen Blick."

def _vision_title(lang: str) -> str:
    return "Strategic Vision" if lang=="en" else "Strategische Vision"

def _gamechanger_title(lang: str) -> str:
    return "Innovation & Gamechanger" if lang=="en" else "Innovation & Gamechanger"
# gpt_analyze.py — Block 3/5
def _analysis_paragraphs(industry: str, main_offer: str, size: str, lang: str) -> Dict[str, str]:
    if lang == "en":
        return {
            "quick_wins": (
                "Start with a clean data path and one workflow where AI removes friction for your team "
                "or your clients. A small, visible success builds confidence and unlocks adoption."
            ),
            "risks": (
                "Avoid model sprawl and shadow tooling. Keep consent, provenance and auditability in sight—"
                "especially when external data is mixed into client‑facing outputs."
            ),
            "recommendations": (
                "Name one responsible owner, define acceptable use and rollout gates, and provide a safe "
                "internal sandbox. Pair each AI idea with a clear stop‑criterion."
            ),
            "roadmap": (
                "90 days: data hygiene, access and one guided pilot • 180 days: scale 2–3 pilots, governance live • "
                "12 months: platform choices, integration, training at scale."
            ),
            "vision": (
                "A practice where assistants handle the repetitive 20%, teams focus on empathy and craft, "
                "and clients feel the difference from the very first interaction."
            ),
            "gamechanger": (
                "Use retrieval‑augmented assistants connected to your own knowledge, plug in structured feedback "
                "loops, and let real‑time signals steer prioritisation."
            ),
        }
    # de
    return {
        "quick_wins": (
            "Beginnen Sie mit einer sauberen Datenstrecke und einem konkreten Ablauf, in dem KI spürbare Reibung "
            "für Team oder Kundschaft reduziert. Ein kleiner, sichtbarer Erfolg schafft Vertrauen und öffnet Türen."
        ),
        "risks": (
            "Vermeiden Sie Tool‑Wildwuchs und Schatten‑Automatisierung. Einwilligung, Herkunft und Nachvollziehbarkeit "
            "müssen jederzeit sichtbar bleiben – besonders, wenn externe Daten in kundennahe Ausgaben einfließen."
        ),
        "recommendations": (
            "Benennen Sie eine verantwortliche Person, definieren Sie zulässige Nutzung und Rollout‑Meilensteine, "
            "und stellen Sie eine sichere interne Spielwiese bereit. Jede KI‑Idee erhält ein klares Abbruchkriterium."
        ),
        "roadmap": (
            "90 Tage: Datenhygiene, Zugriffe, ein geführter Pilot • 180 Tage: 2–3 Piloten skalieren, Governance live • "
            "12 Monate: Plattform‑Entscheidungen, Integration, Training auf Breite."
        ),
        "vision": (
            "Eine Praxis, in der Assistenten die repetitiven 20 % übernehmen, Teams sich auf Empathie und Handwerk "
            "konzentrieren – und Kund:innen den Unterschied ab dem ersten Kontakt spüren."
        ),
        "gamechanger": (
            "Setzen Sie auf wissensgestützte Assistenten (RAG) mit Ihrem eigenen Wissen, schließen Sie Feedback‑Schleifen, "
            "und lassen Sie Echtzeitsignale die Prioritäten steuern."
        ),
    }

def _load_seed_and_filter(industry: str, size: str, location: str) -> Tuple[List[Dict[str,str]], List[Dict[str,str]]]:
    tools = _read_csv(TOOLS_CSV)
    funds = _read_csv(FUNDING_CSV)
    return (
        _filter_by_context(tools, industry, size, location),
        _filter_by_context(funds, industry, size, location),
    )

def _build_tools_html(industry: str, size: str, location: str, lang: str) -> str:
    tools, _ = _load_seed_and_filter(industry, size, location)
    nar = _narrative_for_tools(tools, lang)
    table = _mk_table_html(
        rows=tools[:10],
        lang=lang,
        cols=[
            ("name","Tool"),
            ("use_case","Anwendung" if lang=="de" else "Use case"),
            ("target","Zielgruppe" if lang=="de" else "Target"),
            ("cost_tier","Kosten" if lang=="de" else "Cost"),
            ("homepage_url","URL"),
        ],
    )
    live = _live_box(industry, size, location, lang, "tools")
    return nar + live + table

def _build_funding_html(industry: str, size: str, location: str, lang: str) -> str:
    _, funds = _load_seed_and_filter(industry, size, location)
    nar = _narrative_for_funding(funds, lang)
    table = _mk_table_html(
        rows=funds[:10],
        lang=lang,
        cols=[
            ("name","Programm"),
            ("what","Förderinhalt" if lang=="de" else "Scope"),
            ("target","Zielgruppe" if lang=="de" else "Target"),
            ("amount","Förderhöhe" if lang=="de" else "Amount"),
            ("info_url","Info"),
        ],
    )
    live = _live_box(industry, size, location, lang, "funding")
    return nar + live + table
# gpt_analyze.py — Block 4/5
def _extract_context(body: Dict[str, Any]) -> Dict[str, str]:
    industry = _get(body, "branche","industry","sector","Industry","Branche", default="Beratung")
    main_offer = _get(body, "hauptleistung","hauptprodukt","main_offer","main_product","Hauptleistung/Hauptprodukt", default="Beratung & Projekte")
    size = _get(body, "company_size","unternehmensgröße","size","Mitarbeitende", default="KMU")
    location = _get(body, "standort","location","country","Country","Ort", default="Deutschland")
    company = _get(body, "company","firma","Unternehmen","Company", default="")
    return {
        "industry": industry,
        "main_offer": main_offer,
        "size": size,
        "location": location,
        "company": company,
    }

def _title(lang: str) -> str:
    return "KI‑Statusbericht" if lang=="de" else "AI Readiness Report"

def _cta(lang: str) -> str:
    return "Ihre Meinung zählt: Feedback geben (kurz)" if lang=="de" else "Your opinion matters: Give feedback (short)"

def _stand_date(lang: str) -> str:
    return _month_year(lang)

def analyze_briefing(body: Dict[str, Any], lang: str="de") -> Dict[str, Any]:
    """
    Erzeugt ein Kontext-Dict für Jinja-Vorlagen (DE/EN).
    Keine ungereiften Jinja-Tags in Strings – Templates rendern den Text.
    """
    lang = _lang(lang)
    ctx = _extract_context(body)

    industry = ctx["industry"]; main_offer = ctx["main_offer"]; size = ctx["size"]; location = ctx["location"]
    paras = _analysis_paragraphs(industry, main_offer, size, lang)

    # Narrative Felder
    exec_summary = _build_exec_summary(industry, main_offer, size, lang)
    hook = _hook(industry, lang)
    comp_html = _compliance_html(lang)

    # Funding & Tools (Seeds + Live)
    funding_html = _build_funding_html(industry, size, location, lang)
    tools_html = _build_tools_html(industry, size, location, lang)

    # Vision / Gamechanger
    vision_title = _vision_title(lang)
    game_title = _gamechanger_title(lang)

    out = {
        "title": _title(lang),
        "lang": lang,
        "company": ctx["company"],
        "industry": industry,
        "main_offer": main_offer,
        "company_size": size,
        "location": location,
        "industry_hook": hook,
        "executive_summary": exec_summary,
        "quick_wins": paras["quick_wins"],
        "risks": paras["risks"],
        "recommendations": paras["recommendations"],
        "roadmap": paras["roadmap"],
        "vision_title": vision_title,
        "vision": paras["vision"],
        "game_title": game_title,
        "gamechanger": paras["gamechanger"],
        "compliance_html": comp_html,
        "funding_html": funding_html,
        "tools_html": tools_html,
        "stand_datum": _stand_date(lang),
        "footer_cta": _cta(lang),
        "report_version": "gold-std-2025-09-17",
    }
    return out
# gpt_analyze.py — Block 5/5
# Optional: einfacher Selbsttest
if __name__ == "__main__":
    sample = {
        "lang": "de",
        "branche": "Beratung",
        "hauptleistung": "Strategie & Change",
        "unternehmensgröße": "50-200",
        "standort": "Deutschland",
        "company": "Beispiel GmbH",
    }
    html_ctx = analyze_briefing(sample, lang="de")
    # Nur Kontext zeigen
    print(json.dumps({k: (v[:80]+"…" if isinstance(v,str) and len(v)>80 else v) for k,v in html_ctx.items()}, ensure_ascii=False, indent=2))
