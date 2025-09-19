"""
Minimal but robust gpt_analyze module providing analyze_briefing(payload, lang).
This version avoids external dependencies and returns a fully-rendered HTML string
so the caller does not depend on Jinja templates for successful PDF generation.
"""

from typing import Dict, Any, Optional
from datetime import datetime

def _norm_lang(lang: Optional[str]) -> str:
    l = (lang or "de").lower().strip()
    return "de" if l.startswith("de") else "en"

def _val(d: Dict[str, Any], key: str, default: str = "") -> str:
    v = d.get(key)
    return str(v).strip() if v is not None else default

def analyze_briefing(payload: Dict[str, Any], lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns a dict with an 'html' field (fully rendered narrative report).
    This keeps the pipeline resilient even if templates are missing/misaligned.
    """
    lang = _norm_lang(lang or payload.get("lang") or payload.get("language"))
    company = _val(payload, "unternehmen", _val(payload, "company", "Ihr Unternehmen"))
    branche = _val(payload, "branche", _val(payload, "industry", ""))
    size    = _val(payload, "unternehmensgroesse", _val(payload, "size", ""))
    city    = _val(payload, "standort", _val(payload, "location", ""))

    title_de = "KI-Statusbericht"
    title_en = "AI Status Report"
    title = title_de if lang == "de" else title_en
    today = datetime.now().strftime("%Y-%m-%d")

    if lang == "de":
        intro = (f"<p>Dieser Bericht fasst den aktuellen Stand zum Einsatz von KI in der "
                 f"Organisation <b>{company}</b> zusammen und zeigt konkrete nächste Schritte. "
                 f"Branche: {branche or '—'} · Größe: {size or '—'} · Standort: {city or '—'}.</p>")
        exec_summary_h = "Executive Summary"
        quick_h = "Schnelle Erfolge (Quick Wins)"
        risk_h  = "Risiken & Leitplanken"
        rec_h   = "Empfehlungen"
        roadmap_h = "Roadmap"
        compliance_h = "Compliance (DSGVO · ePrivacy · DSA · EU AI Act)"
        vision_h = "Vision & Gamechanger"
    else:
        intro = (f"<p>This report summarises the current state of AI use at "
                 f"<b>{company}</b> and outlines concrete next steps. "
                 f"Industry: {branche or '—'} · Size: {size or '—'} · Location: {city or '—'}.</p>")
        exec_summary_h = "Executive Summary"
        quick_h = "Quick Wins"
        risk_h  = "Risks & Guardrails"
        rec_h   = "Recommendations"
        roadmap_h = "Roadmap"
        compliance_h = "Compliance (GDPR · ePrivacy · DSA · EU AI Act)"
        vision_h = "Vision & Gamechanger"

    free = _val(payload, "hauptleistung", "")
    if free:
        if lang == "de":
            intro += f"<p><b>Fokusleistung:</b> {free}</p>"
        else:
            intro += f"<p><b>Main offering:</b> {free}</p>"

    html = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{title} · {company}</title>
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
  <h1>{title} – {company}</h1>
  <div class="meta">{today}</div>
  {intro}
  <div class="sep"></div>

  <h2>{exec_summary_h}</h2>
  <p>{_val(payload, "exec_summary", "Die wichtigsten Punkte in knapper, verständlicher Form.").replace("<","&lt;")}</p>

  <h2>{quick_h}</h2>
  <p>{_val(payload, "quick_wins", "2–3 kurzfristig umsetzbare Maßnahmen mit hohem Nutzen.").replace("<","&lt;")}</p>

  <h2>{risk_h}</h2>
  <p>{_val(payload, "risks", "Wesentliche Risiken & organisatorische Leitplanken.").replace("<","&lt;")}</p>

  <h2>{rec_h}</h2>
  <p>{_val(payload, "recommendations", "Priorisierte Empfehlungen für 90 Tage.").replace("<","&lt;")}</p>

  <h2>{roadmap_h}</h2>
  <p>{_val(payload, "roadmap", "T30 / T90 / T365 – kurze Roadmap mit Verantwortlichkeiten.").replace("<","&lt;")}</p>

  <h2>{compliance_h}</h2>
  <p>{_val(payload, "compliance", "Hinweise zu DSGVO/GDPR, ePrivacy, DSA und EU AI Act – pragmatisch & narrativ.").replace("<","&lt;")}</p>

  <h2>{vision_h}</h2>
  <p>{_val(payload, "vision", "Ein inspirierendes Zielbild plus 1 Gamechanger-Idee.").replace("<","&lt;")}</p>
</body>
</html>"""

    return {"html": html}
