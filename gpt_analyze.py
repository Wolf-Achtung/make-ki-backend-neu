from typing import Dict, Any, List, Optional
from loguru import logger
from services import llm, i18n

def build_report_payload(
    language: str,
    company: Optional[str],
    industry: Optional[str],
    prompts: Dict[str, str],
    datasets: Dict[str, Any],
    latest_news: List[Dict[str, Any]] | None = None,
    sections: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Central orchestration. Merges static datasets, optional LLM outputs,
    and Tavily news into a single Jinja context.
    """
    lang = i18n.normalize_lang(language)
    latest_news = latest_news or []

    # --- Compose base meta ---
    meta = {
        "language": lang,
        "company": company,
        "industry": industry,
    }

    # --- Choose default sections (order matters) ---
    default_sections = [
        "einleitung" if lang == "de" else "introduction",
        "strategie" if lang == "de" else "strategy",
        "governance",
        "regulierung" if lang == "de" else "regulation",
        "projekte" if lang == "de" else "projects",
        "news",
        "ausblick" if lang == "de" else "outlook"
    ]
    if sections:
        wanted = [s.lower() for s in sections]
        ordered = [s for s in default_sections if s in wanted]
        # include any extra in the end
        rest = [s for s in wanted if s not in ordered]
        sections_order = ordered + rest
    else:
        sections_order = default_sections

    # --- Helper to maybe call LLM with prompt key ---
    def llm_section(key_de: str, key_en: str) -> Optional[str]:
        key = key_de if lang == "de" else key_en
        prompt = prompts.get(key) or prompts.get(key_de) or prompts.get(key_en)
        if not prompt:
            return None
        sys_prompt = "Du bist ein zuverlässiger Analyst." if lang == "de" else "You are a reliable analyst."
        return llm.generate_with_llm(prompt=prompt, sys_prompt=sys_prompt)

    # --- Build sections ---
    sections_map: Dict[str, Any] = {}

    # Intro
    intro = llm_section("intro", "intro")
    if not intro:
        intro = (
            f"Dieser Bericht fasst den aktuellen Stand der KI-Initiativen bei {company or 'dem Unternehmen'} "
            f"in der Branche {industry or 'n/a'} zusammen."
            if lang == "de"
            else f"This report summarizes the current status of AI initiatives at {company or 'the organization'} in the {industry or 'n/a'} sector."
        )
    sections_map["einleitung" if lang == "de" else "introduction"] = intro

    # Strategy
    strategy = llm_section("strategie", "strategy") or prompts.get("strategy") or ""
    if not strategy:
        strategy = "Strategische Leitlinien wurden zusammengestellt." if lang == "de" else "Strategic guidelines have been summarized."
    sections_map["strategie" if lang == "de" else "strategy"] = strategy

    # Governance
    governance = llm_section("governance", "governance") or prompts.get("governance") or ""
    if not governance:
        governance = "Governance-Strukturen sind im Aufbau." if lang == "de" else "Governance structures are being established."
    sections_map["governance"] = governance

    # Regulation
    regulation = llm_section("regulierung", "regulation") or prompts.get("regulation") or ""
    if not regulation:
        regulation = "Überblick über relevante Regulierungen wurde ergänzt." if lang == "de" else "An overview of relevant regulations has been added."
    sections_map["regulierung" if lang == "de" else "regulation"] = regulation

    # Projects
    projects_text = llm_section("projekte", "projects") or prompts.get("projects") or ""
    if not projects_text:
        projects_text = "Wichtige Projekte wurden priorisiert." if lang == "de" else "Key projects have been prioritized."
    sections_map["projekte" if lang == "de" else "projects"] = projects_text

    # News (from Tavily if present)
    sections_map["news"] = latest_news

    # Outlook
    outlook = llm_section("ausblick", "outlook") or prompts.get("outlook") or ""
    if not outlook:
        outlook = "Nächste Schritte wurden definiert." if lang == "de" else "Next steps have been defined."
    sections_map["ausblick" if lang == "de" else "outlook"] = outlook

    # Filter by requested order
    ordered_sections = {k: sections_map.get(k) for k in sections_order if k in sections_map}

    payload = {
        "meta": meta,
        "sections": ordered_sections,
        "datasets": datasets,   # pass-through in case templates render charts/tables
    }
    return payload
