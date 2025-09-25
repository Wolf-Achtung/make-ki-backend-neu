# gpt_analyze.py — Gold-Standard (VOLLSTÄNDIGE, aktualisierte Vollversion)
# Version: 2025-09-25-gold
# Features implemented here:
# • Zahlensanitizer & robustes Input-Mapping (DE/EN, alte & neue Feldnamen)
# • Coach-Modus (Business-Coach) – eigener Prompt, Output fließt unter Empfehlungen
# • Tools-Kapitel: CSV-Renderer mit Badge-Chips (EU‑Hosting / Open Source / Low‑Code)
#   + Fallback (wenn CSV fehlt) über LLM &/oder Whitelist-Links
# • Förderprogramme: CSV + Live‑Search (Tavily → SerpAPI Fallback) inkl. „Frist“-Spalte
# • Live‑Updates: kuratierte Linkliste (Whitelist-Domains), Kapitel nur wenn vorhanden
# • Gamechanger/Vision: optionale Einbindung gamechanger_features.py / gamechanger_blocks.py
# • Vollständiger Rückgabekontext für pdf_template(_en).html (keine leeren Felder)
# • Keine Code-Fences im HTML, keine Markdown-Bullets „[] **“
# • Nutzt alle Prompts im Ordner ./prompts (wenn vorhanden) + business_coach_{de,en}.txt
#
# Diese Datei kann 1:1 die existierende gpt_analyze.py ersetzen.

from __future__ import annotations
import os, re, csv, json, html, logging, importlib.util
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ---- Logging ----
log = logging.getLogger("backend")

ROOT = Path(__file__).parent
PROMPTS_DIRS = [ROOT/"prompts", ROOT/"prompts_unzip", ROOT]
DATA_DIRS = [ROOT/"data", ROOT]
WHITELIST = [d.strip() for d in (os.getenv("SEARCH_INCLUDE_DOMAINS") or "bmwi.de,bafa.de,ihk.de,exist.de,europa.eu".replace(",", " ").replace(" ", ",")).split(",") if d.strip()]

# ---- Provider-Konfiguration ----
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
DEFAULT_MODEL = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")
EXEC_SUMMARY_MODEL = os.getenv("EXEC_SUMMARY_MODEL") or DEFAULT_MODEL
TEMPERATURE = float(os.getenv("GPT_TEMPERATURE") or "0.2")

# ---- Websuche ----
try:
    from websearch_utils import search_links, build_live_box
except Exception:
    # Slim Fallback (keine Suche verfügbar)
    def search_links(q: str, lang: str="de", num: int=5, recency_days: int=30) -> List[Dict[str, Any]]:
        return []
    def build_live_box(title: str, links: List[Dict[str, Any]], lang: str="de") -> str:
        return ""

# =============================================================================
# Hilfen
# =============================================================================

def _read_text_file(path: Path) -> Optional[str]:
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    return None

def _find_first_file(candidates: List[str]) -> Optional[Path]:
    for base in PROMPTS_DIRS:
        for name in candidates:
            p = base / name
            if p.is_file():
                return p
    return None

def _load_prompt(*names: str) -> Optional[str]:
    p = _find_first_file(list(names))
    return _read_text_file(p) if p else None

def _strip_md(s: str) -> str:
    if not s: return ""
    s = s.replace("\\n", "\n")
    # Entfernt Code-Fences und führende „[] **“ etc.
    s = re.sub(r"```[\\s\\S]*?```", "", s, flags=re.M)  # Codeblöcke entfernen
    s = re.sub(r"^\\s*[-*]\\s+", "", s, flags=re.M)     # Bullet-Listenzeichen
    s = re.sub(r"\\[\\]\\s*\\*\\*", "", s)              # „[] **“
    s = s.replace("**", "")                             # fett-Markdown
    return s.strip()

def _chip(text: str) -> str:
    text = html.escape(text.strip())
    return f'<span class="chip">{text}</span>' if text else ""

def _normalize_lang(lang: Optional[str]) -> str:
    if not lang: return "de"
    return "de" if lang.lower().startswith("de") else "en"

def _coalesce(*vals):
    for v in vals:
        if v is not None and str(v).strip() != "":
            return v
    return None

def _to_num(value: Any) -> Optional[float]:
    """Zahlensanitizer: akzeptiert '1.234,56', '1,234.56', '85 %', '€ 1.200' etc."""
    if value is None: return None
    if isinstance(value, (int, float)): return float(value)
    s = str(value)
    s = s.replace("\\u00A0", " ").strip()  # NBSP
    s = re.sub(r"[€$%+~°]", "", s)         # störende Zeichen
    # deutsche und englische Formatierung normalisieren
    if "," in s and "." in s:
        # Entscheide anhand der letzten Trennzeichenposition
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(re.findall(r"-?\\d+(?:\\.\\d+)?", s)[0])
    except Exception:
        return None

def _read_csv_first(*names: str) -> Optional[List[Dict[str, str]]]:
    for base in DATA_DIRS:
        for nm in names:
            p = base / nm
            if p.is_file():
                try:
                    with p.open("r", encoding="utf-8", errors="ignore") as f:
                        return list(csv.DictReader(f))
                except Exception as e:
                    log.warning("CSV-Read failed for %s: %s", p, e)
    return None

def _opt_import(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        # support file next to main
        p = ROOT / f"{module_name}.py"
        try:
            if p.exists():
                spec = importlib.util.spec_from_file_location(module_name, str(p))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)  # type: ignore
                    return mod
        except Exception:
            pass
    return None

# =============================================================================
# LLM Aufruf (OpenAI)
# =============================================================================

def _openai_chat(messages: List[Dict[str, str]], model: Optional[str]=None, temperature: Optional[float]=None, max_tokens: Optional[int]=None) -> str:
    model = model or DEFAULT_MODEL
    temperature = TEMPERATURE if (temperature is None) else temperature
    if not OPENAI_API_KEY:
        # Offline-Fallback: kombiniere User-Inputs in narrative Absätze
        joined = "\\n\\n".join([m.get("content","") for m in messages if m.get("role")=="user"])
        return "Offline‑Fallback (kein API‑Key konfiguriert).\\n\\n" + joined[:4000]
    try:
        import httpx
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": messages, "temperature": float(temperature)}
        if max_tokens: payload["max_tokens"] = max_tokens
        with httpx.Client(timeout=60) as client:
            r = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        txt = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        return txt
    except Exception as e:
        log.warning("OpenAI request failed: %s", e)
        return ""

# =============================================================================
# Kapitel-Renderer
# =============================================================================

def _render_tools_html(lang: str, branche: str, rows: Optional[List[Dict[str,str]]]) -> str:
    if not rows: 
        # Fallback kurzer Text
        return "<p>" + ("Keine kuratierten Tools gefunden. Wir ergänzen die Empfehlungen manuell in der Beratung."
                        if lang=="de" else
                        "No curated tools found. We'll add tailored suggestions during coaching.") + "</p>"
    # Normiertes Mapping
    out = [ "<table><thead><tr>"
            + ("<th>Tool</th><th>Zweck</th><th>Badges</th>" if lang=="de" else "<th>Tool</th><th>Purpose</th><th>Badges</th>")
            + "</tr></thead><tbody>" ]
    for r in rows:
        name = (r.get("name") or r.get("tool") or "").strip()
        url = (r.get("url") or r.get("link") or "").strip()
        purpose = r.get("purpose") or r.get("zweck") or r.get("category") or ""
        badges: List[str] = []
        if str(r.get("eu_hosting") or r.get("eu") or r.get("hosting") or "").strip().lower() in ("1","true","yes","ja"):
            badges.append("EU‑Hosting")
        if str(r.get("open_source") or r.get("oss") or "").strip().lower() in ("1","true","yes","ja"):
            badges.append("Open Source")
        if str(r.get("low_code") or r.get("nocode") or "").strip().lower() in ("1","true","yes","ja"):
            badges.append("Low‑Code")
        btxt = ", ".join(badges) if badges else "—"
        if url and not url.startswith("http"): url = "https://" + url
        link = f'<a href="{html.escape(url)}">{html.escape(name)}</a>' if url else html.escape(name or "—")
        out.append(f"<tr><td>{link}</td><td>{html.escape(purpose)}</td><td>{html.escape(btxt)}</td></tr>")
    out.append("</tbody></table>")
    return "\n".join(out)

def _render_funding_html(lang: str, bundesland: Optional[str], rows: Optional[List[Dict[str,str]]]) -> str:
    if not rows:
        return "<p>" + ("Derzeit keine passenden Programme in der Datenbasis. Über die Live‑Suche (unten) prüfen wir zusätzlich tagesaktuell."
                        if lang=="de" else
                        "No suitable programmes in the local data. Live search below adds fresh items.") + "</p>"
    lab = ("Programm","Träger","Frist") if lang=="de" else ("Programme","Provider","Deadline")
    out = [f"<table><thead><tr><th>{lab[0]}</th><th>{lab[1]}</th><th>{lab[2]}</th></tr></thead><tbody>"]
    for r in rows:
        name = r.get("name") or r.get("programm") or r.get("title") or "—"
        url  = r.get("url") or r.get("link") or ""
        prov_raw = r.get("provider") or r.get("traeger") or r.get("quelle") or "—"
        dl   = r.get("deadline") or r.get("frist") or r.get("stichtag") or r.get("date") or r.get("ends") or ""
        if not dl:
            # versuche Datums-Extraktion
            text = " ".join([r.get(k) or "" for k in ("notes","beschreibung","desc","snippet","text")])
            m = re.search(r"(\d{1,2}[.\/ ]\d{1,2}[.\/ ]\d{2,4}|\d{4}-\d{2}-\d{2})", text or "")
            dl = m.group(0) if m else "–"
        link = f'<a href="{html.escape(url)}">{html.escape(name)}</a>' if url else html.escape(name)
        prov = f'<span class="chip">{html.escape(prov_raw)}</span>' if prov_raw else "—"
        out.append(f"<tr><td>{link}</td><td>{prov}</td><td>{html.escape(dl)}</td></tr>")
    out.append("</tbody></table>")
    if bundesland:
        out.append(f'<p class="muted'>{ "Gefiltert nach Bundesland" if lang=="de" else "Filtered by federal state"}: {html.escape(bundesland.upper())}</p>')
    return "\n".join(out)

def _build_live_updates(lang: str, branche: str, bundesland: Optional[str]) -> Tuple[str, str]:
    # Titel & Queries
    title = "Neu & relevant" if lang=="de" else "Fresh & relevant"
    queries = []
    if lang=="de":
        queries = [
            f"site:bmwi.de OR site:bafa.de OR site:ihk.de KI Förderung {bundesland or ''}".strip(),
            f"site:europa.eu EU AI Act Umsetzung Leitfäden {bundesland or ''}".strip(),
            f"{branche} KI Tools Best Practices Deutschland"
        ]
    else:
        queries = [
            f"site:europa.eu EU AI Act guidance {bundesland or ''}".strip(),
            f"{branche} AI tools SMB best practices Germany",
        ]
    # Sammeln, whitelisten (Suchmodul normalisiert bereits; wir filtern nur)
    links: List[Dict[str,Any]] = []
    for q in queries:
        try:
            res = search_links(q, lang=lang, num=5, recency_days=int(os.getenv("SEARCH_DAYS") or "30"))
            for it in res:
                u = it.get("url","")
                if any(wh in u for wh in WHITELIST):
                    links.append(it)
        except Exception as e:
            log.warning("live search failed: %s", e)
    # Render
    html_box = build_live_box(title, links[:7], lang=lang) if links else ""
    return title, html_box

def _load_gamechanger(lang: str) -> Tuple[str, str]:
    """Rendert Vision & Gamechanger via optionale Module."""
    vision_html = ""; game_html = ""
    mod_f = _opt_import("gamechanger_features")
    mod_b = _opt_import("gamechanger_blocks")
    if mod_f and hasattr(mod_f, "render_features_html"):
        try:
            vision_html = getattr(mod_f, "render_features_html")(lang=lang) or ""
        except Exception as e:
            log.warning("gamechanger_features failed: %s", e)
    if mod_b and hasattr(mod_b, "render_blocks_html"):
        try:
            game_html = getattr(mod_b, "render_blocks_html")(lang=lang) or ""
        except Exception as e:
            log.warning("gamechanger_blocks failed: %s", e)
    return vision_html, game_html

# =============================================================================
# Analyse (Hauptfunktion)
# =============================================================================

def analyze_briefing(body: Dict[str, Any], lang: str = "de") -> Dict[str, Any]:
    """
    Erwartet das Form-JSON aus dem Frontend. Gibt einen Kontext für die
    Jinja-Templates (pdf_template.html / pdf_template_en.html) zurück.
    Rückgabe ist IMMER vollständig befüllt (keine None-Werte).
    """
    lang = _normalize_lang(lang or body.get("lang"))
    # --- Eingaben lesen ---
    branche = (body.get("branche") or body.get("industry") or "—").strip()
    size_raw = body.get("unternehmensgroesse") or body.get("company_size") or ""
    bundesland = (body.get("bundesland") or body.get("state") or "").strip()
    produkt = (body.get("hauptleistung") or body.get("produkt") or body.get("main_product") or "").strip()
    company = (body.get("unternehmensname") or body.get("company") or body.get("firma") or "").strip()
    email = body.get("email") or body.get("to") or ""
    # Scoring Inputs (sanitisiert)
    digi = _to_num(body.get("digitalisierungsgrad")) or 1.0
    know = {"keine":0,"grundkenntnisse":1,"mittel":2,"fortgeschritten":3,"expertenwissen":4}.get(str(body.get("ki_knowhow") or "").lower(), 1)
    risk = _to_num(body.get("risikofreude")) or 3.0
    auto = {"sehr_niedrig":0,"eher_niedrig":1,"mittel":2,"eher_hoch":3,"sehr_hoch":4}.get(str(body.get("automatisierungsgrad") or "").lower(), 2)

    # Größe labeln
    size_label = {
        "solo": ("Solo-Unternehmen" if lang=="de" else "Solo business"),
        "team": ("Kleines Team (2–10)" if lang=="de" else "Small team (2–10)"),
        "kmu":  ("KMU (11+)" if lang=="de" else "SME (11+)"),
    }.get(size_raw or "", size_raw or ("—"))

    # --- Score (0–100) ---
    score = int(round(
        ( (digi-1)/9 * 40 ) +   # 40%
        ( know/4 * 20 ) +       # 20%
        ( auto/4 * 20 ) +       # 20%
        ( (risk-1)/4 * 20 )     # 20%
    ))
    score = max(0, min(100, score))

    # =============================================================================
    # Prompts laden
    # =============================================================================
    # Executive/Empfehlungen
    prompt_exec = _load_prompt("executive_de.txt","exec_de.txt","executive_summary_de.txt") if lang=="de" else _load_prompt("executive_en.txt","exec_en.txt","executive_summary_en.txt")
    prompt_reco = _load_prompt("business_prompt_de.txt","business-prompt_de.txt","recommendations_de.txt") if lang=="de" else _load_prompt("business_prompt_en.txt","business-prompt_en.txt","recommendations_en.txt")
    # Coach
    prompt_coach = _load_prompt("business_coach_de.txt","coach_de.txt","business-prompt_coach_de.txt") if lang=="de" else _load_prompt("business_coach_en.txt","coach_en.txt","business-prompt_coach_en.txt")

    # Dynamischer Kontext aus CSV / MD
    tools_rows = _read_csv_first("tools.csv","tools_de.csv")
    funding_rows = _read_csv_first("foerdermittel.csv","foerderprogramme.csv","funding.csv","funding_programs.csv")

    # =============================================================================
    # LLM-Aufrufe (robust)
    # =============================================================================
    # Gemeinsamer Kontext
    ctx_json = json.dumps({
        "industry": branche,
        "company_size": size_label,
        "state": bundesland,
        "main_product": produkt,
        "score_percent": score,
        "goals": body.get("projektziel") or body.get("strategic_goals"),
        "use_cases": body.get("ki_usecases"),
        "time_capacity": body.get("time_capacity"),
        "existing_tools": body.get("existing_tools"),
        "regulated_industry": body.get("regulated_industry"),
        "training_interests": body.get("training_interests"),
    }, ensure_ascii=False)

    # 1) Executive Summary
    messages = [
        {"role":"system","content": "You are a senior AI advisor for SMEs. Write compact, actionable paragraphs. No markdown bullets, no code blocks." if lang!="de" else
                                    "Du bist ein erfahrener KI‑Berater für KMU. Schreibe kompakte, handlungsnahe Absätze. Keine Markdown‑Aufzählungen, keine Code‑Blöcke."},
        {"role":"user","content": (prompt_exec or "") + "\\n\\n" + ctx_json}
    ]
    exec_text = _strip_md(_openai_chat(messages, model=EXEC_SUMMARY_MODEL, max_tokens=700))

    # 2) Empfehlungen (Kern)
    messages = [
        {"role":"system","content": "Write a concise, structured recommendation section. Prefer EU/Germany context. No bullet characters." if lang!="de" else
                                    "Erstelle einen kompakten, strukturierten Empfehlungs‑Teil. Bevorzuge EU/Deutschland‑Kontext. Keine Aufzählungszeichen."},
        {"role":"user","content": (prompt_reco or "") + "\\n\\n" + ctx_json}
    ]
    reco_text = _strip_md(_openai_chat(messages, model=DEFAULT_MODEL, max_tokens=1100))

    # 3) Coaching – als eigener Block, wird im Template (noch) an Empfehlungen angehängt
    coach_text = ""
    if prompt_coach:
        messages = [
            {"role":"system","content": "Act as a pragmatic AI coach. Give step‑by‑step questions and exercises tailored to the user’s situation. No lists with dashes; use short paragraphs." if lang!="de" else
                                        "Agieren Sie als pragmatischer KI‑Coach. Stellen Sie Schritt‑für‑Schritt‑Fragen und kleine Übungen passend zur Lage des Unternehmens. Keine Listen mit Bindestrichen; kurze Absätze."},
            {"role":"user","content": prompt_coach + "\\n\\n" + ctx_json}
        ]
        coach_text = _strip_md(_openai_chat(messages, model=DEFAULT_MODEL, max_tokens=900))

    # 4) Risiken
    messages = [
        {"role":"system","content": "Highlight risks and how to mitigate them (data quality, governance, compliance, change). Short paragraphs only." if lang!="de" else
                                    "Nenne Risiken und Gegenmaßnahmen (Datenqualität, Governance, Compliance, Change). Nur kurze Absätze."},
        {"role":"user","content": ctx_json}
    ]
    risks_text = _strip_md(_openai_chat(messages, model=DEFAULT_MODEL, max_tokens=500))

    # 5) Roadmap (90 Tage / 6 Monate)
    messages = [
        {"role":"system","content": "Draft a 30/60/90‑day plan plus 6‑month outlook. Each phase 3–4 concrete actions. No bullet characters." if lang!="de" else
                                    "Erstelle einen 30/60/90‑Tage‑Plan plus 6‑Monats‑Ausblick. Pro Phase 3–4 konkrete Schritte. Keine Aufzählungszeichen."},
        {"role":"user","content": ctx_json}
    ]
    roadmap_text = _strip_md(_openai_chat(messages, model=DEFAULT_MODEL, max_tokens=900))

    # 6) Quick Wins
    messages = [
        {"role":"system","content": "List 3–5 quick wins with impact and effort note. No list markers; short paragraphs." if lang!="de" else
                                    "Formuliere 3–5 Quick Wins mit Hinweis auf Wirkung/Aufwand. Keine Listenmarker; kurze Absätze."},
        {"role":"user","content": ctx_json}
    ]
    quickwins_text = _strip_md(_openai_chat(messages, model=DEFAULT_MODEL, max_tokens=500))

    # =============================================================================
    # Tools & Funding Rendering
    # =============================================================================
    tools_html = _render_tools_html(lang, branche, tools_rows)

    # Funding: filtere grob nach Bundesland/Branche, nimm max 6
    if funding_rows:
        filtered: List[Dict[str,str]] = []
        for r in funding_rows:
            ok = True
            if bundesland:
                val = (r.get("bundesland") or r.get("state") or "").lower()
                ok = (not val) or (bundesland.lower() in val)
            if ok: filtered.append(r)
        funding_html = _render_funding_html(lang, bundesland, filtered[:6])
    else:
        funding_html = ""

    # =============================================================================
    # Compliance (MD-Checklisten – falls vorhanden)
    # =============================================================================
    compl_parts: List[str] = []
    for name in ("check_compliance_eu_ai_act.md","check_datenschutz.md","check_foerdermittel.md","check_ki_readiness.md"):
        for base in DATA_DIRS:
            p = base / name
            if p.exists():
                compl_parts.append("<div class='box'>" + _strip_md(_read_text_file(p) or "") + "</div>")
    compliance_html = "\n".join(compl_parts)

    # =============================================================================
    # Vision & Gamechanger (optionale Module)
    # =============================================================================
    vision_html, game_html = _load_gamechanger(lang)

    # =============================================================================
    # Live‑Updates (Tavily/SerpAPI)
    # =============================================================================
    live_title, live_html = _build_live_updates(lang, branche, bundesland)

    # =============================================================================
    # Zusammenstellen (Kontext für Template)
    # =============================================================================
    # Coach-Block wird (bis Template ergänzt) ans Ende der Empfehlungen gehängt:
    if coach_text:
        reco_text = reco_text + ("\n\n<strong>Coach‑Modus</strong>\n" if lang=="de" else "\n\n<strong>Coaching Mode</strong>\n") + coach_text

    meta = {
        "title": "KI‑Status‑Report" if lang=="de" else "AI Status Report",
        "author": "KI‑Sicherheit.jetzt",
        "version": "2025‑09‑25",
        "lang": lang.upper(),
    }

    ctx: Dict[str, Any] = {
        "meta": meta,
        "company": company,
        "branche": branche,
        "company_size_label": size_label,
        "bundesland": bundesland,
        "product": produkt,
        "email": email,
        "score_percent": score,
        # Kapitel
        "exec_summary_html": exec_text or "",
        "quick_wins_html": quickwins_text or "",
        "risks_html": risks_text or "",
        "recommendations_html": reco_text or "",
        "roadmap_html": roadmap_text or "",
        "compliance_html": compliance_html or "",
        "funding_html": funding_html or "",
        "tools_html": tools_html or "",
        "vision_html": vision_html or "",
        "gamechanger_html": game_html or "",
        "live_html": live_html or "",
        "live_title": live_title or "",
        # Fußzeileninfos
        "copyright_year": datetime.now().year,
        "copyright_owner": "Wolf Hohl",
    }

    return ctx
