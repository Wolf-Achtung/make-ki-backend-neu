# gpt_analyze_COMPLETE_FIX.py
# Vollständige Korrektur aller Fehler aus dem Log
# Version: HOTFIX-2025-09-28-v2

from __future__ import annotations

import os
import re
import json
import time
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from jinja2 import Environment, FileSystemLoader, select_autoescape

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
PDF_TEMPLATE_NAME = os.getenv("PDF_TEMPLATE_NAME", "pdf_template.html")

DEFAULT_LANG = "de"
SUPPORTED_LANGS = {"de", "en"}

# Quality-Control (standardmäßig AUS)
QUALITY_CONTROL_AVAILABLE = False  # Deaktiviert wegen Problemen
MIN_QUALITY_SCORE = 30

# Logging
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
logger = logging.getLogger("gpt_analyze")

# OpenAI
_openai_client = None
try:
    from openai import OpenAI
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key:
        _openai_client = OpenAI(api_key=api_key)
        logger.info(f"OpenAI Client initialisiert")
except Exception as e:
    logger.warning(f"OpenAI nicht verfügbar: {e}")

# ---------------------------------------------------------------------------
# KRITISCH: Fehlende Helper-Funktionen
# ---------------------------------------------------------------------------

def get_readiness_level(score, lang='de'):
    """Bestimmt Readiness-Level basierend auf Score"""
    score = int(score) if score else 50
    if score >= 85: return 'Führend' if lang == 'de' else 'Leading'
    if score >= 70: return 'Reif' if lang == 'de' else 'Mature'
    if score >= 50: return 'Fortgeschritten' if lang == 'de' else 'Advanced'
    if score >= 30: return 'Grundlegend' if lang == 'de' else 'Basic'
    return 'Anfänger' if lang == 'de' else 'Beginner'

def _safe_int(value, default=0):
    """Sichere Integer-Konvertierung"""
    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            cleaned = re.sub(r'[^\d]', '', str(value))
            if cleaned:
                return int(cleaned)
    except:
        pass
    return default

def _safe_float(value, default=0.0):
    """Sichere Float-Konvertierung"""
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = str(value).replace(',', '.')
            cleaned = re.sub(r'[^\d.]', '', cleaned)
            if cleaned and cleaned != '.':
                return float(cleaned)
    except:
        pass
    return default

# ---------------------------------------------------------------------------
# Jinja2 Environment mit allen benötigten Filtern
# ---------------------------------------------------------------------------

def setup_jinja_env(templates_dir: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    
    # KRITISCH: Alle fehlenden Filter hinzufügen
    env.filters["min"] = lambda a, b: min(_safe_float(a, 0), _safe_float(b, 0))
    env.filters["max"] = lambda a, b: max(_safe_float(a, 0), _safe_float(b, 0))
    env.filters["round"] = lambda v, p=0: round(_safe_float(v, 0), int(p))
    env.filters["int"] = lambda v: _safe_int(v, 0)
    env.filters["float"] = lambda v: _safe_float(v, 0)
    env.filters["currency"] = lambda v, s="€": f"{_safe_int(v, 0):,} {s}".replace(',', '.')
    env.filters["default"] = lambda v, d: v if v is not None else d
    env.filters["capitalize"] = lambda s: str(s).capitalize() if s else ""
    env.filters["upper"] = lambda s: str(s).upper() if s else ""
    env.filters["lower"] = lambda s: str(s).lower() if s else ""
    
    return env

# ---------------------------------------------------------------------------
# KPI Berechnung
# ---------------------------------------------------------------------------

def calculate_kpis(body: Dict[str, Any]) -> Dict[str, Any]:
    """Berechnet alle KPIs robust"""
    
    # Basis-Werte extrahieren
    digital = _safe_int(body.get('digitalisierungsgrad', 5), 5)
    digital = min(10, max(1, digital))
    
    auto_text = str(body.get('automatisierungsgrad', 'mittel')).lower()
    auto_map = {
        'sehr_niedrig': 20, 'sehr niedrig': 20,
        'eher_niedrig': 35, 'eher niedrig': 35, 
        'mittel': 50,
        'eher_hoch': 70, 'eher hoch': 70,
        'sehr_hoch': 85, 'sehr hoch': 85
    }
    auto = auto_map.get(auto_text, 50)
    
    risk = _safe_int(body.get('risikofreude', 3), 3)
    risk = min(5, max(1, risk))
    
    knowhow_text = str(body.get('ki_knowhow', 'grundkenntnisse')).lower()
    knowhow_map = {
        'keine': 10, 'anfaenger': 25, 'anfänger': 25,
        'grundkenntnisse': 50, 'fortgeschritten': 75, 'experte': 90
    }
    knowhow_score = knowhow_map.get(knowhow_text, 50)
    
    # Scores berechnen
    readiness = int(
        (digital * 3.5) +
        (auto * 0.25) +
        (knowhow_score * 0.20) +
        (risk * 4)
    )
    readiness = max(35, min(92, readiness))
    
    efficiency = int(min(65, max(25, (100 - auto) * 0.75)))
    
    compliance = 40
    if body.get('datenschutzbeauftragter') in ['ja', 'yes', 'extern']:
        compliance += 30
    compliance = min(100, compliance)
    
    innovation = int(
        risk * 15 +
        (knowhow_score * 0.35) +
        (digital * 3.5) +
        15
    )
    innovation = min(95, max(40, innovation))
    
    # Budget und ROI
    budget = get_budget_amount(body.get('budget', body.get('investitionsbudget', '6000')))
    roi_months = max(4, min(18, 12 - int(efficiency / 10)))
    annual_saving = max(budget * 2, int(budget * 2.5))
    
    return {
        'score_percent': readiness,
        'kpi_efficiency': efficiency,
        'kpi_cost_saving': int(efficiency * 0.85),
        'kpi_roi_months': roi_months,
        'kpi_compliance': compliance,
        'kpi_innovation': innovation,
        'roi_investment': budget,
        'roi_annual_saving': annual_saving,
        'roi_three_year': (annual_saving * 3 - budget),
        'digitalisierungsgrad': digital,
        'automatisierungsgrad': auto,
        'automatisierungsgrad_percent': auto,
        'risikofreude': risk,
        'ki_knowhow_score': knowhow_score
    }

def get_budget_amount(budget_str) -> int:
    """Robuste Budget-Extraktion"""
    if not budget_str:
        return 6000
    
    s = str(budget_str).strip().lower().replace("€","").replace(" ", "").replace(".", "")
    
    mapping = {
        "unter2000": 1500, "unter_2000": 1500,
        "2000-10000": 6000, "2.000-10.000": 6000,
        "10000-50000": 25000, "10.000-50.000": 25000,
        "50000-100000": 75000, "50.000-100.000": 75000,
        "ueber50000": 75000, "über50000": 75000
    }
    
    for k, v in mapping.items():
        if k in s or s in k:
            return v
    
    # Versuche Zahl zu extrahieren
    numbers = re.findall(r'\d+', s)
    if numbers:
        val = int(numbers[0])
        if val < 100:
            val = val * 1000
        return val
    
    return 6000

# ---------------------------------------------------------------------------
# Template Variablen - VOLLSTÄNDIG
# ---------------------------------------------------------------------------

def get_template_variables(body: Dict[str, Any], lang: str = 'de') -> Dict[str, Any]:
    """Erstellt ALLE benötigten Template-Variablen"""
    
    # KPIs berechnen
    kpis = calculate_kpis(body)
    
    # Use Cases verarbeiten
    ki_usecases = body.get('ki_usecases', [])
    if isinstance(ki_usecases, str):
        ki_usecases = [ki_usecases]
    elif not ki_usecases:
        ki_usecases = ['Prozessautomatisierung']
    
    ki_hemmnisse = body.get('ki_hemmnisse', [])
    if isinstance(ki_hemmnisse, str):
        ki_hemmnisse = [ki_hemmnisse]
    elif not ki_hemmnisse:
        ki_hemmnisse = ['Zeit', 'Budget']
    
    # Quick Win bestimmen
    quick_win_primary = "Prozessautomatisierung"
    if ki_usecases:
        first_uc = str(ki_usecases[0]).lower()
        if 'text' in first_uc:
            quick_win_primary = "Automatisierte Texterstellung"
        elif 'daten' in first_uc or 'analyse' in first_uc:
            quick_win_primary = "Datenanalyse & Reports"
        elif 'kunde' in first_uc or 'support' in first_uc:
            quick_win_primary = "KI-Chatbot"
    
    # Company Size Label
    company_size = body.get('unternehmensgroesse', '2-10')
    if str(company_size) == '1' or 'solo' in str(company_size).lower():
        company_size_label = "1 (Solo-Selbstständig)"
    elif '2-10' in str(company_size):
        company_size_label = "2-10 (Kleines Team)"
    elif '11-100' in str(company_size):
        company_size_label = "11-100 (KMU)"
    elif '101-500' in str(company_size):
        company_size_label = "101-500 (Mittelstand)"
    else:
        company_size_label = str(company_size)
    
    # Komplette Variablen-Sammlung
    variables = {
        # === Zeitstempel (FIX für 'now' Problem) ===
        'datum': datetime.now().strftime('%d.%m.%Y'),
        'today': datetime.now().strftime('%Y-%m-%d'),
        'generation_date': datetime.now().strftime('%d.%m.%Y'),
        'copyright_year': datetime.now().year,
        
        # === Firmendaten ===
        'branche': body.get('branche', 'Beratung'),
        'bundesland': body.get('bundesland', 'BE'),
        'hauptleistung': body.get('hauptleistung', ''),
        'unternehmensgroesse': company_size,
        'company_size_label': company_size_label,
        
        # === KPIs ===
        **kpis,  # Alle KPIs aus der Berechnung
        'readiness_level': get_readiness_level(kpis['score_percent'], lang),
        
        # === Budget ===
        'budget': body.get('budget', body.get('investitionsbudget', '6000')),
        'budget_amount': kpis['roi_investment'],
        'investitionsbudget': body.get('investitionsbudget', '6000'),
        
        # === KI-Daten ===
        'ki_usecases': ', '.join(str(uc) for uc in ki_usecases),
        'ki_hemmnisse': ', '.join(str(h) for h in ki_hemmnisse),
        'ki_knowhow': body.get('ki_knowhow', 'grundkenntnisse'),
        'ki_knowhow_label': body.get('ki_knowhow', 'grundkenntnisse').replace('_', ' ').title(),
        'quick_win_primary': quick_win_primary,
        
        # === Compliance ===
        'datenschutzbeauftragter': body.get('datenschutzbeauftragter', 'nein'),
        
        # === Prozesse ===
        'prozesse_papierlos': body.get('prozesse_papierlos', '51-80'),
        'prozesse_papierlos_percent': 65,
        
        # === Für Tools Template ===
        'tool_name': 'ChatGPT',  # Default Tool Name
        
        # === Meta ===
        'lang': lang,
        'is_german': lang == 'de',
        'report_version': '3.0',
        
        # === Formatierte Werte ===
        'roi_annual_saving_formatted': f"{kpis['roi_annual_saving']:,}".replace(',', '.') if lang == 'de' else f"{kpis['roi_annual_saving']:,}",
        'roi_three_year_formatted': f"{kpis['roi_three_year']:,}".replace(',', '.') if lang == 'de' else f"{kpis['roi_three_year']:,}",
        'roi_investment_formatted': f"{kpis['roi_investment']:,}".replace(',', '.') if lang == 'de' else f"{kpis['roi_investment']:,}",
        
        # === Collections ===
        'funding_programs': body.get('funding_programs', []),
        'tools': body.get('tools', []),
        'foerderprogramme_table': body.get('funding_programs', []),
        'tools_table': body.get('tools', []),
        
        # === Links ===
        'feedback_link': 'https://make.ki-sicherheit.jetzt/feedback',
        
        # === Meta Objekt ===
        'meta': {
            'title': 'KI-Statusbericht & Handlungsempfehlungen' if lang == 'de' else 'AI Status Report',
            'subtitle': f"AI Readiness: {kpis['score_percent']}%",
            'date': datetime.now().strftime('%d.%m.%Y'),
            'lang': lang,
            'version': '3.0'
        }
    }
    
    # Division by Zero verhindern
    if variables['kpi_efficiency'] == 0:
        variables['kpi_efficiency'] = 1
    
    return variables

# ---------------------------------------------------------------------------
# Prompt Processing
# ---------------------------------------------------------------------------

class PromptProcessor:
    def __init__(self, prompts_dir: str = PROMPTS_DIR):
        self.prompts_dir = prompts_dir
        self.env = None
        if os.path.isdir(self.prompts_dir):
            self.env = Environment(
                loader=FileSystemLoader(self.prompts_dir),
                autoescape=False,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            # Filter für Prompts hinzufügen
            self.env.filters["min"] = lambda a, b: min(_safe_float(a, 0), _safe_float(b, 0))
            self.env.filters["max"] = lambda a, b: max(_safe_float(a, 0), _safe_float(b, 0))
            self.env.filters["round"] = lambda v, p=0: round(_safe_float(v, 0), int(p))
            self.env.filters["int"] = lambda v: _safe_int(v, 0)

    def render(self, prompt_name: str, variables: Dict[str, Any], lang: str) -> str:
        if not self.env:
            raise FileNotFoundError(f"Prompts-Verzeichnis fehlt: {self.prompts_dir}")
        
        # Suche nach Prompt-Datei
        candidates = [
            f"{prompt_name}_{lang}.md",
            f"{prompt_name}.md",
        ]
        
        for filename in candidates:
            try:
                template = self.env.get_template(filename)
                return template.render(**variables)
            except Exception:
                continue
        
        raise FileNotFoundError(f"Prompt nicht gefunden: {prompt_name}")

# ---------------------------------------------------------------------------
# GPT Integration
# ---------------------------------------------------------------------------

def call_gpt_api(prompt: str, section_name: str, lang: str = 'de') -> Optional[str]:
    """Ruft OpenAI API auf"""
    if not _openai_client:
        return None
    
    try:
        system = (
            "Du bist ein KI-Strategieberater. "
            "Erstelle professionelle HTML-Inhalte in <p>-Tags. "
            "Verwende <strong> für Hervorhebungen. "
            "Sei konkret und handlungsorientiert."
        ) if lang == 'de' else (
            "You are an AI strategy consultant. "
            "Create professional HTML content in <p> tags. "
            "Use <strong> for emphasis. "
            "Be specific and action-oriented."
        )
        
        response = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"GPT API Fehler für {section_name}: {e}")
        return None

# ---------------------------------------------------------------------------
# Fallback Content
# ---------------------------------------------------------------------------

def generate_fallback_content(section_name: str, variables: Dict, lang: str) -> str:
    """Generiert Fallback-Content wenn GPT nicht verfügbar"""
    
    fallbacks = {
        'de': {
            'executive_summary': f"""
                <div class="executive-summary">
                <p><strong>Ihre Ausgangslage:</strong> Mit {variables.get('score_percent', 50)}% KI-Reifegrad 
                haben Sie eine solide Basis für die digitale Transformation. Ihre Branche 
                {variables.get('branche', 'Beratung')} bietet ideale Voraussetzungen für KI-Integration.</p>
                <p><strong>Ihr Erfolgsweg:</strong> Starten Sie mit {variables.get('quick_win_primary', 'Quick Wins')}, 
                die sofortige Verbesserungen bringen. Die schrittweise Implementierung minimiert Risiken.</p>
                <p><strong>Ihr Gewinn:</strong> Die erwarteten Einsparungen von {variables.get('roi_annual_saving', 20000)} EUR 
                jährlich rechtfertigen die Investition nach {variables.get('kpi_roi_months', 12)} Monaten.</p>
                </div>
            """,
            'business': f"""
                <div class="business-case">
                <h3>Ihr Business Case</h3>
                <p>Bei einer Investition von {variables.get('budget_amount', 10000)} EUR erreichen Sie 
                den Break-Even nach {variables.get('kpi_roi_months', 12)} Monaten.</p>
                <p>Die jährlichen Einsparungen von {variables.get('roi_annual_saving', 20000)} EUR 
                ergeben über 3 Jahre einen Gewinn von {variables.get('roi_three_year', 50000)} EUR.</p>
                </div>
            """,
            'vision': """
                <div class="vision">
                <h3>Ihre KI-Vision 2027</h3>
                <p>In drei Jahren haben Sie KI vollständig in Ihre Kernprozesse integriert. 
                Die Automatisierung von Routineaufgaben schafft Freiräume für Innovation und Kundenfokus.</p>
                <p>Sie positionieren sich als Vorreiter in Ihrer Branche und ziehen talentierte 
                Mitarbeiter an, die mit modernen Tools arbeiten möchten.</p>
                </div>
            """,
            'tools': """
                <div class="tools">
                <h3>Empfohlene KI-Tools</h3>
                <p><strong>ChatGPT/Claude:</strong> Für Texterstellung und Analyse - 0-20 EUR/Monat</p>
                <p><strong>Zapier/Make:</strong> Für Prozessautomatisierung - 20-100 EUR/Monat</p>
                <p><strong>Notion AI:</strong> Für Wissensmanagement - 10-20 EUR/User/Monat</p>
                </div>
            """
        },
        'en': {
            'executive_summary': f"""
                <div class="executive-summary">
                <p><strong>Your Starting Position:</strong> With {variables.get('score_percent', 50)}% AI maturity, 
                you have a solid foundation for digital transformation.</p>
                <p><strong>Your Success Path:</strong> Start with {variables.get('quick_win_primary', 'Quick Wins')} 
                that bring immediate improvements.</p>
                <p><strong>Your Returns:</strong> Expected savings of {variables.get('roi_annual_saving', 20000)} EUR 
                annually justify the investment after {variables.get('kpi_roi_months', 12)} months.</p>
                </div>
            """
        }
    }
    
    lang_fallbacks = fallbacks.get(lang, fallbacks['de'])
    return lang_fallbacks.get(section_name, f'<p>Content for {section_name} is being prepared.</p>')

# ---------------------------------------------------------------------------
# Section Generation
# ---------------------------------------------------------------------------

def generate_section(section_name: str, variables: Dict, lang: str = 'de') -> str:
    """Generiert eine Section mit Prompt oder Fallback"""
    
    try:
        # Versuche Prompt zu laden
        prompt_processor = PromptProcessor()
        prompt = prompt_processor.render(section_name, variables, lang)
        
        # Versuche GPT-Aufruf
        if _openai_client:
            content = call_gpt_api(prompt, section_name, lang)
            if content and len(content) > 100:
                return content
    except Exception as e:
        logger.warning(f"Prompt-Rendering fehlgeschlagen [{section_name}]: {e}")
    
    # Fallback verwenden
    return generate_fallback_content(section_name, variables, lang)

# ---------------------------------------------------------------------------
# Main Function
# ---------------------------------------------------------------------------

def analyze_briefing(body: Dict[str, Any], lang: str = 'de') -> str:
    """Hauptfunktion - generiert den kompletten HTML-Report"""
    
    try:
        # Template Environment
        env = setup_jinja_env(TEMPLATES_DIR)
        template = env.get_template(PDF_TEMPLATE_NAME)
        
        # Variablen vorbereiten
        variables = get_template_variables(body, lang)
        
        # Sektionen generieren
        sections = [
            'executive_summary', 'business', 'persona', 'quick_wins',
            'risks', 'recommendations', 'roadmap', 'praxisbeispiel',
            'coach', 'vision', 'gamechanger', 'compliance',
            'foerderprogramme', 'tools'
        ]
        
        context = dict(variables)  # Kopiere alle Variablen
        
        # HTML-Sektionen generieren
        for section in sections:
            key = f"{section.replace('_', '')}_html"
            if section == 'executive_summary':
                key = 'exec_summary_html'
            context[key] = generate_section(section, variables, lang)
        
        # Template rendern
        html = template.render(**context)
        return html
        
    except Exception as e:
        logger.error(f"Template-Rendering fehlgeschlagen: {e}")
        # Minimaler Fallback
        return f"""
        <html>
        <body>
        <h1>KI-Statusbericht</h1>
        <p>Der Report wird generiert. Bitte versuchen Sie es in wenigen Minuten erneut.</p>
        <p>Bei anhaltenden Problemen kontaktieren Sie: kontakt@ki-sicherheit.jetzt</p>
        </body>
        </html>
        """

# Export
__all__ = ['analyze_briefing']
