# gpt_analyze.py
# Gold‑Standard Analyze-Modul (async): erzeugt strukturierte Sections aus Formdaten,
# nutzt Prompts aus prompts/{lang}/..., optional Live-Layer (Tavily) und sanitizes HTML.

from __future__ import annotations
import os, asyncio, datetime as dt, re, html
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx

# -------- Konfiguration --------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # kompatibel zur /v1/chat/completions
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL", OPENAI_MODEL)
TEMPERATURE_DEFAULT = float(os.getenv("TEMPERATURE", "0.4"))

# Live-Layer (optional)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
SEARCH_DAYS = int(os.getenv("SEARCH_DAYS", "30"))
SEARCH_DEPTH = os.getenv("SEARCH_DEPTH", "basic")  # "basic" oder "advanced"

BASE_DIR = Path(__file__).parent
PROMPTS_DIR = BASE_DIR / "prompts"

# -------- Utilities --------
ALLOWED_TAGS = {"p","em","strong","b","i","u","a","br","h3","span","small","sub","sup"}
def sanitize_html(text: str) -> str:
    """Sehr konservativ: entfernt Code-Fences/Backticks, reduziert auf Absätze + erlaubte Inline-Tags."""
    if not text:
        return ""
    t = text.replace("```", " ").replace("`", " ")
    # Entferne Markdown-Listen-Start, falls LLM sie trotzdem baut
    t = re.sub(r"^\s*[-*]\s+", "", t, flags=re.MULTILINE)
    # Wrap plain text in <p> falls keine Tags vorhanden
    if "<p" not in t and "<h3" not in t:
        # Splitting in Absätze
        paras = [f"<p>{html.escape(line.strip())}</p>" for line in re.split(r"\n{2,}", t.strip()) if line.strip()]
        t = "\n".join(paras)
    # primitiver Tag-Filter: strippt alles, was nicht in ALLOWED_TAGS ist
    t = re.sub(r"</?([a-zA-Z0-9]+)(\s[^>]*)?>", lambda m: m.group(0) if m.group(1).lower() in ALLOWED_TAGS else "", t)
    # Normiere <h3 class='sub'>
    t = re.sub(r"<h3([^>]*)>", lambda m: "<h3 class='sub'>" if "class=" not in m.group(1) else f"<h3{m.group(1)}>", t)
    return t

def load_prompt(lang: str, name: str) -> str:
    p = PROMPTS_DIR / lang / f"{name}.md"
    if not p.exists():
        # Fallback: EN
        p = PROMPTS_DIR / "en" / f"{name}.md"
    return p.read_text(encoding="utf-8")

def _profile_anchors(data: Dict[str, Any]) -> Dict[str, str]:
    return {
        "branche": data.get("branche") or "—",
        "groesse": data.get("unternehmensgroesse") or data.get("company_size") or "—",
        "standort": data.get("bundesland") or data.get("state") or "—",
        "hauptleistung": data.get("hauptleistung") or data.get("main_product") or "—",
        "lang": data.get("lang") or "de",
    }

async def _openai_chat(messages: List[Dict[str,str]], model: str, temperature: float) -> str:
    if not OPENAI_API_KEY:
        return ""
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15)) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": model, "messages": messages, "temperature": temperature},
        )
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"]

async def _tavily_search(query: str, **kw) -> Dict[str, Any]:
    if not TAVILY_API_KEY:
        return {}
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": kw.get("search_depth", SEARCH_DEPTH),
        "days": kw.get("days", SEARCH_DAYS),
        "max_results": kw.get("max_results", 5),
        "include_answer": True,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(50, connect=10)) as client:
        r = await client.post("https://api.tavily.com/search", json=payload)
        if r.status_code == 200:
            return r.json()
        return {}

def _tools_table_from_live(live_tools: List[Dict[str, str]]) -> str:
    """Erzeugt kleine HTML-Tabelle (CRM/Schreiben/Automation/Project/Security) falls live_tools vorhanden; sonst generisch."""
    if not live_tools:
        # Minimaler generischer Fallback
        return (
            "<table class='tbl tools'><thead><tr>"
            "<th>Baustein</th><th>Wozu</th><th>EU‑Hinweise</th></tr></thead>"
            "<tbody>"
            "<tr><td>CRM / Kontakt‑Hub</td><td>Kundenfäden bündeln</td><td>EU‑Datenregion, Export, Rollen/Logs</td></tr>"
            "<tr><td>Schreib‑/Recherche‑Assistent</td><td>Texte, Recherche</td><td>EU‑Region, Datensparmodus</td></tr>"
            "<tr><td>Automationsschicht</td><td>Workflows</td><td>Self‑Hosting EU (z. B. n8n), Rollback</td></tr>"
            "</tbody></table>"
        )
    rows = []
    for t in live_tools[:8]:
        name = html.escape(t.get("name","Tool"))
        what = html.escape(t.get("what","—"))
        eu = html.escape(t.get("eu","EU‑Datenregion/DPA prüfen"))
        rows.append(f"<tr><td>{name}</td><td>{what}</td><td>{eu}</td></tr>")
    return "<table class='tbl tools'><thead><tr><th>Tool</th><th>Einsatz</th><th>EU‑Hinweis</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"

def _funding_table_from_live(live_funding: List[Dict[str,str]]) -> str:
    if not live_funding:
        return (
            "<table class='tbl funding'><thead><tr>"
            "<th>Pfad</th><th>Geeignet wenn</th><th>Hinweise</th></tr></thead>"
            "<tbody>"
            "<tr><td>Daten‑Grundlagen</td><td>Datenqualität verbessern</td><td>Erster Schritt für KI; DSFA prüfen</td></tr>"
            "<tr><td>Kleine Piloten</td><td>Ideen testen</td><td>KMU‑förderfreundlich; Export/Logs</td></tr>"
            "<tr><td>Qualifizierung</td><td>Team schulen</td><td>Kammern/IHK; EU‑Programme</td></tr>"
            "</tbody></table>"
        )
    rows = []
    for f in live_funding[:8]:
        path = html.escape(f.get("path","Programm"))
        when = html.escape(f.get("when","—"))
        note = html.escape(f.get("note","Fristen & Richtlinien beachten"))
        rows.append(f"<tr><td>{path}</td><td>{when}</td><td>{note}</td></tr>")
    return "<table class='tbl funding'><thead><tr><th>Pfad</th><th>Geeignet wenn</th><th>Hinweise</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"

# -------- Hauptanalyse --------

async def _live_layer(data: Dict[str,Any], lang: str) -> Dict[str, Any]:
    """Sammelt Tools/Förderungen/News (wenn Key vorhanden), mappt minimal für die Tabellen."""
    out: Dict[str,Any] = {"tools": [], "funding": [], "news": []}
    if not TAVILY_API_KEY:
        return out

    branche = data.get("branche","")
    region = data.get("bundesland","")
    queries = [
        f"{branche} EU-hosted CRM SME DPA export",
        f"{branche} open-source automation n8n EU hosting",
        f"{region} KMU Förderung Digitalisierung KI Programm offizielle Stelle",
    ]
    tasks = [ _tavily_search(q, max_results=5) for q in queries ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # sehr einfache Heuristik
    tools: List[Dict[str,str]] = []
    funding: List[Dict[str,str]] = []
    news: List[Dict[str,str]] = []

    for r in results:
        if isinstance(r, Exception) or not isinstance(r, dict):
            continue
        for item in r.get("results", []):
            url = item.get("url","")
            title = item.get("title","")
            snippet = item.get("content","") or item.get("snippet","")
            if any(k in url for k in ["crm", "hubspot", "salesforce", "centralstation", "weclapp", "odoo", "n8n", "make.com"]):
                tools.append({"name": title[:60], "what": snippet[:120], "eu":"EU‑Region/DPA prüfen"})
            if any(k in url for k in ["foerder", "förder", "bmwk", "ibb", "eif", "europa.eu", "funding", "tenders"]):
                funding.append({"path": title[:60], "when":"KMU / Digitalisierung", "note":"Offizielles Portal; Fristen beachten"})
            if r.get("answer"):
                news.append({"title": r["answer"][:140]})

    out["tools"] = tools
    out["funding"] = funding
    out["news"] = news
    return out

async def _gen_section(lang: str, name: str, profile: Dict[str,str], data: Dict[str,Any], temperature: float, model: Optional[str]=None, live: Optional[Dict[str,Any]]=None) -> str:
    sys_prompt = load_prompt(lang, name)
    # Kontext in den Nutzerdaten
    user_ctx = {
        "profile": profile,
        "data_quality": data.get("datenqualitaet") or data.get("data_quality"),
        "existing_tools": data.get("vorhandene_tools") or data.get("existing_tools"),
        "it_infrastruktur": data.get("it_infrastruktur"),
        "datenquellen": data.get("datenquellen"),
        "time_capacity": data.get("zeitbudget") or data.get("time_capacity"),
        "governance": data.get("governance") or data.get("ai_governance"),
        "lang": lang,
    }
    if live:
        user_ctx["live_tools"] = live.get("tools",[])
        user_ctx["live_funding"] = live.get("funding",[])
        user_ctx["live_news"] = live.get("news",[])

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"Kontext:\n{user_ctx}\n\nBitte liefern Sie reinen HTML‑Fließtext gemäß Vorgaben." if lang=="de" else f"Context:\n{user_ctx}\n\nPlease deliver clean HTML prose as per the prompt."}
    ]
    content = await _openai_chat(messages, model or OPENAI_MODEL, temperature)
    return sanitize_html(content)

async def analyze_briefing(data: Dict[str, Any], lang: str = "de", temperature: float = TEMPERATURE_DEFAULT) -> Dict[str, Any]:
    """Haupt‑Entry (async). Liefert {meta, sections, tables}."""
    profile = _profile_anchors(data)
    live = await _live_layer(data, lang)

    # Tabellen (system-generated, danach kommentieren die Kapitel sie)
    tools_table = _tools_table_from_live(live.get("tools", []))
    funding_table = _funding_table_from_live(live.get("funding", []))

    # Abschnitte parallel erzeugen
    # (exec_summary ggf. eigenes Modell, rest Standard)
    tasks = {
        "exec_summary": _gen_section(lang, "exec_summary", profile, data, temperature, model=EXEC_SUMMARY_MODEL, live=live),
        "quick_wins": _gen_section(lang, "quick_wins", profile, data, temperature, live=live),
        "risks": _gen_section(lang, "risks", profile, data, temperature, live=live),
        "recommendations": _gen_section(lang, "recommendations", profile, data, temperature, live=live),
        "roadmap": _gen_section(lang, "roadmap", profile, data, temperature, live=live),
        "vision": _gen_section(lang, "vision", profile, data, temperature, live=live),
        "gamechanger": _gen_section(lang, "gamechanger", profile, data, temperature, live=live),
        "compliance": _gen_section(lang, "compliance", profile, data, temperature, live=live),
        "tools": _gen_section(lang, "tools", profile, data, temperature, live=live),
        "funding": _gen_section(lang, "funding", profile, data, temperature, live=live),
        "live": _gen_section(lang, "live", profile, data, temperature, live=live),
        "trusted_check": _gen_section(lang, "trusted_check", profile, data, temperature, live=live),
    }
    results = await asyncio.gather(*tasks.values())

    # map zurück
    sections = []
    for key, html_blob in zip(tasks.keys(), results):
        title_map_de = {
            "exec_summary":"Executive Summary","quick_wins":"Sichere Sofortschritte","risks":"Risiken",
            "recommendations":"Empfehlungen","roadmap":"Roadmap","vision":"Vision",
            "gamechanger":"Gamechanger","compliance":"Compliance","tools":"Tools (EU‑Optionen)",
            "funding":"Förderprogramme (Auswahl)","live":"Neu seit 2025","trusted_check":"Trusted KI‑Check (Beilage)"
        }
        title_map_en = {
            "exec_summary":"Executive Summary","quick_wins":"Safe immediate steps","risks":"Risks",
            "recommendations":"Recommendations","roadmap":"Roadmap","vision":"Vision",
            "gamechanger":"Game‑changer","compliance":"Compliance","tools":"Tools (EU options)",
            "funding":"Funding (selected)","live":"Live updates","trusted_check":"Trusted AI check (appendix)"
        }
        title = (title_map_de if lang=="de" else title_map_en).get(key, key)
        sections.append({"id": key, "title": title, "html": html_blob})

    meta = {
        "title": "KI‑Statusbericht",
        "date": dt.date.today().isoformat(),
        "lang": lang,
        "branche": profile["branche"],
        "groesse": profile["groesse"],
        "standort": profile["standort"],
    }

    # Tabellen separat (für Templates, die sie voranstellen)
    tables = {"tools": tools_table, "funding": funding_table}
    return {"meta": meta, "sections": sections, "tables": tables}
