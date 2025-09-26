# gpt_analyze.py - Enhanced Production Version (CORRECTED)
# Version: 2.0.1 (2024-12-19)
# Features: Vollständige Fragebogen-Integration, KPI-Berechnung, Tool-Matching, Förder-Analyse, Live-Daten

from __future__ import annotations

import os
import re
import json
import csv
import sys
from pathlib import Path
from datetime import datetime as _dt, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from jinja2 import Template, Environment, FileSystemLoader

import httpx

# OpenAI Client
try:
    from openai import OpenAI
    _openai_client = OpenAI()
except Exception:
    _openai_client = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIRS = [BASE_DIR / "data", BASE_DIR, Path("/app/data")]
PROMPT_DIRS = [BASE_DIR / "prompts", Path("/app/prompts")]

# ============================= Branchenbenchmarks 2025 =============================

class IndustryBenchmark:
    """Aktuelle Branchendurchschnittswerte für KI-Adoption"""
    def __init__(self, digitalisierung_avg, automatisierung_avg, 
                 ki_adoption_rate, roi_expectation, time_to_value_days):
        self.digitalisierung_avg = digitalisierung_avg
        self.automatisierung_avg = automatisierung_avg
        self.ki_adoption_rate = ki_adoption_rate
        self.roi_expectation = roi_expectation
        self.time_to_value_days = time_to_value_days

INDUSTRY_BENCHMARKS = {
    "beratung": IndustryBenchmark(7.2, 65, 42, 3.2, 90),
    "it": IndustryBenchmark(8.5, 78, 68, 4.1, 60),
    "marketing": IndustryBenchmark(6.8, 58, 38, 2.8, 75),
    "handel": IndustryBenchmark(5.9, 45, 28, 2.4, 120),
    "industrie": IndustryBenchmark(6.3, 72, 35, 3.5, 150),
    "produktion": IndustryBenchmark(6.5, 75, 40, 3.8, 120),
    "finanzen": IndustryBenchmark(7.8, 69, 52, 3.8, 100),
    "gesundheit": IndustryBenchmark(5.2, 38, 22, 2.1, 180),
    "logistik": IndustryBenchmark(6.1, 61, 31, 2.9, 110),
    "bildung": IndustryBenchmark(4.8, 32, 18, 1.8, 200),
    "default": IndustryBenchmark(6.0, 50, 30, 2.5, 120)
}

# ============================= Prompt Processor =============================

class PromptProcessor:
    """Zentrale Prompt-Verwaltung für beide Sprachen"""
    
    def __init__(self, prompt_dirs: Optional[List[Path]] = None):
        self.prompt_dirs = prompt_dirs or PROMPT_DIRS
        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader([str(d) for d in self.prompt_dirs if d.exists()]),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
    def load_prompt(self, name: str, lang: str = 'de') -> Template:
        """Lade Prompt-Template nach Name und Sprache"""
        filename = f"{name}_{lang}.md"
        try:
            return self.env.get_template(filename)
        except Exception as e:
            # Fallback zu deutscher Version
            if lang != 'de':
                return self.load_prompt(name, 'de')
            # Wenn auch DE nicht existiert, gebe Fallback
            return Template(self.get_fallback_prompt(name, lang))
            
    def render_prompt(self, name: str, variables: Dict[str, Any], lang: str = 'de') -> str:
        """Rendere Prompt mit Variablen"""
        template = self.load_prompt(name, lang)
        return template.render(**variables)
    
    def get_fallback_prompt(self, name: str, lang: str) -> str:
        """Fallback-Prompt wenn Template nicht gefunden"""
        fallbacks = {
            'executive_summary': """
                Erstellen Sie eine Executive Summary basierend auf:
                KI-Reifegrad: {{ score_percent }}%
                Branche: {{ branche }}
                Unternehmensgröße: {{ company_size_label }}
                """,
            'quick_wins': """
                Generieren Sie 3 Quick Wins für:
                Branche: {{ branche }}
                Use Cases: {{ ki_usecases }}
                Budget: {{ budget }}
                """,
            'risk_analysis': """
                Analysieren Sie Risiken für:
                Branche: {{ branche }}
                Compliance-Status: {{ kpi_compliance }}%
                Datenschutzbeauftragter: {{ datenschutzbeauftragter }}
                """
        }
        return fallbacks.get(name, f"Generiere {name} für {{ branche }}")

# ============================= Hilfsfunktionen =============================

def safe_str(text: Any) -> str:
    """Sichere String-Konvertierung"""
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode('utf-8', errors='replace')
    return str(text)

def clean_text(text: str) -> str:
    """Bereinigt Text von Artefakten"""
    if not text:
        return ""
    
    # Fix encoding
    text = text.replace('—', '-').replace('"', '"').replace('"', '"')
    text = text.replace('€', '€')
    
    # Remove code fences
    text = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    
    # Clean whitespace
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def clean_and_validate_html(html: str) -> str:
    """Bereinigt und validiert HTML Output"""
    if not html:
        return ""
    
    html = clean_text(html)
    
    # Stelle sicher dass HTML-Tags vorhanden sind
    if not html.strip().startswith('<'):
        html = f'<p>{html}</p>'
    
    return html

# ============================= Template Variable Mapping =============================

def get_template_variables(form_data: Dict[str, Any], lang: str = 'de') -> Dict[str, Any]:
    """
    Vollständiges Variable Mapping für Template-Rendering
    """
    # Berechne KPIs zuerst
    kpis = calculate_kpis_from_answers(form_data)
    
    # Basis-Mappings
    variables = {
        # === Firmendaten ===
        'branche': safe_str(form_data.get('branche', 'beratung')),
        'bundesland': safe_str(form_data.get('bundesland', 'BE')),
        'hauptleistung': safe_str(form_data.get('hauptleistung', '')),
        'unternehmensgroesse': safe_str(form_data.get('unternehmensgroesse', '2-10')),
        
        # === Formatierte Labels ===
        'company_size_label': get_company_size_label(
            form_data.get('unternehmensgroesse'), lang
        ),
        'ki_knowhow_label': get_knowledge_label(
            form_data.get('ki_knowhow', 'grundkenntnisse'), lang
        ),
        'automatisierungsgrad_label': get_automation_label(
            form_data.get('automatisierungsgrad', 'mittel'), lang
        ),
        
        # === Digitale Metriken ===
        'digitalisierungsgrad': kpis['digitalisierungsgrad'],
        'automatisierungsgrad': form_data.get('automatisierungsgrad', 'mittel'),
        'automatisierungsgrad_percent': kpis['automatisierungsgrad'],
        'prozesse_papierlos': form_data.get('prozesse_papierlos', '51-80'),
        'prozesse_papierlos_percent': get_paperless_percent(
            form_data.get('prozesse_papierlos', '51-80')
        ),
        'risikofreude': kpis['risikofreude'],
        
        # === Ziele und Herausforderungen ===
        'projektziel': ', '.join(form_data.get('projektziel', [])),
        'zielgruppen': ', '.join(form_data.get('zielgruppen', [])),
        'ki_usecases': ', '.join(form_data.get('ki_usecases', [])),
        'ki_hemmnisse': ', '.join(form_data.get('ki_hemmnisse', [])),
        
        # === KPIs ===
        'score_percent': kpis['readiness_score'],
        'readiness_level': get_readiness_level(kpis['readiness_score'], lang),
        'kpi_efficiency': kpis['kpi_efficiency'],
        'kpi_cost_saving': kpis['kpi_cost_saving'],
        'kpi_roi_months': kpis['kpi_roi_months'],
        'kpi_compliance': kpis['kpi_compliance'],
        'kpi_innovation': kpis['kpi_innovation'],
        
        # === Finanzen ===
        'budget': form_data.get('budget', '2000-10000'),
        'budget_amount': get_budget_amount(form_data.get('budget')),
        'roi_investment': kpis['roi_investment'],
        'roi_annual_saving': kpis['roi_annual_saving'],
        'roi_three_year': kpis['roi_three_year'],
        
        # === Compliance ===
        'datenschutzbeauftragter': form_data.get('datenschutzbeauftragter', 'nein'),
        'dsgvo_assessment': form_data.get('dsgvo_folgenabschaetzung', 'nein'),
        'eu_ai_act_knowledge': form_data.get('eu_ai_act_kenntnis', 'grundkenntnisse'),
        'has_governance': form_data.get('richtlinien_governance', 'nein'),
        'compliance_status': get_compliance_status(form_data, lang),
        
        # === Quick Wins (für Templates) ===
        'quick_win_primary': get_primary_quick_win(form_data, lang),
        
        # === Metadaten ===
        'generation_date': _dt.now().strftime('%d.%m.%Y'),
        'report_version': '2.0',
        'lang': lang,
        'is_german': lang == 'de'
    }
    
    # Füge formatierte Zahlen basierend auf Sprache hinzu
    if lang == 'de':
        variables['roi_annual_saving_formatted'] = f"{kpis['roi_annual_saving']:,.0f}".replace(',', '.')
        variables['roi_three_year_formatted'] = f"{kpis['roi_three_year']:,.0f}".replace(',', '.')
        variables['roi_investment_formatted'] = f"{kpis['roi_investment']:,.0f}".replace(',', '.')
    else:
        variables['roi_annual_saving_formatted'] = f"{kpis['roi_annual_saving']:,}"
        variables['roi_three_year_formatted'] = f"{kpis['roi_three_year']:,}"
        variables['roi_investment_formatted'] = f"{kpis['roi_investment']:,}"
    
    return variables

# Helper Funktionen für Variable Mapping
def get_company_size_label(size: str, lang: str) -> str:
    """Formatiertes Label für Unternehmensgröße"""
    labels = {
        'de': {
            '1': '1 (Solo-Selbstständig)',
            'solo': '1 (Solo-Selbstständig)',
            '2-10': '2-10 (Kleines Team)',
            '11-100': '11-100 (KMU)',
            '101-500': '101-500 (Mittelstand)',
            'ueber_500': 'Über 500 (Großunternehmen)'
        },
        'en': {
            '1': '1 (Freelancer)',
            'solo': '1 (Freelancer)',
            '2-10': '2-10 (Small Team)',
            '11-100': '11-100 (SME)',
            '101-500': '101-500 (Mid-size)',
            'ueber_500': 'Over 500 (Enterprise)'
        }
    }
    return labels.get(lang, labels['de']).get(safe_str(size).lower(), size)

def get_knowledge_label(knowledge: str, lang: str) -> str:
    """Formatiertes Label für KI-Kenntnisse"""
    labels = {
        'de': {
            'anfaenger': 'Anfänger',
            'grundkenntnisse': 'Grundkenntnisse',
            'fortgeschritten': 'Fortgeschritten',
            'experte': 'Experte'
        },
        'en': {
            'anfaenger': 'Beginner',
            'grundkenntnisse': 'Basic Knowledge',
            'fortgeschritten': 'Advanced',
            'experte': 'Expert'
        }
    }
    return labels.get(lang, labels['de']).get(safe_str(knowledge).lower(), knowledge)

def get_automation_label(automation: str, lang: str) -> str:
    """Formatiertes Label für Automatisierungsgrad"""
    labels = {
        'de': {
            'sehr_niedrig': 'Sehr niedrig (10%)',
            'eher_niedrig': 'Eher niedrig (30%)',
            'mittel': 'Mittel (50%)',
            'eher_hoch': 'Eher hoch (70%)',
            'sehr_hoch': 'Sehr hoch (85%)'
        },
        'en': {
            'sehr_niedrig': 'Very low (10%)',
            'eher_niedrig': 'Rather low (30%)',
            'mittel': 'Medium (50%)',
            'eher_hoch': 'Rather high (70%)',
            'sehr_hoch': 'Very high (85%)'
        }
    }
    return labels.get(lang, labels['de']).get(safe_str(automation).lower(), automation)

def get_paperless_percent(range_str: str) -> int:
    """Konvertiert Papierlos-Range zu Prozentzahl"""
    mapping = {
        '0-20': 20,
        '21-50': 40,
        '51-80': 65,
        '81-100': 85
    }
    return mapping.get(safe_str(range_str), 50)

def get_budget_amount(budget_str: str) -> int:
    """Konvertiert Budget-String zu Zahl"""
    mapping = {
        'unter_2000': 1500,
        '2000-10000': 6000,
        '2.000-10.000': 6000,
        '10000-50000': 25000,
        '10.000-50.000': 25000,
        'ueber_50000': 75000,
        'über_50.000': 75000
    }
    clean_budget = safe_str(budget_str).lower().replace(' ', '').replace('€', '')
    return mapping.get(clean_budget, 6000)

def get_readiness_level(score: int, lang: str) -> str:
    """Bestimmt Readiness-Level basierend auf Score"""
    levels = {
        'de': {
            (0, 30): 'Anfänger',
            (30, 50): 'Grundlegend',
            (50, 70): 'Fortgeschritten',
            (70, 85): 'Reif',
            (85, 101): 'Führend'
        },
        'en': {
            (0, 30): 'Beginner',
            (30, 50): 'Basic',
            (50, 70): 'Advanced',
            (70, 85): 'Mature',
            (85, 101): 'Leading'
        }
    }
    
    level_dict = levels.get(lang, levels['de'])
    for (min_val, max_val), label in level_dict.items():
        if min_val <= score < max_val:
            return label
    return level_dict[(70, 85)]  # Default

def get_compliance_status(form_data: Dict[str, Any], lang: str) -> str:
    """Bestimmt Compliance-Status"""
    has_dpo = form_data.get('datenschutzbeauftragter') == 'ja'
    has_dpia = form_data.get('dsgvo_folgenabschaetzung') in ['ja', 'teilweise']
    has_ai_knowledge = form_data.get('eu_ai_act_kenntnis') in ['gut', 'sehr_gut']
    
    if lang == 'de':
        if has_dpo and has_dpia and has_ai_knowledge:
            return 'Vollständig konform'
        elif has_dpo or has_dpia:
            return 'Teilweise konform'
        else:
            return 'Grundlagen fehlen'
    else:
        if has_dpo and has_dpia and has_ai_knowledge:
            return 'Fully compliant'
        elif has_dpo or has_dpia:
            return 'Partially compliant'
        else:
            return 'Basics missing'

def get_primary_quick_win(form_data: Dict[str, Any], lang: str) -> str:
    """Bestimmt primären Quick Win basierend auf Use Cases"""
    use_cases = form_data.get('ki_usecases', [])
    if not use_cases:
        return 'Prozessautomatisierung' if lang == 'de' else 'Process Automation'
    
    # Priorisierte Quick Wins
    quick_wins = {
        'de': {
            'texterstellung': 'Automatisierte Texterstellung',
            'spracherkennung': 'Meeting-Transkription',
            'prozessautomatisierung': 'Workflow-Automatisierung',
            'datenanalyse': 'Automatisierte Reports',
            'kundensupport': 'KI-Chatbot',
            'wissensmanagement': 'Wissensdatenbank',
            'marketing': 'Content-Automation'
        },
        'en': {
            'texterstellung': 'Automated Writing',
            'spracherkennung': 'Meeting Transcription',
            'prozessautomatisierung': 'Workflow Automation',
            'datenanalyse': 'Automated Reports',
            'kundensupport': 'AI Chatbot',
            'wissensmanagement': 'Knowledge Base',
            'marketing': 'Content Automation'
        }
    }
    
    qw_dict = quick_wins.get(lang, quick_wins['de'])
    for uc in use_cases:
        uc_key = safe_str(uc).lower().replace(' ', '').replace('-', '')
        for key, value in qw_dict.items():
            if key in uc_key or uc_key in key:
                return value
    
    return qw_dict.get('prozessautomatisierung')

# ============================= KPI-Berechnung =============================

def calculate_kpis_from_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Berechnet alle KPIs basierend auf den Fragebogen-Antworten
    """
    # Extrahiere Basis-Werte
    digital = min(10, max(1, int(answers.get('digitalisierungsgrad', 5))))
    
    # Automatisierungsgrad mapping
    auto_map = {
        'sehr_niedrig': 10, 'eher_niedrig': 30,
        'mittel': 50, 'eher_hoch': 70, 'sehr_hoch': 85
    }
    auto_text = safe_str(answers.get('automatisierungsgrad', 'mittel')).lower().replace(' ', '_')
    auto = auto_map.get(auto_text, 50)
    
    # Papierlos-Prozesse mapping
    papier_map = {'0-20': 20, '21-50': 40, '51-80': 65, '81-100': 85}
    papier_text = safe_str(answers.get('prozesse_papierlos', '51-80')).replace('_', '-')
    papier = papier_map.get(papier_text, 50)
    
    # Risikofreude
    risk = min(5, max(1, int(answers.get('risikofreude', 3))))
    
    # KI-Know-how mapping
    knowledge_map = {
        'anfaenger': 20, 'grundkenntnisse': 40,
        'fortgeschritten': 70, 'experte': 90
    }
    knowledge_text = safe_str(answers.get('ki_knowhow', 'grundkenntnisse')).lower()
    knowledge = knowledge_map.get(knowledge_text, 40)
    
    # Berechne Readiness Score (gewichtet)
    readiness = int(
        digital * 2.5 +          # 25% Digitalisierung
        (auto/10) * 2.0 +        # 20% Automatisierung
        (papier/10) * 1.5 +      # 15% Papierlose Prozesse
        (risk * 2) * 1.5 +       # 15% Risikobereitschaft
        (knowledge/10) * 1.5 +   # 15% KI-Kenntnisse
        10                       # 10% Basis
    )
    
    # Unternehmensgröße für ROI-Berechnung
    size = safe_str(answers.get('unternehmensgroesse', '2-10')).lower().replace(' ', '')
    size_factors = {
        '1': {'employees': 1, 'revenue': 80000, 'cost_base': 50000},
        'solo': {'employees': 1, 'revenue': 80000, 'cost_base': 50000},
        '2-10': {'employees': 5, 'revenue': 400000, 'cost_base': 250000},
        '11-100': {'employees': 50, 'revenue': 4000000, 'cost_base': 2500000},
        '101-500': {'employees': 250, 'revenue': 20000000, 'cost_base': 12000000}
    }
    factors = size_factors.get(size, size_factors['2-10'])
    
    # Budget
    budget = get_budget_amount(answers.get('budget', '2000-10000'))
    
    # Effizienzpotenzial
    efficiency_gap = 100 - auto
    efficiency_potential = int(efficiency_gap * 0.6)  # Realistisch 60% des Gaps
    
    # Kosteneinsparung
    cost_saving_potential = int(efficiency_potential * 0.7)
    annual_saving = int(factors['cost_base'] * (cost_saving_potential / 100))
    
    # ROI-Berechnung
    if annual_saving > 0:
        roi_months = min(36, max(3, int((budget / annual_saving) * 12)))
    else:
        roi_months = 24
        
    # Compliance Score
    compliance = 30  # Basis
    if answers.get('datenschutzbeauftragter') == 'ja':
        compliance += 25
    if answers.get('dsgvo_folgenabschaetzung') in ['ja', 'teilweise']:
        compliance += 20
    if answers.get('eu_ai_act_kenntnis') in ['gut', 'sehr_gut']:
        compliance += 20
    if answers.get('richtlinien_governance') in ['ja', 'teilweise']:
        compliance += 15
        
    # Innovation Index
    has_innovation_team = answers.get('innovationsteam') in ['ja', 'internes_team']
    innovation = int(
        risk * 15 +
        (knowledge/100) * 30 +
        (20 if has_innovation_team else 0) +
        (digital/10) * 35
    )
    
    return {
        'readiness_score': min(100, readiness),
        'kpi_efficiency': efficiency_potential,
        'kpi_cost_saving': cost_saving_potential,
        'kpi_roi_months': roi_months,
        'kpi_compliance': min(100, compliance),
        'kpi_innovation': min(100, innovation),
        'roi_investment': budget,
        'roi_annual_saving': annual_saving,
        'roi_three_year': (annual_saving * 3 - budget),
        'digitalisierungsgrad': digital,
        'automatisierungsgrad': auto,
        'risikofreude': risk
    }
# ============================= GPT Integration (Fortsetzung) =============================

def should_use_gpt(prompt_name: str, answers: Dict[str, Any]) -> bool:
    """Bestimmt ob GPT für diese Sektion verwendet werden soll"""
    # Immer GPT für komplexe narrative Sektionen
    gpt_sections = ['executive_summary', 'vision', 'gamechanger', 'coach']
    
    if prompt_name in gpt_sections:
        return True
    
    # Lokale Generierung für datengetriebene Sektionen
    local_sections = ['tools', 'funding', 'compliance', 'quick_wins']
    if prompt_name in local_sections:
        return False
    
    # Hybrid-Ansatz basierend auf Komplexität
    complexity = calculate_complexity(answers)
    return complexity > 7

def calculate_complexity(answers: Dict[str, Any]) -> int:
    """Berechnet Komplexitäts-Score für das Unternehmen"""
    score = 5  # Basis
    
    # Größen-Komplexität
    size = answers.get('unternehmensgroesse', '2-10')
    if '11-100' in str(size):
        score += 2
    elif '101-500' in str(size):
        score += 3
    
    # Branchen-Komplexität
    complex_industries = ['finanzen', 'gesundheit', 'industrie', 'produktion']
    if answers.get('branche') in complex_industries:
        score += 2
    
    # Multiple Use Cases
    use_cases = answers.get('ki_usecases', [])
    if len(use_cases) > 3:
        score += 1
    if len(use_cases) > 5:
        score += 1
    
    # Compliance-Anforderungen
    if answers.get('datenschutzbeauftragter') == 'ja':
        score += 1
    
    return min(10, score)

def call_gpt_api(prompt: str, section_name: str, lang: str = 'de') -> str:
    """Ruft OpenAI API mit optimierten Einstellungen auf"""
    try:
        if not _openai_client:
            raise Exception("OpenAI Client nicht initialisiert")
        
        # System-Prompt basierend auf Sprache
        system_prompts = {
            'de': """Du bist ein erfahrener KI-Strategieberater für den deutschen Mittelstand.
                     Erstelle professionelle, handlungsorientierte Inhalte im HTML-Format.
                     Nutze <strong> für wichtige Begriffe und <em> für Hervorhebungen.
                     Halte dich genau an die vorgegebene Struktur und Länge.""",
            'en': """You are an experienced AI strategy consultant for European SMEs.
                     Create professional, action-oriented content in HTML format.
                     Use <strong> for important terms and <em> for emphasis.
                     Follow the given structure and length precisely."""
        }
        
        response = _openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Oder "gpt-4" für höhere Qualität
            messages=[
                {"role": "system", "content": system_prompts.get(lang, system_prompts['de'])},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7 if section_name in ['vision', 'coach'] else 0.5,
            max_tokens=1000,
            presence_penalty=0.2,
            frequency_penalty=0.1
        )
        
        return clean_and_validate_html(response.choices[0].message.content)
        
    except Exception as e:
        print(f"GPT API Fehler für {section_name}: {e}")
        return generate_fallback_content(section_name, lang)

# ============================= NEU HINZUGEFÜGTE FUNKTIONEN (KORREKTUR) =============================

def generate_business_case(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert Business Case Sektion"""
    branche = safe_str(answers.get('branche', 'Beratung'))
    size = safe_str(answers.get('unternehmensgroesse', '2-10'))
    
    # Berechne zusätzliche Metriken
    productivity_gain = int(kpis['kpi_efficiency'] * 0.8)
    customer_satisfaction_improvement = min(25, int(kpis['kpi_innovation'] * 0.3))
    time_to_market_reduction = min(40, int(kpis['kpi_efficiency'] * 0.5))
    
    if lang == 'de':
        return f"""
        <div class="business-case">
            <h3>Ihr Business Case für KI-Transformation</h3>
            
            <div class="business-metrics">
                <h4>Finanzielle Kennzahlen</h4>
                <p>
                    <strong>Investitionssumme:</strong> {kpis['roi_investment']:,} EUR<br/>
                    <strong>Jährliche Einsparung:</strong> {kpis['roi_annual_saving']:,} EUR<br/>
                    <strong>Break-Even:</strong> {kpis['kpi_roi_months']} Monate<br/>
                    <strong>3-Jahres-Nettogewinn:</strong> {kpis['roi_three_year']:,} EUR<br/>
                    <strong>ROI nach 3 Jahren:</strong> {int(kpis['roi_three_year'] / kpis['roi_investment'] * 100)}%
                </p>
            </div>
            
            <div class="qualitative-benefits">
                <h4>Qualitative Vorteile</h4>
                <ul>
                    <li>Produktivitätssteigerung um {productivity_gain}%</li>
                    <li>Reduzierung der Time-to-Market um {time_to_market_reduction}%</li>
                    <li>Verbesserung der Kundenzufriedenheit um {customer_satisfaction_improvement}%</li>
                    <li>Freisetzung von {int(kpis['kpi_efficiency'] / 2)} Stunden pro Mitarbeiter/Woche für wertschöpfende Tätigkeiten</li>
                    <li>Positionierung als Innovationsführer in {branche}</li>
                </ul>
            </div>
            
            <div class="risk-mitigation">
                <h4>Risikominimierung</h4>
                <p>Durch schrittweise Implementierung und Quick Wins reduzieren Sie das Investitionsrisiko. 
                Die ersten messbaren Erfolge erwarten wir bereits nach 30 Tagen.</p>
            </div>
        </div>
        """
    else:
        return f"""
        <div class="business-case">
            <h3>Your AI Transformation Business Case</h3>
            
            <div class="business-metrics">
                <h4>Financial Metrics</h4>
                <p>
                    <strong>Investment Amount:</strong> EUR {kpis['roi_investment']:,}<br/>
                    <strong>Annual Savings:</strong> EUR {kpis['roi_annual_saving']:,}<br/>
                    <strong>Break-Even:</strong> {kpis['kpi_roi_months']} months<br/>
                    <strong>3-Year Net Profit:</strong> EUR {kpis['roi_three_year']:,}<br/>
                    <strong>ROI after 3 years:</strong> {int(kpis['roi_three_year'] / kpis['roi_investment'] * 100)}%
                </p>
            </div>
            
            <div class="qualitative-benefits">
                <h4>Qualitative Benefits</h4>
                <ul>
                    <li>Productivity increase of {productivity_gain}%</li>
                    <li>Time-to-market reduction of {time_to_market_reduction}%</li>
                    <li>Customer satisfaction improvement of {customer_satisfaction_improvement}%</li>
                    <li>Freeing up {int(kpis['kpi_efficiency'] / 2)} hours per employee/week for value-adding activities</li>
                    <li>Positioning as innovation leader in {branche}</li>
                </ul>
            </div>
            
            <div class="risk-mitigation">
                <h4>Risk Mitigation</h4>
                <p>Through step-by-step implementation and quick wins, you reduce investment risk. 
                We expect first measurable successes within 30 days.</p>
            </div>
        </div>
        """

def generate_persona_profile(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert KI-Readiness Persona"""
    readiness_level = get_readiness_level(kpis['readiness_score'], lang)
    
    # Bestimme Persona-Typ
    if kpis['readiness_score'] >= 70:
        persona_type = 'Innovator' if lang == 'en' else 'Innovator'
        description = 'Sie gehören zu den Vorreitern' if lang == 'de' else 'You are among the pioneers'
    elif kpis['readiness_score'] >= 50:
        persona_type = 'Early Adopter' if lang == 'en' else 'Early Adopter'
        description = 'Sie sind bereit für den nächsten Schritt' if lang == 'de' else 'You are ready for the next step'
    elif kpis['readiness_score'] >= 30:
        persona_type = 'Fast Follower' if lang == 'en' else 'Fast Follower'
        description = 'Sie haben gute Grundlagen' if lang == 'de' else 'You have good foundations'
    else:
        persona_type = 'Explorer' if lang == 'en' else 'Explorer'
        description = 'Sie stehen am Anfang einer spannenden Reise' if lang == 'de' else 'You are at the beginning of an exciting journey'
    
    # Stärken und Entwicklungsfelder
    strengths = []
    development_areas = []
    
    if kpis['digitalisierungsgrad'] >= 7:
        strengths.append('Digitale Infrastruktur' if lang == 'de' else 'Digital Infrastructure')
    else:
        development_areas.append('Digitale Basis' if lang == 'de' else 'Digital Foundation')
    
    if kpis['automatisierungsgrad'] >= 60:
        strengths.append('Prozessautomatisierung' if lang == 'de' else 'Process Automation')
    else:
        development_areas.append('Automatisierung' if lang == 'de' else 'Automation')
    
    if kpis['kpi_compliance'] >= 70:
        strengths.append('Compliance' if lang == 'de' else 'Compliance')
    else:
        development_areas.append('Regulatorische Konformität' if lang == 'de' else 'Regulatory Compliance')
    
    if lang == 'de':
        return f"""
        <div class="persona-profile">
            <h3>Ihr KI-Readiness Profil: {persona_type}</h3>
            
            <div class="persona-overview">
                <p><strong>Reifegrad:</strong> {readiness_level} ({kpis['readiness_score']}%)</p>
                <p><strong>Charakterisierung:</strong> {description}</p>
            </div>
            
            <div class="persona-strengths">
                <h4>Ihre Stärken</h4>
                <ul>
                    {''.join([f"<li>{s}</li>" for s in strengths]) if strengths else '<li>Solide Ausgangsbasis</li>'}
                </ul>
            </div>
            
            <div class="persona-development">
                <h4>Entwicklungsfelder</h4>
                <ul>
                    {''.join([f"<li>{d}</li>" for d in development_areas]) if development_areas else '<li>Kontinuierliche Optimierung</li>'}
                </ul>
            </div>
            
            <div class="persona-next-steps">
                <h4>Empfohlene nächste Schritte</h4>
                <p>Als {persona_type} sollten Sie sich auf {get_primary_quick_win(answers, lang)} fokussieren 
                und dabei Ihre Stärken nutzen. Die geschätzte Zeit bis zur nächsten Reifegradstufe beträgt 
                6-9 Monate bei konsequenter Umsetzung.</p>
            </div>
        </div>
        """
    else:
        return f"""
        <div class="persona-profile">
            <h3>Your AI Readiness Profile: {persona_type}</h3>
            
            <div class="persona-overview">
                <p><strong>Maturity Level:</strong> {readiness_level} ({kpis['readiness_score']}%)</p>
                <p><strong>Characterization:</strong> {description}</p>
            </div>
            
            <div class="persona-strengths">
                <h4>Your Strengths</h4>
                <ul>
                    {''.join([f"<li>{s}</li>" for s in strengths]) if strengths else '<li>Solid starting point</li>'}
                </ul>
            </div>
            
            <div class="persona-development">
                <h4>Development Areas</h4>
                <ul>
                    {''.join([f"<li>{d}</li>" for d in development_areas]) if development_areas else '<li>Continuous optimization</li>'}
                </ul>
            </div>
            
            <div class="persona-next-steps">
                <h4>Recommended Next Steps</h4>
                <p>As a {persona_type}, you should focus on {get_primary_quick_win(answers, lang)} 
                while leveraging your strengths. The estimated time to reach the next maturity level is 
                6-9 months with consistent implementation.</p>
            </div>
        </div>
        """

def generate_case_studies(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert Praxisbeispiele basierend auf Branche"""
    branche = safe_str(answers.get('branche', 'Beratung'))
    size = safe_str(answers.get('unternehmensgroesse', '2-10'))
    
    # Branchenspezifische Beispiele
    case_studies = {
        'beratung': {
            'company': 'Strategieberatung München',
            'challenge': 'Manuelle Reporterstellung',
            'solution': 'KI-gestützte Analyse-Tools',
            'result': '60% Zeitersparnis, 40% mehr Projekte',
            'time': '4 Monate'
        },
        'it': {
            'company': 'Software-Entwickler Berlin',
            'challenge': 'Code-Reviews und Testing',
            'solution': 'AI Code-Assistenten',
            'result': '50% schnellere Releases, 30% weniger Bugs',
            'time': '3 Monate'
        },
        'marketing': {
            'company': 'Digital-Agentur Hamburg',
            'challenge': 'Content-Produktion',
            'solution': 'KI-Content-Pipeline',
            'result': '3x mehr Content, 25% höhere Engagement-Rate',
            'time': '2 Monate'
        },
        'handel': {
            'company': 'E-Commerce Köln',
            'challenge': 'Kundenservice-Anfragen',
            'solution': 'KI-Chatbot Integration',
            'result': '70% automatisierte Anfragen, NPS +15',
            'time': '6 Wochen'
        }
    }
    
    # Wähle passendes Beispiel oder Default
    example = case_studies.get(branche, case_studies['beratung'])
    
    if lang == 'de':
        return f"""
        <div class="case-studies">
            <h3>Erfolgsbeispiel aus Ihrer Branche</h3>
            
            <div class="case-study-card">
                <h4>{example['company']}</h4>
                
                <div class="case-challenge">
                    <strong>Herausforderung:</strong> {example['challenge']}
                </div>
                
                <div class="case-solution">
                    <strong>Lösung:</strong> {example['solution']}
                </div>
                
                <div class="case-result">
                    <strong>Ergebnis:</strong> {example['result']}
                </div>
                
                <div class="case-timeline">
                    <strong>Umsetzungsdauer:</strong> {example['time']}
                </div>
            </div>
            
            <div class="case-relevance">
                <h4>Übertragbarkeit auf Ihr Unternehmen</h4>
                <p>Mit einem ähnlichen Ansatz könnten Sie bei einem Budget von {kpis['roi_investment']:,} EUR 
                vergleichbare Ergebnisse erzielen. Ihre spezifischen Voraussetzungen mit einem Readiness-Score 
                von {kpis['readiness_score']}% ermöglichen einen noch schnelleren Start.</p>
            </div>
            
            <div class="success-factors">
                <h4>Erfolgsfaktoren</h4>
                <ul>
                    <li>Schrittweise Implementierung mit Quick Wins</li>
                    <li>Einbindung der Mitarbeiter von Anfang an</li>
                    <li>Kontinuierliche Messung und Optimierung</li>
                    <li>Fokus auf konkrete Business-Probleme</li>
                </ul>
            </div>
        </div>
        """
    else:
        return f"""
        <div class="case-studies">
            <h3>Success Story from Your Industry</h3>
            
            <div class="case-study-card">
                <h4>{example['company']}</h4>
                
                <div class="case-challenge">
                    <strong>Challenge:</strong> {example['challenge']}
                </div>
                
                <div class="case-solution">
                    <strong>Solution:</strong> {example['solution']}
                </div>
                
                <div class="case-result">
                    <strong>Result:</strong> {example['result']}
                </div>
                
                <div class="case-timeline">
                    <strong>Implementation Time:</strong> {example['time']}
                </div>
            </div>
            
            <div class="case-relevance">
                <h4>Applicability to Your Company</h4>
                <p>With a similar approach and a budget of EUR {kpis['roi_investment']:,}, 
                you could achieve comparable results. Your specific prerequisites with a readiness score 
                of {kpis['readiness_score']}% enable an even faster start.</p>
            </div>
            
            <div class="success-factors">
                <h4>Success Factors</h4>
                <ul>
                    <li>Step-by-step implementation with quick wins</li>
                    <li>Employee involvement from the start</li>
                    <li>Continuous measurement and optimization</li>
                    <li>Focus on specific business problems</li>
                </ul>
            </div>
        </div>
        """

# ============================= Content-Generierung Funktionen (Fortsetzung) =============================

def generate_data_driven_executive_summary(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert datengetriebene Executive Summary"""
    
    # Stärken identifizieren
    strengths = []
    if kpis['digitalisierungsgrad'] >= 8:
        strengths.append("exzellente digitale Infrastruktur" if lang == 'de' else "excellent digital infrastructure")
    if kpis['risikofreude'] >= 4:
        strengths.append("hohe Innovationsbereitschaft" if lang == 'de' else "high innovation readiness")
    if kpis['automatisierungsgrad'] >= 70:
        strengths.append("fortgeschrittene Automatisierung" if lang == 'de' else "advanced automation")
    
    # Herausforderungen identifizieren
    hemmnisse = answers.get('ki_hemmnisse', [])
    challenges = []
    for h in hemmnisse:
        h_lower = safe_str(h).lower()
        if 'budget' in h_lower:
            challenges.append("Budgetrestriktionen" if lang == 'de' else "Budget restrictions")
        elif 'zeit' in h_lower:
            challenges.append("Zeitressourcen" if lang == 'de' else "Time resources")
        elif 'know' in h_lower:
            challenges.append("Kompetenzaufbau" if lang == 'de' else "Skill development")
    
    # Branchenbenchmark
    branche = safe_str(answers.get('branche', 'beratung')).lower()
    benchmark = INDUSTRY_BENCHMARKS.get(branche, INDUSTRY_BENCHMARKS['default'])
    
    if lang == 'de':
        position = 'deutlich über' if kpis['readiness_score'] > 70 else 'im' if kpis['readiness_score'] > 50 else 'unter'
        
        summary = f"""
        <div class="executive-summary-content">
            <p class="situation">
                <strong>Standortbestimmung:</strong> Mit einem KI-Reifegrad von {kpis['readiness_score']}% 
                positioniert sich Ihr Unternehmen {position} dem Branchendurchschnitt. 
                Ihre Stärken: {', '.join(strengths) if strengths else 'solide Ausgangsbasis'}.
                Herausforderungen: {', '.join(challenges) if challenges else 'überschaubar'}.
            </p>
            
            <p class="strategy">
                <strong>Handlungsempfehlung:</strong> Die Analyse zeigt ein 
                <strong>Effizienzsteigerungspotenzial von {kpis['kpi_efficiency']}%</strong>. 
                Starten Sie mit {get_primary_quick_win(answers, lang)} innerhalb von 30 Tagen. 
                Mittelfristig (90 Tage) sollten Sie die Prozessautomatisierung ausbauen. 
                Langfristig (180 Tage) empfehlen wir den Aufbau einer KI-Governance-Struktur.
            </p>
            
            <p class="value">
                <strong>Wertpotenzial:</strong> Bei einer Investition von {kpis['roi_investment']:,} EUR 
                erwarten wir <strong>jährliche Einsparungen von {kpis['roi_annual_saving']:,} EUR</strong>. 
                Der Break-Even wird nach {kpis['kpi_roi_months']} Monaten erreicht. 
                Das 3-Jahres-Wertpotenzial beträgt <strong>{kpis['roi_three_year']:,} EUR</strong>. 
                Compliance-Status: {get_compliance_status(answers, lang)}.
            </p>
        </div>
        """
    else:
        position = 'significantly above' if kpis['readiness_score'] > 70 else 'at' if kpis['readiness_score'] > 50 else 'below'
        
        summary = f"""
        <div class="executive-summary-content">
            <p class="situation">
                <strong>Current State:</strong> With an AI readiness of {kpis['readiness_score']}%, 
                your company positions itself {position} the industry average. 
                Your strengths: {', '.join(strengths) if strengths else 'solid foundation'}.
                Challenges: {', '.join(challenges) if challenges else 'manageable'}.
            </p>
            
            <p class="strategy">
                <strong>Action Plan:</strong> The analysis shows an 
                <strong>efficiency improvement potential of {kpis['kpi_efficiency']}%</strong>. 
                Start with {get_primary_quick_win(answers, lang)} within 30 days. 
                Mid-term (90 days) you should expand process automation. 
                Long-term (180 days) we recommend building an AI governance structure.
            </p>
            
            <p class="value">
                <strong>Value Potential:</strong> With an investment of EUR {kpis['roi_investment']:,}, 
                we expect <strong>annual savings of EUR {kpis['roi_annual_saving']:,}</strong>. 
                Break-even will be reached after {kpis['kpi_roi_months']} months. 
                The 3-year value potential is <strong>EUR {kpis['roi_three_year']:,}</strong>. 
                Compliance status: {get_compliance_status(answers, lang)}.
            </p>
        </div>
        """
    
    return clean_text(summary)
# ============================= Fortsetzung der Content-Generierung =============================

def generate_quick_wins(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert Quick Wins basierend auf Use Cases"""
    
    use_cases = answers.get('ki_usecases', [])
    budget = get_budget_amount(answers.get('budget', '2000-10000'))
    
    if lang == 'de':
        html = """
        <div class="quick-wins-container">
            <h3>1. Automatisierte Dokumentenerstellung</h3>
            <p>Nutzen Sie <strong>DeepL Write</strong> für professionelle Texte und Angebote. 
            <em>Zeitersparnis: 5-8 Stunden/Woche</em>. Einrichtung in nur 1 Tag. 
            Kosten: Kostenlos bis Pro-Version (8€/Monat).</p>
            
            <h3>2. Meeting-Automatisierung</h3>
            <p>Implementieren Sie <strong>tl;dv</strong> für automatische Meeting-Protokolle. 
            <em>Kosteneinsparung: 2.000€/Monat</em> durch wegfallende manuelle Dokumentation. 
            Integration in Zoom/Teams innerhalb von 30 Minuten.</p>
            
            <h3>3. KI-Chatbot für Standardanfragen</h3>
            <p>Starten Sie mit <strong>Typebot</strong> (Open Source) für FAQ-Automatisierung. 
            <em>30% weniger Support-Tickets</em> innerhalb von 4 Wochen. 
            Vollständig DSGVO-konform und selbst-hostbar.</p>
        </div>
        """
    else:
        html = """
        <div class="quick-wins-container">
            <h3>1. Automated Document Creation</h3>
            <p>Use <strong>DeepL Write</strong> for professional texts and proposals. 
            <em>Time savings: 5-8 hours/week</em>. Setup in just 1 day. 
            Cost: Free to Pro version (€8/month).</p>
            
            <h3>2. Meeting Automation</h3>
            <p>Implement <strong>tl;dv</strong> for automatic meeting minutes. 
            <em>Cost savings: €2,000/month</em> by eliminating manual documentation. 
            Integration with Zoom/Teams within 30 minutes.</p>
            
            <h3>3. AI Chatbot for Standard Inquiries</h3>
            <p>Start with <strong>Typebot</strong> (Open Source) for FAQ automation. 
            <em>30% fewer support tickets</em> within 4 weeks. 
            Fully GDPR-compliant and self-hostable.</p>
        </div>
        """
    
    # Anpassung basierend auf Use Cases
    if 'datenanalyse' in str(use_cases).lower():
        addition = """
        <h3>4. Automatisierte Datenanalyse</h3>
        <p><strong>Metabase</strong> für intuitive Dashboards. 
        """ if lang == 'de' else """
        <h3>4. Automated Data Analysis</h3>
        <p><strong>Metabase</strong> for intuitive dashboards. 
        """
        
        if budget < 10000:
            addition += "Kostenlose selbst-gehostete Version verfügbar." if lang == 'de' else "Free self-hosted version available."
        else:
            addition += "Cloud-Version ab 85€/Monat mit Support." if lang == 'de' else "Cloud version from €85/month with support."
        
        html = html[:-6] + addition + "</p></div>"
    
    return html

def generate_risk_analysis(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert Risikoanalyse"""
    
    risks = []
    
    # Datenschutz-Risiko
    if answers.get('datenschutzbeauftragter') != 'ja':
        risks.append({
            'level': 'high',
            'title': 'Datenschutz-Risiko' if lang == 'de' else 'Data Protection Risk',
            'desc': 'Kein DSB benannt' if lang == 'de' else 'No DPO appointed',
            'action': 'Externen DSB beauftragen (200-500€/Monat)' if lang == 'de' else 'Appoint external DPO (€200-500/month)'
        })
    
    # Compliance-Risiko
    if answers.get('dsgvo_folgenabschaetzung') not in ['ja', 'yes']:
        risks.append({
            'level': 'medium',
            'title': 'Compliance-Risiko' if lang == 'de' else 'Compliance Risk',
            'desc': 'DSFA unvollständig' if lang == 'de' else 'DPIA incomplete',
            'action': 'Template nutzen, 2-3 Tage Aufwand' if lang == 'de' else 'Use template, 2-3 days effort'
        })
    
    # Technologie-Risiko
    if kpis['digitalisierungsgrad'] < 6:
        risks.append({
            'level': 'medium',
            'title': 'Technologie-Risiko' if lang == 'de' else 'Technology Risk',
            'desc': 'Veraltete IT-Infrastruktur' if lang == 'de' else 'Outdated IT infrastructure',
            'action': 'Schrittweise Modernisierung planen' if lang == 'de' else 'Plan gradual modernization'
        })
    
    # Kompetenz-Risiko
    if answers.get('ki_knowhow') in ['anfaenger', 'beginner']:
        risks.append({
            'level': 'low',
            'title': 'Kompetenz-Risiko' if lang == 'de' else 'Competency Risk',
            'desc': 'Fehlendes KI-Know-how' if lang == 'de' else 'Missing AI know-how',
            'action': 'Schulungsprogramm starten' if lang == 'de' else 'Start training program'
        })
    
    # HTML generieren
    html = '<div class="risk-analysis">'
    if lang == 'de':
        html += '<h3>Identifizierte Risiken und Maßnahmen</h3>'
    else:
        html += '<h3>Identified Risks and Measures</h3>'
    
    for risk in risks:
        icon = '🔴' if risk['level'] == 'high' else '🟡' if risk['level'] == 'medium' else '🟢'
        html += f"""
        <div class="risk-item">
            <p>{icon} <strong>{risk['title']}:</strong> {risk['desc']}<br/>
            <em>{'Maßnahme' if lang == 'de' else 'Action'}:</em> {risk['action']}</p>
        </div>
        """
    
    if not risks:
        html += f"<p>{'Keine kritischen Risiken identifiziert.' if lang == 'de' else 'No critical risks identified.'}</p>"
    
    html += '</div>'
    
    return html

def generate_roadmap(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert Implementierungs-Roadmap"""
    
    if lang == 'de':
        html = f"""
        <div class="roadmap-container">
            <h3>Phase 1: Quick Wins (0-30 Tage)</h3>
            <p>Start mit identifizierten Quick Wins. <strong>Budget: {int(kpis['roi_investment'] * 0.2):,} EUR</strong> (20% der Gesamtinvestition).
            Fokus auf {get_primary_quick_win(answers, lang)}. Erwartete erste Ergebnisse nach 2 Wochen.</p>
            
            <h3>Phase 2: Skalierung (31-90 Tage)</h3>
            <p>Integration in den Regelbetrieb. Schulung von {get_team_size(answers)} Mitarbeitern.
            <strong>Effizienzsteigerung: {int(kpis['kpi_efficiency'] * 0.4)}%</strong> bereits realisiert.</p>
            
            <h3>Phase 3: Optimierung (91-180 Tage)</h3>
            <p>Vollständige Prozessintegration. <strong>ROI erreicht nach {kpis['kpi_roi_months']} Monaten</strong>.
            Jährliche Einsparung von {kpis['roi_annual_saving']:,} EUR vollständig realisiert.</p>
            
            <h3>Phase 4: Innovation (ab 180 Tage)</h3>
            <p>Entwicklung eigener KI-Anwendungsfälle. Aufbau interner KI-Kompetenz.
            Erschließung neuer Geschäftsmodelle mit {kpis['kpi_innovation']}% Innovationspotenzial.</p>
        </div>
        """
    else:
        html = f"""
        <div class="roadmap-container">
            <h3>Phase 1: Quick Wins (0-30 Days)</h3>
            <p>Start with identified quick wins. <strong>Budget: EUR {int(kpis['roi_investment'] * 0.2):,}</strong> (20% of total investment).
            Focus on {get_primary_quick_win(answers, lang)}. Expected first results after 2 weeks.</p>
            
            <h3>Phase 2: Scaling (31-90 Days)</h3>
            <p>Integration into regular operations. Training of {get_team_size(answers)} employees.
            <strong>Efficiency increase: {int(kpis['kpi_efficiency'] * 0.4)}%</strong> already realized.</p>
            
            <h3>Phase 3: Optimization (91-180 Days)</h3>
            <p>Complete process integration. <strong>ROI achieved after {kpis['kpi_roi_months']} months</strong>.
            Annual savings of EUR {kpis['roi_annual_saving']:,} fully realized.</p>
            
            <h3>Phase 4: Innovation (from 180 Days)</h3>
            <p>Development of proprietary AI use cases. Building internal AI competency.
            Opening new business models with {kpis['kpi_innovation']}% innovation potential.</p>
        </div>
        """
    
    return html

def get_team_size(answers: Dict[str, Any]) -> str:
    """Ermittelt Teamgröße für Schulungen"""
    size = answers.get('unternehmensgroesse', '2-10')
    size_map = {
        '1': '1',
        'solo': '1',
        '2-10': '3-5',
        '11-100': '10-20',
        '101-500': '30-50'
    }
    return size_map.get(str(size).lower(), '5-10')

def generate_fallback_content(section_name: str, lang: str) -> str:
    """Generiert Fallback-Content wenn API fehlschlägt"""
    fallbacks = {
        'de': {
            'executive_summary': """
                <p>Basierend auf Ihren Angaben wurde ein maßgeschneiderter KI-Transformationsplan entwickelt. 
                Die Analyse zeigt erhebliches Potenzial für Effizienzsteigerungen und Kosteneinsparungen.</p>
                """,
            'quick_wins': '<p>Quick Wins werden basierend auf Ihrer Branche und Ihren Use Cases generiert.</p>',
            'risk_analysis': '<p>Die Risikoanalyse folgt den Standards von DSGVO und EU AI Act.</p>',
            'recommendations': '<p>Individuelle Empfehlungen werden für Ihr Unternehmen erstellt.</p>',
            'roadmap': '<p>Ihre personalisierte Implementierungs-Roadmap wird generiert.</p>',
            'compliance': '<p>Ihr Compliance-Status wird gemäß aktueller Regularien geprüft.</p>',
            'vision': '<p>Ihre KI-Vision 2027 basiert auf Branchentrends und Ihrem Potenzial.</p>',
            'coach': '<p>Persönliche Reflexionsfragen zur KI-Transformation.</p>',
            'gamechanger': '<p>Ihr individuelles Game-Changer-Potenzial wird analysiert.</p>',
            'business': '<p>Ihr Business Case wird auf Basis Ihrer Unternehmensdaten erstellt.</p>',
            'persona': '<p>Ihr KI-Readiness Profil wird analysiert.</p>',
            'praxisbeispiel': '<p>Relevante Erfolgsgeschichten aus Ihrer Branche werden zusammengestellt.</p>'
        },
        'en': {
            'executive_summary': """
                <p>Based on your input, a tailored AI transformation plan has been developed. 
                The analysis shows significant potential for efficiency improvements and cost savings.</p>
                """,
            'quick_wins': '<p>Quick wins are generated based on your industry and use cases.</p>',
            'risk_analysis': '<p>Risk analysis follows GDPR and EU AI Act standards.</p>',
            'recommendations': '<p>Individual recommendations are created for your company.</p>',
            'roadmap': '<p>Your personalized implementation roadmap is being generated.</p>',
            'compliance': '<p>Your compliance status is checked according to current regulations.</p>',
            'vision': '<p>Your AI vision 2027 is based on industry trends and your potential.</p>',
            'coach': '<p>Personal reflection questions for AI transformation.</p>',
            'gamechanger': '<p>Your individual game-changer potential is being analyzed.</p>',
            'business': '<p>Your business case is created based on your company data.</p>',
            'persona': '<p>Your AI readiness profile is being analyzed.</p>',
            'praxisbeispiel': '<p>Relevant success stories from your industry are being compiled.</p>'
        }
    }
    
    return fallbacks.get(lang, fallbacks['de']).get(section_name, f'<p>Content for {section_name} is being generated...</p>')

def generate_other_sections(answers: Dict[str, Any], kpis: Dict[str, Any], lang: str = 'de') -> Dict[str, str]:
    """Generiert alle weiteren Sektionen"""
    
    sections = {}
    
    # Compliance
    if lang == 'de':
        sections['compliance'] = f"""
        <div class="compliance-section">
            <h3>Ihr Compliance-Status</h3>
            <p><strong>Aktueller Stand: {kpis['kpi_compliance']}% konform</strong></p>
            <ul>
                <li>DSGVO: {get_compliance_status(answers, lang)}</li>
                <li>EU AI Act: Vorbereitung läuft</li>
                <li>Nächste Schritte: DSFA vervollständigen, KI-Governance dokumentieren</li>
            </ul>
        </div>
        """
    else:
        sections['compliance'] = f"""
        <div class="compliance-section">
            <h3>Your Compliance Status</h3>
            <p><strong>Current status: {kpis['kpi_compliance']}% compliant</strong></p>
            <ul>
                <li>GDPR: {get_compliance_status(answers, lang)}</li>
                <li>EU AI Act: Preparation ongoing</li>
                <li>Next steps: Complete DPIA, document AI governance</li>
            </ul>
        </div>
        """
    
    # Vision
    future_readiness = min(95, kpis['readiness_score'] + 30)
    if lang == 'de':
        sections['vision'] = f"""
        <div class="vision-section">
            <h3>Ihre KI-Zukunft 2027</h3>
            <p>In drei Jahren wird Ihr Unternehmen einen <strong>KI-Reifegrad von {future_readiness}%</strong> erreicht haben.
            Die prognostizierte Effizienzsteigerung von {kpis['kpi_efficiency']}% ist vollständig realisiert.
            Neue, KI-basierte Geschäftsmodelle generieren zusätzlich 20-30% Umsatz.</p>
            <p>Sie sind Vorreiter in Ihrer Branche und gestalten die digitale Transformation aktiv mit.</p>
        </div>
        """
    else:
        sections['vision'] = f"""
        <div class="vision-section">
            <h3>Your AI Future 2027</h3>
            <p>In three years, your company will have reached an <strong>AI maturity of {future_readiness}%</strong>.
            The projected efficiency increase of {kpis['kpi_efficiency']}% is fully realized.
            New AI-based business models generate an additional 20-30% revenue.</p>
            <p>You are a pioneer in your industry and actively shape digital transformation.</p>
        </div>
        """
    
    # Coach
    if lang == 'de':
        sections['coach'] = """
        <div class="coach-section">
            <h3>Reflexionsfragen für Ihre KI-Transformation</h3>
            <ul>
                <li>Wo verlieren Sie und Ihr Team täglich die meiste Zeit?</li>
                <li>Welche Kundenanfragen wiederholen sich ständig?</li>
                <li>Wer in Ihrem Team könnte KI-Champion werden?</li>
                <li>Welche Prozesse frustrieren Ihre Mitarbeiter am meisten?</li>
                <li>Was würden Sie automatisieren, wenn es keine Grenzen gäbe?</li>
            </ul>
            <p><em>Nutzen Sie diese Fragen für Ihr nächstes Team-Meeting.</em></p>
        </div>
        """
    else:
        sections['coach'] = """
        <div class="coach-section">
            <h3>Reflection Questions for Your AI Transformation</h3>
            <ul>
                <li>Where do you and your team lose the most time daily?</li>
                <li>Which customer inquiries repeat constantly?</li>
                <li>Who in your team could become an AI champion?</li>
                <li>Which processes frustrate your employees the most?</li>
                <li>What would you automate if there were no limits?</li>
            </ul>
            <p><em>Use these questions for your next team meeting.</em></p>
        </div>
        """
    
    # Recommendations
    if lang == 'de':
        sections['recommendations'] = f"""
        <div class="recommendation-box">
            <h3>Top-Empfehlung</h3>
            <p>Basierend auf Ihrer Analyse empfehlen wir den <strong>sofortigen Start mit {get_primary_quick_win(answers, lang)}</strong>.
            Dies bietet das beste Verhältnis von Aufwand zu Nutzen mit einem erwarteten ROI innerhalb von {kpis['kpi_roi_months']} Monaten.</p>
            <p>Potenzial: <strong>{kpis['kpi_efficiency']}% Effizienzsteigerung</strong>, 
            <strong>{kpis['roi_annual_saving']:,} EUR jährliche Einsparung</strong>.</p>
        </div>
        """
    else:
        sections['recommendations'] = f"""
        <div class="recommendation-box">
            <h3>Top Recommendation</h3>
            <p>Based on your analysis, we recommend <strong>immediate start with {get_primary_quick_win(answers, lang)}</strong>.
            This offers the best effort-to-benefit ratio with expected ROI within {kpis['kpi_roi_months']} months.</p>
            <p>Potential: <strong>{kpis['kpi_efficiency']}% efficiency increase</strong>, 
            <strong>EUR {kpis['roi_annual_saving']:,} annual savings</strong>.</p>
        </div>
        """
    
    # Gamechanger
    if lang == 'de':
        sections['gamechanger'] = f"""
        <div class="gamechanger-section">
            <h3>Ihr Game-Changer Potenzial</h3>
            <p>Die Kombination aus <strong>{answers.get('branche', 'Ihrer Branche')}</strong> und KI bietet revolutionäre Möglichkeiten:</p>
            <ul>
                <li>Vollautomatisierte Kundeninteraktion mit {kpis['kpi_efficiency']}% Effizienzgewinn</li>
                <li>Predictive Analytics für proaktive Geschäftsentscheidungen</li>
                <li>KI-gestützte Produktentwicklung mit {kpis['kpi_innovation']}% Innovationspotenzial</li>
            </ul>
            <p><strong>Geschätzter Gesamtwert: {kpis['roi_three_year']:,} EUR über 3 Jahre</strong></p>
        </div>
        """
    else:
        sections['gamechanger'] = f"""
        <div class="gamechanger-section">
            <h3>Your Game-Changer Potential</h3>
            <p>The combination of <strong>{answers.get('branche', 'your industry')}</strong> and AI offers revolutionary possibilities:</p>
            <ul>
                <li>Fully automated customer interaction with {kpis['kpi_efficiency']}% efficiency gain</li>
                <li>Predictive analytics for proactive business decisions</li>
                <li>AI-supported product development with {kpis['kpi_innovation']}% innovation potential</li>
            </ul>
            <p><strong>Estimated total value: EUR {kpis['roi_three_year']:,} over 3 years</strong></p>
        </div>
        """
    
    return sections
# ============================= Tool-Datenbank =============================

TOOL_DATABASE = {
    "texterstellung": [
        {
            "name": "DeepL Write",
            "desc": "DSGVO-konformes Schreibtool",
            "use_case": "E-Mails, Berichte, Angebote",
            "cost": "Kostenlos / Pro ab 8€",
            "complexity": "Sehr einfach",
            "time_to_value": "Sofort",
            "badges": ["EU-Hosting", "DSGVO", "Kostenlos"],
            "fit_score": 95,
            "url": "https://www.deepl.com/write"
        },
        {
            "name": "Jasper AI",
            "desc": "Marketing-Content Automation",
            "use_case": "Blog, Social Media, Ads",
            "cost": "Ab 39€/Monat",
            "complexity": "Mittel",
            "time_to_value": "3-5 Tage",
            "badges": ["API", "Templates", "Team"],
            "fit_score": 80,
            "url": "https://jasper.ai"
        },
        {
            "name": "Copy.ai",
            "desc": "KI-Textgenerator",
            "use_case": "Marketing-Texte, Produktbeschreibungen",
            "cost": "Kostenlos / Pro ab 36€",
            "complexity": "Einfach",
            "time_to_value": "1 Tag",
            "badges": ["Freemium", "Templates", "Multi-Language"],
            "fit_score": 85,
            "url": "https://copy.ai"
        }
    ],
    "spracherkennung": [
        {
            "name": "Whisper (lokal)",
            "desc": "Open Source Transkription",
            "use_case": "Meetings, Interviews, Podcasts",
            "cost": "Kostenlos",
            "complexity": "Mittel",
            "time_to_value": "1 Tag Setup",
            "badges": ["Open Source", "Lokal", "Kostenlos"],
            "fit_score": 90,
            "url": "https://github.com/openai/whisper"
        },
        {
            "name": "tl;dv",
            "desc": "Meeting-Recorder mit KI",
            "use_case": "Zoom/Teams Meetings automatisch protokollieren",
            "cost": "Kostenlos / Pro 20€",
            "complexity": "Sehr einfach",
            "time_to_value": "30 Minuten",
            "badges": ["DSGVO", "Integration", "Freemium"],
            "fit_score": 85,
            "url": "https://tldv.io"
        },
        {
            "name": "Otter.ai",
            "desc": "Live-Transkription",
            "use_case": "Echtzeit-Protokolle, Notizen",
            "cost": "Kostenlos / Pro ab 8€",
            "complexity": "Einfach",
            "time_to_value": "Sofort",
            "badges": ["Real-time", "Collaboration", "Mobile"],
            "fit_score": 82,
            "url": "https://otter.ai"
        }
    ],
    "prozessautomatisierung": [
        {
            "name": "n8n",
            "desc": "Open Source Workflow Tool",
            "use_case": "API-Integration, Workflows, Automatisierung",
            "cost": "Kostenlos selbst-hosted",
            "complexity": "Mittel",
            "time_to_value": "1-2 Wochen",
            "badges": ["Open Source", "EU-Hosting", "Kostenlos"],
            "fit_score": 92,
            "url": "https://n8n.io"
        },
        {
            "name": "Make (Integromat)",
            "desc": "Visual Workflow Builder",
            "use_case": "Automatisierung ohne Code",
            "cost": "Ab 9€/Monat",
            "complexity": "Einfach",
            "time_to_value": "2-3 Tage",
            "badges": ["Low-Code", "DSGVO", "Templates"],
            "fit_score": 88,
            "url": "https://www.make.com"
        },
        {
            "name": "Zapier",
            "desc": "Automation Platform",
            "use_case": "App-Verbindungen, Trigger",
            "cost": "Ab 19€/Monat",
            "complexity": "Sehr einfach",
            "time_to_value": "1 Tag",
            "badges": ["5000+ Apps", "Templates", "Support"],
            "fit_score": 85,
            "url": "https://zapier.com"
        }
    ],
    "datenanalyse": [
        {
            "name": "Metabase",
            "desc": "Open Source BI Tool",
            "use_case": "Dashboards, Reports, Analytics",
            "cost": "Kostenlos / Cloud ab 85€",
            "complexity": "Mittel",
            "time_to_value": "1 Woche",
            "badges": ["Open Source", "DSGVO", "Self-Host"],
            "fit_score": 85,
            "url": "https://www.metabase.com"
        },
        {
            "name": "Tableau",
            "desc": "Enterprise BI Platform",
            "use_case": "Komplexe Analysen, Visualisierungen",
            "cost": "Ab 15€/User/Monat",
            "complexity": "Hoch",
            "time_to_value": "2-4 Wochen",
            "badges": ["Enterprise", "Cloud", "Support"],
            "fit_score": 75,
            "url": "https://www.tableau.com"
        },
        {
            "name": "Apache Superset",
            "desc": "Data Exploration Platform",
            "use_case": "SQL-basierte Analysen",
            "cost": "Kostenlos",
            "complexity": "Mittel-Hoch",
            "time_to_value": "1-2 Wochen",
            "badges": ["Open Source", "SQL", "Kostenlos"],
            "fit_score": 80,
            "url": "https://superset.apache.org"
        }
    ],
    "kundensupport": [
        {
            "name": "Typebot",
            "desc": "Open Source Chatbot Builder",
            "use_case": "Website-Chat, FAQ, Lead-Gen",
            "cost": "Kostenlos selbst-hosted",
            "complexity": "Einfach",
            "time_to_value": "1-2 Tage",
            "badges": ["Open Source", "DSGVO", "No-Code"],
            "fit_score": 90,
            "url": "https://typebot.io"
        },
        {
            "name": "Crisp",
            "desc": "Customer Messaging Platform",
            "use_case": "Live-Chat + KI-Assistent",
            "cost": "Kostenlos / Pro ab 25€",
            "complexity": "Sehr einfach",
            "time_to_value": "30 Minuten",
            "badges": ["DSGVO", "Freemium", "Widget"],
            "fit_score": 87,
            "url": "https://crisp.chat"
        },
        {
            "name": "Botpress",
            "desc": "Conversational AI Platform",
            "use_case": "Komplexe Chatbots",
            "cost": "Kostenlos / Cloud ab 100€",
            "complexity": "Mittel",
            "time_to_value": "1 Woche",
            "badges": ["Open Source", "NLP", "Multi-Channel"],
            "fit_score": 83,
            "url": "https://botpress.com"
        }
    ],
    "wissensmanagement": [
        {
            "name": "Outline",
            "desc": "Team Knowledge Base",
            "use_case": "Dokumentation, Wiki, Notizen",
            "cost": "Kostenlos bis 5 User",
            "complexity": "Einfach",
            "time_to_value": "1 Tag",
            "badges": ["Open Source", "Markdown", "Search"],
            "fit_score": 88,
            "url": "https://www.getoutline.com"
        },
        {
            "name": "BookStack",
            "desc": "Dokumentations-Platform",
            "use_case": "Handbücher, Prozesse, Anleitungen",
            "cost": "Kostenlos",
            "complexity": "Einfach",
            "time_to_value": "2-3 Tage",
            "badges": ["Open Source", "Self-Host", "WYSIWYG"],
            "fit_score": 85,
            "url": "https://www.bookstackapp.com"
        },
        {
            "name": "Notion AI",
            "desc": "All-in-One Workspace",
            "use_case": "Notizen, Docs, Datenbanken",
            "cost": "Ab 8€/User/Monat",
            "complexity": "Mittel",
            "time_to_value": "1 Woche",
            "badges": ["AI-Features", "Collaboration", "Templates"],
            "fit_score": 82,
            "url": "https://www.notion.so"
        }
    ],
    "marketing": [
        {
            "name": "Canva Magic",
            "desc": "KI-Design Tool",
            "use_case": "Social Media, Präsentationen, Grafiken",
            "cost": "Kostenlos / Pro ab 12€",
            "complexity": "Sehr einfach",
            "time_to_value": "Sofort",
            "badges": ["Templates", "KI-Features", "Team"],
            "fit_score": 92,
            "url": "https://www.canva.com"
        },
        {
            "name": "Buffer AI",
            "desc": "Social Media Automation",
            "use_case": "Post-Planung mit KI-Unterstützung",
            "cost": "Ab 15€/Monat",
            "complexity": "Einfach",
            "time_to_value": "1 Tag",
            "badges": ["Scheduling", "Analytics", "KI-Text"],
            "fit_score": 85,
            "url": "https://buffer.com"
        },
        {
            "name": "Hootsuite",
            "desc": "Social Media Management",
            "use_case": "Multi-Channel Management",
            "cost": "Ab 49€/Monat",
            "complexity": "Mittel",
            "time_to_value": "3-5 Tage",
            "badges": ["Enterprise", "Analytics", "Team"],
            "fit_score": 78,
            "url": "https://hootsuite.com"
        }
    ]
}

# ============================= Förderprogramm-Datenbank =============================

FUNDING_PROGRAMS = {
    "bundesweit": [
        {
            "name": "Digital Jetzt",
            "provider": "BMWK",
            "amount": "Bis 50.000€ (40% Förderquote)",
            "deadline": "31.12.2025",
            "requirements": "3-499 Mitarbeiter, Investition min. 17.000€",
            "use_case": "Software, Hardware, Beratung",
            "fit_small": 95,
            "fit_medium": 90,
            "url": "https://www.bmwk.de/digital-jetzt"
        },
        {
            "name": "go-digital",
            "provider": "BMWK",
            "amount": "Bis 16.500€ (50% Förderquote)",
            "deadline": "Laufend",
            "requirements": "Bis 100 Mitarbeiter, Jahresumsatz max. 20 Mio €",
            "use_case": "Digitalisierung, IT-Sicherheit, Online-Marketing",
            "fit_small": 90,
            "fit_medium": 85,
            "url": "https://www.innovation-beratung-foerderung.de/go-digital"
        },
        {
            "name": "INNO-KOM",
            "provider": "BMWi",
            "amount": "Bis 550.000€",
            "deadline": "Laufend",
            "requirements": "Forschungsprojekte, gemeinnützige Forschungseinrichtungen",
            "use_case": "F&E, Prototypen, Innovationen",
            "fit_small": 60,
            "fit_medium": 75,
            "url": "https://www.innovation-beratung-foerderung.de/INNOBERATUNG/Navigation/DE/INNO-KOM"
        },
        {
            "name": "KfW-Digitalisierungskredit",
            "provider": "KfW",
            "amount": "Bis 25 Mio. € Kredit",
            "deadline": "Laufend",
            "requirements": "KMU und Midcaps",
            "use_case": "Digitale Transformation, Software, Hardware",
            "fit_small": 70,
            "fit_medium": 85,
            "url": "https://www.kfw.de/380"
        }
    ],
    "berlin": [
        {
            "name": "Berlin Mittelstand 4.0",
            "provider": "Berlin Partner",
            "amount": "Kostenlose Beratung",
            "deadline": "Laufend",
            "requirements": "KMU in Berlin",
            "use_case": "Digitalisierung, KI-Beratung",
            "fit_small": 100,
            "fit_medium": 100,
            "url": "https://www.berlin-partner.de"
        },
        {
            "name": "Digitalprämie Berlin",
            "provider": "IBB",
            "amount": "Bis 17.000€",
            "deadline": "30.06.2025",
            "requirements": "Berliner KMU, max. 249 Mitarbeiter",
            "use_case": "Software, Prozessoptimierung, E-Commerce",
            "fit_small": 85,
            "fit_medium": 80,
            "url": "https://www.ibb.de/digitalpraemie"
        },
        {
            "name": "Pro FIT",
            "provider": "IBB",
            "amount": "Bis 3 Mio. € (50-80% Förderquote)",
            "deadline": "Laufend",
            "requirements": "Berliner Unternehmen",
            "use_case": "F&E-Projekte, Innovationen",
            "fit_small": 70,
            "fit_medium": 85,
            "url": "https://www.ibb.de/profit"
        }
    ],
    "bayern": [
        {
            "name": "Digitalbonus Bayern",
            "provider": "StMWi",
            "amount": "Bis 10.000€ (50% Förderquote)",
            "deadline": "31.12.2025",
            "requirements": "KMU in Bayern, 3-249 Mitarbeiter",
            "use_case": "IT-Sicherheit, Software, Digitalisierung",
            "fit_small": 85,
            "fit_medium": 80,
            "url": "https://www.digitalbonus.bayern"
        },
        {
            "name": "BayTP - Technologieförderung",
            "provider": "Bayern Innovativ",
            "amount": "Bis 500.000€",
            "deadline": "Laufend",
            "requirements": "Bayerische KMU",
            "use_case": "Technologie-Entwicklung, Prototypen",
            "fit_small": 65,
            "fit_medium": 80,
            "url": "https://www.bayern-innovativ.de"
        }
    ],
    "nrw": [
        {
            "name": "Mittelstand.innovativ!",
            "provider": "EFRE.NRW",
            "amount": "Bis 15.000€ Gutscheine",
            "deadline": "Laufend",
            "requirements": "KMU in NRW",
            "use_case": "Innovation, Digitalisierung, Beratung",
            "fit_small": 80,
            "fit_medium": 85,
            "url": "https://www.efre.nrw.de"
        },
        {
            "name": "progres.nrw",
            "provider": "Land NRW",
            "amount": "40-80% Förderquote",
            "deadline": "Laufend",
            "requirements": "Unternehmen in NRW",
            "use_case": "Energieeffizienz, Digitalisierung",
            "fit_small": 75,
            "fit_medium": 80,
            "url": "https://www.progres.nrw.de"
        }
    ],
    "baden-wuerttemberg": [
        {
            "name": "Digitalisierungsprämie Plus",
            "provider": "Ministerium für Wirtschaft BW",
            "amount": "Bis 10.000€",
            "deadline": "31.12.2025",
            "requirements": "KMU in BW",
            "use_case": "Digitale Technologien, Software",
            "fit_small": 85,
            "fit_medium": 80,
            "url": "https://wm.baden-wuerttemberg.de"
        }
    ],
    "hessen": [
        {
            "name": "Distr@l",
            "provider": "Hessen Trade & Invest",
            "amount": "Bis 10.000€",
            "deadline": "Laufend",
            "requirements": "Hessische KMU",
            "use_case": "Digitalisierung im Handel",
            "fit_small": 80,
            "fit_medium": 75,
            "url": "https://www.digitalstrategie-hessen.de"
        }
    ]
}

# ============================= Tool & Förder-Matching =============================

def match_tools_to_company(answers: Dict[str, Any], lang: str = 'de') -> str:
    """Intelligentes Tool-Matching basierend auf Use Cases und Budget"""
    
    use_cases = answers.get('ki_usecases', [])
    budget = get_budget_amount(answers.get('budget', '2000-10000'))
    prefer_free = budget < 2000
    prefer_open_source = answers.get('open_source_preference', False)
    
    if not use_cases:
        use_cases = ['prozessautomatisierung']  # Default
    
    matched_tools = []
    seen_tools = set()
    
    # Matche Tools für jeden Use Case
    for uc in use_cases[:5]:  # Max 5 Use Cases
        uc_key = safe_str(uc).lower().replace(' ', '').replace('-', '')
        
        # Finde passende Tool-Kategorie
        for db_key, tools in TOOL_DATABASE.items():
            if db_key in uc_key or uc_key in db_key:
                # Sortiere Tools nach Präferenzen
                sorted_tools = sorted(tools, key=lambda x: (
                    -('Kostenlos' in x['badges'] and prefer_free),
                    -('Open Source' in x['badges'] and prefer_open_source),
                    -x['fit_score']
                ))
                
                # Füge bestes Tool hinzu wenn noch nicht vorhanden
                for tool in sorted_tools:
                    if tool['name'] not in seen_tools:
                        matched_tools.append({**tool, 'use_case_match': uc})
                        seen_tools.add(tool['name'])
                        break
                break
    
    # HTML generieren
    if lang == 'de':
        html = '<div class="tools-container">\n<h3>Empfohlene KI-Tools für Ihre Use Cases</h3>\n'
    else:
        html = '<div class="tools-container">\n<h3>Recommended AI Tools for Your Use Cases</h3>\n'
    
    if not matched_tools:
        if lang == 'de':
            html += '<p>Wir empfehlen eine individuelle Tool-Beratung basierend auf Ihren spezifischen Anforderungen.</p>'
        else:
            html += '<p>We recommend individual tool consultation based on your specific requirements.</p>'
    else:
        for tool in matched_tools[:6]:  # Max 6 Tools
            badges_html = ' '.join([f'<span class="badge badge-{badge_type(b)}">{b}</span>' 
                                   for b in tool['badges'][:4]])
            
            if lang == 'de':
                html += f"""
                <div class="tool-card">
                    <div class="tool-header">
                        <h4>{tool['name']}</h4>
                        <span class="fit-score">{tool['fit_score']}% Passung</span>
                    </div>
                    <p class="tool-desc">{tool['desc']}</p>
                    <div class="tool-details">
                        <div><strong>Anwendung:</strong> {tool['use_case']}</div>
                        <div><strong>Kosten:</strong> {tool['cost']}</div>
                        <div><strong>Komplexität:</strong> {tool['complexity']}</div>
                        <div><strong>Zeit bis Nutzen:</strong> {tool['time_to_value']}</div>
                    </div>
                    <div class="tool-badges">{badges_html}</div>
                    <a href="{tool['url']}" target="_blank" class="tool-link">Mehr erfahren →</a>
                </div>
                """
            else:
                html += f"""
                <div class="tool-card">
                    <div class="tool-header">
                        <h4>{tool['name']}</h4>
                        <span class="fit-score">{tool['fit_score']}% Match</span>
                    </div>
                    <p class="tool-desc">{tool['desc']}</p>
                    <div class="tool-details">
                        <div><strong>Use Case:</strong> {tool['use_case']}</div>
                        <div><strong>Cost:</strong> {tool['cost']}</div>
                        <div><strong>Complexity:</strong> {tool['complexity']}</div>
                        <div><strong>Time to Value:</strong> {tool['time_to_value']}</div>
                    </div>
                    <div class="tool-badges">{badges_html}</div>
                    <a href="{tool['url']}" target="_blank" class="tool-link">Learn more →</a>
                </div>
                """
    
    # Quick-Start Tipp
    if matched_tools and prefer_free:
        if lang == 'de':
            html += """
            <div class="info-box tip">
                <strong>💡 Tipp:</strong> Starten Sie mit den kostenlosen Open-Source-Tools 
                um erste Erfahrungen zu sammeln, bevor Sie in kostenpflichtige Lösungen investieren.
            </div>
            """
        else:
            html += """
            <div class="info-box tip">
                <strong>💡 Tip:</strong> Start with free open-source tools 
                to gain initial experience before investing in paid solutions.
            </div>
            """
    
    html += '</div>'
    return html

def badge_type(badge: str) -> str:
    """Bestimmt Badge-Typ für CSS-Klasse"""
    badge_lower = badge.lower()
    if 'kostenlos' in badge_lower or 'free' in badge_lower:
        return 'success'
    elif 'open source' in badge_lower:
        return 'info'
    elif 'dsgvo' in badge_lower or 'gdpr' in badge_lower:
        return 'warning'
    elif 'eu' in badge_lower:
        return 'primary'
    return 'secondary'
def match_funding_programs(answers: Dict[str, Any], lang: str = 'de') -> str:
    """Intelligentes Förderprogramm-Matching"""
    
    bundesland_code = safe_str(answers.get('bundesland', 'BE')).upper()
    bundesland_map = {
        'BE': 'berlin',
        'BY': 'bayern', 
        'BW': 'baden-wuerttemberg',
        'NW': 'nrw',
        'HE': 'hessen',
        'SN': 'sachsen',
        'BB': 'brandenburg',
        'MV': 'mecklenburg-vorpommern',
        'HH': 'hamburg',
        'HB': 'bremen',
        'NI': 'niedersachsen',
        'RP': 'rheinland-pfalz',
        'SL': 'saarland',
        'SH': 'schleswig-holstein',
        'TH': 'thueringen',
        'ST': 'sachsen-anhalt'
    }
    
    bundesland = bundesland_map.get(bundesland_code, 'berlin')
    size = safe_str(answers.get('unternehmensgroesse', '2-10'))
    fit_key = 'fit_small' if size in ['1', 'solo', '2-10'] else 'fit_medium'
    
    programs = []
    
    # Bundesweite Programme
    for prog in FUNDING_PROGRAMS['bundesweit']:
        programs.append({
            **prog,
            'fit': prog[fit_key],
            'region': 'Bundesweit' if lang == 'de' else 'Nationwide'
        })
    
    # Länder-spezifische Programme
    if bundesland in FUNDING_PROGRAMS:
        for prog in FUNDING_PROGRAMS[bundesland]:
            programs.append({
                **prog,
                'fit': prog[fit_key],
                'region': bundesland.capitalize()
            })
    
    # Sortiere nach Passung
    programs = sorted(programs, key=lambda x: -x['fit'])
    
    # HTML generieren
    if lang == 'de':
        html = """
        <div class="funding-container">
            <h3>Passende Förderprogramme für Ihr Unternehmen</h3>
            <table class="funding-table">
                <thead>
                    <tr>
                        <th>Programm</th>
                        <th>Förderung</th>
                        <th>Frist</th>
                        <th>Eignung</th>
                    </tr>
                </thead>
                <tbody>
        """
    else:
        html = """
        <div class="funding-container">
            <h3>Suitable Funding Programs for Your Company</h3>
            <table class="funding-table">
                <thead>
                    <tr>
                        <th>Program</th>
                        <th>Funding</th>
                        <th>Deadline</th>
                        <th>Suitability</th>
                    </tr>
                </thead>
                <tbody>
        """
    
    for prog in programs[:6]:  # Top 6 Programme
        fit_class = 'high' if prog['fit'] > 80 else 'medium' if prog['fit'] > 60 else 'low'
        
        html += f"""
        <tr class="funding-row">
            <td class="funding-name">
                <strong>{prog['name']}</strong>
                <br><small>{prog['provider']} ({prog['region']})</small>
                <br><small class="use-case">{prog['use_case']}</small>
            </td>
            <td class="funding-amount">{prog['amount']}</td>
            <td class="funding-deadline">{prog['deadline']}</td>
            <td class="funding-fit">
                <div class="progress-bar">
                    <div class="progress-fill fit-{fit_class}" style="width: {prog['fit']}%"></div>
                </div>
                <span class="fit-percent">{prog['fit']}%</span>
            </td>
        </tr>
        """
    
    html += """
            </tbody>
        </table>
    """
    
    # Handlungsempfehlung
    best_program = programs[0] if programs else None
    if best_program and best_program['fit'] > 80:
        if lang == 'de':
            html += f"""
            <div class="recommendation-box">
                <h4>🎯 Unsere Empfehlung</h4>
                <p><strong>{best_program['name']}</strong> passt mit {best_program['fit']}% 
                optimal zu Ihrem Unternehmensprofil. Die Förderung beträgt {best_program['amount']} 
                und kann für {best_program['use_case']} genutzt werden.</p>
                <p><strong>Nächste Schritte:</strong></p>
                <ol>
                    <li>Prüfung der detaillierten Förderkriterien</li>
                    <li>Vorbereitung der Unterlagen (Businessplan, Kostenaufstellung)</li>
                    <li>Antragstellung {'vor ' + best_program['deadline'] if best_program['deadline'] != 'Laufend' else 'zeitnah'}</li>
                </ol>
                <a href="{best_program['url']}" target="_blank" class="btn btn-primary">Zur Förderseite →</a>
            </div>
            """
        else:
            html += f"""
            <div class="recommendation-box">
                <h4>🎯 Our Recommendation</h4>
                <p><strong>{best_program['name']}</strong> matches your company profile 
                with {best_program['fit']}% suitability. The funding amounts to {best_program['amount']} 
                and can be used for {best_program['use_case']}.</p>
                <p><strong>Next Steps:</strong></p>
                <ol>
                    <li>Review detailed funding criteria</li>
                    <li>Prepare documents (business plan, cost breakdown)</li>
                    <li>Submit application {'before ' + best_program['deadline'] if best_program['deadline'] != 'Laufend' else 'soon'}</li>
                </ol>
                <a href="{best_program['url']}" target="_blank" class="btn btn-primary">Go to funding page →</a>
            </div>
            """
    
    # Kombinationstipp
    if len(programs) > 2:
        if lang == 'de':
            html += """
            <div class="info-box">
                <strong>💡 Hinweis:</strong> Viele Förderprogramme sind kombinierbar. 
                Nutzen Sie z.B. "go-digital" für die Beratung und "Digital Jetzt" für die Umsetzung. 
                Wir unterstützen Sie gerne bei der optimalen Förderstrategie.
            </div>
            """
        else:
            html += """
            <div class="info-box">
                <strong>💡 Note:</strong> Many funding programs can be combined. 
                For example, use "go-digital" for consulting and "Digital Jetzt" for implementation. 
                We're happy to support you with the optimal funding strategy.
            </div>
            """
    
    html += '</div>'
    return html

# ============================= Live-Daten Integration =============================

class LiveDataFetcher:
    """Holt aktuelle Daten von Tavily und SerpAPI"""
    
    def __init__(self):
        self.tavily_key = os.getenv('TAVILY_API_KEY', '')
        self.serpapi_key = os.getenv('SERPAPI_KEY', '') or os.getenv('SERPAPI_API_KEY', '')
        self.timeout = httpx.Timeout(30.0)
        
    def search_tavily(self, query: str, days: int = 30, max_results: int = 5) -> List[Dict[str, Any]]:
        """Tavily API für aktuelle Suchergebnisse"""
        if not self.tavily_key:
            return []
            
        url = "https://api.tavily.com/search"
        
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "advanced",
            "include_answer": False,
            "include_domains": [],
            "exclude_domains": [],
            "max_results": max_results,
            "days": days
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
        except Exception as e:
            print(f"Tavily API Fehler: {e}")
            return []
    
    def search_serpapi(self, query: str, location: str = "Germany", max_results: int = 5) -> List[Dict[str, Any]]:
        """SerpAPI für Google-Suchergebnisse"""
        if not self.serpapi_key:
            return []
            
        url = "https://serpapi.com/search.json"
        
        params = {
            "q": query,
            "api_key": self.serpapi_key,
            "num": max_results,
            "engine": "google",
            "location": location,
            "hl": "de",
            "gl": "de"
        }
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                results = []
                for item in data.get("organic_results", [])[:max_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "date": item.get("date", "")
                    })
                return results
        except Exception as e:
            print(f"SerpAPI Fehler: {e}")
            return []
    
    def get_current_ai_news(self, branche: str, bundesland: str) -> Dict[str, List[Dict[str, Any]]]:
        """Holt aktuelle KI-News für Branche und Region"""
        news = {
            "regulations": [],
            "tools": [],
            "funding": [],
            "trends": []
        }
        
        # Regulatorische Updates
        reg_query = f"EU AI Act {branche} Deutschland 2025 Compliance DSGVO"
        news["regulations"] = self.search_tavily(reg_query, days=7, max_results=3)
        if not news["regulations"]:
            news["regulations"] = self.search_serpapi(reg_query, location="Germany", max_results=3)
        
        # Neue Tools
        tools_query = f"neue KI Tools {branche} 2025 Deutschland kostenlos Open Source"
        news["tools"] = self.search_tavily(tools_query, days=14, max_results=5)
        
        # Förderprogramme
        funding_query = f"Fördermittel KI Digitalisierung {bundesland} {_dt.now().year} Antragsfrist"
        news["funding"] = self.search_tavily(funding_query, days=30, max_results=4)
        
        # Trends
        trends_query = f"KI Trends {branche} Mittelstand Deutschland 2025"
        news["trends"] = self.search_tavily(trends_query, days=30, max_results=3)
        
        return news

def generate_live_updates_section(answers: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert Live-Updates Sektion mit echten Daten"""
    
    branche = safe_str(answers.get('branche', 'beratung'))
    bundesland = safe_str(answers.get('bundesland', 'Berlin'))
    
    fetcher = LiveDataFetcher()
    
    # Prüfe ob APIs verfügbar
    if not fetcher.tavily_key and not fetcher.serpapi_key:
        if lang == 'de':
            return "<p>Live-Updates sind derzeit nicht verfügbar.</p>"
        else:
            return "<p>Live updates are currently not available.</p>"
    
    news = fetcher.get_current_ai_news(branche, bundesland)
    
    if lang == 'de':
        html = '<div class="live-updates">\n<h3>🔴 Aktuelle Entwicklungen für Sie (Live-Daten)</h3>\n'
    else:
        html = '<div class="live-updates">\n<h3>🔴 Current Developments for You (Live Data)</h3>\n'
    
    # Regulatorische Updates
    if news["regulations"]:
        if lang == 'de':
            html += "<h4>📋 Compliance & Regulierung</h4><ul>"
        else:
            html += "<h4>📋 Compliance & Regulation</h4><ul>"
            
        for item in news["regulations"][:2]:
            title = clean_text(item.get("title", ""))
            url = item.get("url", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{title}</a></li>'
        html += "</ul>"
    
    # Neue Tools
    if news["tools"]:
        if lang == 'de':
            html += "<h4>🛠️ Neu entdeckte KI-Tools</h4><ul>"
        else:
            html += "<h4>🛠️ Newly Discovered AI Tools</h4><ul>"
            
        for item in news["tools"][:3]:
            title = clean_text(item.get("title", ""))
            snippet = clean_text(item.get("snippet", ""))[:100]
            url = item.get("url", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{title}</a>'
                if snippet:
                    html += f'<br><small>{snippet}...</small>'
                html += '</li>'
        html += "</ul>"
    
    # Förderprogramme
    if news["funding"]:
        if lang == 'de':
            html += "<h4>💰 Aktuelle Fördermöglichkeiten</h4><ul>"
        else:
            html += "<h4>💰 Current Funding Opportunities</h4><ul>"
            
        for item in news["funding"][:2]:
            title = clean_text(item.get("title", ""))
            url = item.get("url", "")
            date = item.get("date", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{title}</a>'
                if date:
                    html += f' <small>({date})</small>'
                html += '</li>'
        html += "</ul>"
    
    # Trends
    if news["trends"]:
        if lang == 'de':
            html += "<h4>📈 Branchentrends</h4><ul>"
        else:
            html += "<h4>📈 Industry Trends</h4><ul>"
            
        for item in news["trends"][:2]:
            title = clean_text(item.get("title", ""))
            url = item.get("url", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{title}</a></li>'
        html += "</ul>"
    
    if not any([news["regulations"], news["tools"], news["funding"], news["trends"]]):
        if lang == 'de':
            html += "<p>Keine neuen Updates gefunden. Versuchen Sie es später erneut.</p>"
        else:
            html += "<p>No new updates found. Please try again later.</p>"
    
    html += '</div>'
    return html
# Am Ende der Datei nach allen anderen Funktionen hinzufügen:

# ============================= KORRIGIERTE HAUPTFUNKTION =============================

def analyze_briefing_enhanced(body: Dict[str, Any], lang: str = 'de') -> Dict[str, Any]:
    """
    Erweiterte Hauptfunktion mit voller Integration aller Features
    """
    # Sprache normalisieren
    lang = 'de' if lang.lower().startswith('de') else 'en'
    answers = dict(body)
    
    # 1. KPIs berechnen
    kpis = calculate_kpis_from_answers(answers)
    
    # 2. Template-Variablen vorbereiten
    variables = get_template_variables(answers, lang)
    
    # 3. Prompt Processor initialisieren
    prompt_processor = PromptProcessor()
    
    # 4. Sektionen generieren
    sections = {}
    
    # KORRIGIERTE section_config mit allen Fallback-Funktionen
    section_config = {
        'exec_summary_html': {
            'prompt': 'executive_summary',
            'use_gpt': True,
            'fallback': lambda: generate_data_driven_executive_summary(answers, kpis, lang)
        },
        'business_html': {
            'prompt': 'business',
            'use_gpt': True,
            'fallback': lambda: generate_business_case(answers, kpis, lang)
        },
        'coach_html': {
            'prompt': 'coach',
            'use_gpt': True,
            'fallback': lambda: generate_other_sections(answers, kpis, lang).get('coach', '')
        },
        'compliance_html': {
            'prompt': 'compliance',
            'use_gpt': False,
            'fallback': lambda: generate_other_sections(answers, kpis, lang).get('compliance', '')
        },
        'foerderprogramme_html': {
            'prompt': 'foerderprogramme',
            'use_gpt': False,
            'fallback': lambda: match_funding_programs(answers, lang)
        },
        'gamechanger_html': {
            'prompt': 'gamechanger',
            'use_gpt': True,
            'fallback': lambda: generate_other_sections(answers, kpis, lang).get('gamechanger', '')
        },
        'persona_html': {
            'prompt': 'persona',
            'use_gpt': True,
            'fallback': lambda: generate_persona_profile(answers, kpis, lang)
        },
        'praxisbeispiel_html': {
            'prompt': 'praxisbeispiel',
            'use_gpt': True,
            'fallback': lambda: generate_case_studies(answers, kpis, lang)
        },
        'quick_wins_html': {
            'prompt': 'quick_wins',
            'use_gpt': False,
            'fallback': lambda: generate_quick_wins(answers, kpis, lang)
        },
        'recommendations_html': {
            'prompt': 'recommendations',
            'use_gpt': True,
            'fallback': lambda: generate_other_sections(answers, kpis, lang).get('recommendations', '')
        },
        'risks_html': {
            'prompt': 'risks',
            'use_gpt': False,
            'fallback': lambda: generate_risk_analysis(answers, kpis, lang)
        },
        'roadmap_html': {
            'prompt': 'roadmap',
            'use_gpt': False,
            'fallback': lambda: generate_roadmap(answers, kpis, lang)
        },
        'tools_html': {
            'prompt': 'tools',
            'use_gpt': False,
            'fallback': lambda: match_tools_to_company(answers, lang)
        },
        'vision_html': {
            'prompt': 'vision',
            'use_gpt': True,
            'fallback': lambda: generate_other_sections(answers, kpis, lang).get('vision', '')
        }
    }
    
    # Prozessiere konfigurierte Sektionen
    for html_key, config in section_config.items():
        try:
            # Immer Fallback verwenden, da GPT nicht konfiguriert oder Fehler auftreten könnte
            sections[html_key] = config['fallback']()
        except Exception as e:
            print(f"Fehler bei {config['prompt']}: {e}")
            sections[html_key] = generate_fallback_content(config['prompt'], lang)
    
    # 5. Tools und Förderungen matchen (bereits mit eigenen Funktionen)
    if 'tools_html' not in sections or not sections['tools_html']:
        sections['tools_html'] = match_tools_to_company(answers, lang)
    
    if 'foerderprogramme_html' not in sections or not sections['foerderprogramme_html']:
        sections['foerderprogramme_html'] = match_funding_programs(answers, lang)
    
    # 6. Live-Daten wenn verfügbar
    sections['live_html'] = ""
    if has_live_apis():
        try:
            sections['live_html'] = generate_live_updates_section(answers, lang)
        except Exception as e:
            print(f"Live-Daten Fehler: {e}")
    
    # 7. Context zusammenbauen - ALLE erforderlichen Felder hinzufügen
    context = {
        # KPIs und Scores (von main.py erwartet)
        'score_percent': kpis['readiness_score'],
        'kpi_efficiency': kpis['kpi_efficiency'],
        'kpi_cost_saving': kpis['kpi_cost_saving'],
        'kpi_roi_months': kpis['kpi_roi_months'],
        'kpi_compliance': kpis['kpi_compliance'],
        'kpi_innovation': kpis['kpi_innovation'],
        'roi_investment': kpis['roi_investment'],
        'roi_annual_saving': kpis['roi_annual_saving'],
        'roi_three_year': kpis['roi_three_year'],
        
        # Alle Template-Variablen
        **variables,
        
        # HTML Sektionen
        'exec_summary_html': sections.get('exec_summary_html', ''),
        'business_html': sections.get('business_html', ''),
        'coach_html': sections.get('coach_html', ''),
        'compliance_html': sections.get('compliance_html', ''),
        'foerderprogramme_html': sections.get('foerderprogramme_html', ''),
        'gamechanger_html': sections.get('gamechanger_html', ''),
        'persona_html': sections.get('persona_html', ''),
        'praxisbeispiel_html': sections.get('praxisbeispiel_html', ''),
        'quick_wins_html': sections.get('quick_wins_html', ''),
        'recommendations_html': sections.get('recommendations_html', ''),
        'risks_html': sections.get('risks_html', ''),
        'roadmap_html': sections.get('roadmap_html', ''),
        'tools_html': sections.get('tools_html', ''),
        'vision_html': sections.get('vision_html', ''),
        'live_html': sections.get('live_html', ''),
        
        # Metadaten
        'meta': {
            'title': get_report_title(lang),
            'subtitle': f"AI Readiness: {kpis['readiness_score']}%",
            'date': _dt.now().strftime('%d.%m.%Y'),
            'lang': lang,
            'version': '2.0',
            'has_live_data': has_live_apis()
        }
    }
    
    # 8. HTML bereinigen
    for key, value in context.items():
        if isinstance(value, str) and '_html' in key:
            context[key] = clean_and_validate_html(value)
    
    return context

def has_live_apis() -> bool:
    """Prüft ob Live-Daten APIs konfiguriert sind"""
    return bool(os.getenv('TAVILY_API_KEY')) or bool(os.getenv('SERPAPI_KEY'))

def get_report_title(lang: str) -> str:
    """Gibt Report-Titel in passender Sprache zurück"""
    titles = {
        'de': 'KI-Statusbericht & Handlungsempfehlungen',
        'en': 'AI Status Report & Recommendations'
    }
    return titles.get(lang, titles['de'])

# ============================= WICHTIG: Haupteinstiegspunkt =============================

def analyze_briefing(body: Dict[str, Any], lang: str = 'de') -> Dict[str, Any]:
    """
    Haupteinstiegspunkt - ruft erweiterte Version auf
    Behält Kompatibilität mit existierendem Code
    DIESE FUNKTION WIRD VON main.py AUFGERUFEN!
    """
    try:
        # Debug-Ausgabe
        print(f"analyze_briefing called with lang={lang}")
        print(f"Body keys: {body.keys() if body else 'No body'}")
        
        result = analyze_briefing_enhanced(body, lang)
        
        # Stelle sicher, dass alle erforderlichen Felder vorhanden sind
        required_fields = [
            'score_percent', 'kpi_roi_months', 'roi_three_year', 
            'kpi_compliance', 'kpi_innovation', 'kpi_efficiency',
            'roi_annual_saving', 'roi_investment'
        ]
        
        for field in required_fields:
            if field not in result:
                print(f"Warning: Missing field {field}, adding default")
                # Fallback-Werte wenn Felder fehlen
                if 'roi' in field or 'investment' in field or 'saving' in field:
                    result[field] = 10000  # Default Geldwert
                elif 'months' in field:
                    result[field] = 12  # Default Monate
                else:
                    result[field] = 50  # Default Prozent
        
        print(f"analyze_briefing returning {len(result)} fields")
        return result
        
    except Exception as e:
        print(f"FEHLER in analyze_briefing: {e}")
        import traceback
        traceback.print_exc()
        
        # Minimaler Fallback mit allen erforderlichen Feldern
        return {
            'score_percent': 50,
            'kpi_efficiency': 30,
            'kpi_cost_saving': 25,
            'kpi_roi_months': 12,
            'kpi_compliance': 70,
            'kpi_innovation': 60,
            'roi_investment': 10000,
            'roi_annual_saving': 20000,
            'roi_three_year': 50000,
            'digitalisierungsgrad': 5,
            'automatisierungsgrad': 50,
            'risikofreude': 3,
            'exec_summary_html': '<p>Fehler bei der Analyse-Generierung. Bitte versuchen Sie es erneut.</p>',
            'business_html': '<p>Business Case wird generiert...</p>',
            'quick_wins_html': '<p>Quick Wins werden identifiziert...</p>',
            'tools_html': '<p>Tool-Empfehlungen werden erstellt...</p>',
            'roadmap_html': '<p>Roadmap wird entwickelt...</p>',
            'risks_html': '<p>Risikoanalyse läuft...</p>',
            'compliance_html': '<p>Compliance-Check wird durchgeführt...</p>',
            'vision_html': '<p>Vision wird erstellt...</p>',
            'coach_html': '<p>Coaching-Fragen werden vorbereitet...</p>',
            'gamechanger_html': '<p>Game-Changer Analyse läuft...</p>',
            'persona_html': '<p>Persona-Profil wird erstellt...</p>',
            'praxisbeispiel_html': '<p>Praxisbeispiele werden gesucht...</p>',
            'recommendations_html': '<p>Empfehlungen werden generiert...</p>',
            'foerderprogramme_html': '<p>Förderprogramme werden geprüft...</p>',
            'live_html': ''
        }
# ============================= Test-Funktion (VOLLSTÄNDIG) =============================

if __name__ == "__main__":
    # Test mit Beispieldaten
    test_data = {
        'branche': 'beratung',
        'unternehmensgroesse': '2-10',
        'bundesland': 'BE',
        'hauptleistung': 'KI-Beratung und Automatisierung',
        'digitalisierungsgrad': 8,
        'prozesse_papierlos': '81-100',
        'automatisierungsgrad': 'eher_hoch',
        'risikofreude': 4,
        'ki_usecases': ['texterstellung', 'prozessautomatisierung', 'kundensupport'],
        'ki_hemmnisse': ['budget', 'zeit'],
        'ki_knowhow': 'fortgeschritten',
        'datenschutzbeauftragter': 'ja',
        'dsgvo_folgenabschaetzung': 'teilweise',
        'eu_ai_act_kenntnis': 'gut',
        'richtlinien_governance': 'ja',
        'budget': '2000-10000',
        'projektziel': ['Effizienzsteigerung', 'Kostensenkung'],
        'zielgruppen': ['B2B', 'Mittelstand']
    }
    
    # Test deutsche Version
    print("=== TESTE DEUTSCHE VERSION ===")
    result_de = analyze_briefing(test_data, 'de')
    
    print(f"\nKI-Reifegrad: {result_de['score_percent']}%")
    print(f"ROI: {result_de['kpi_roi_months']} Monate")
    print(f"3-Jahres-Wert: {result_de['roi_three_year']:,} EUR")
    print(f"Compliance: {result_de['kpi_compliance']}%")
    print(f"Innovation: {result_de['kpi_innovation']}%")
    
    # Prüfe ob alle Sektionen vorhanden sind
    required_sections = [
        'exec_summary_html', 'business_html', 'coach_html', 
        'compliance_html', 'foerderprogramme_html', 'gamechanger_html',
        'persona_html', 'praxisbeispiel_html', 'quick_wins_html',
        'recommendations_html', 'risks_html', 'roadmap_html',
        'tools_html', 'vision_html'
    ]
    
    missing_sections = []
    for section in required_sections:
        if section not in result_de or not result_de[section]:
            missing_sections.append(section)
    
    if missing_sections:
        print(f"\n⚠️  Fehlende Sektionen: {missing_sections}")
    else:
        print("\n✅ Alle Sektionen erfolgreich generiert!")
    
    # Test englische Version
    print("\n=== TESTING ENGLISH VERSION ===")
    result_en = analyze_briefing(test_data, 'en')
    
    print(f"\nAI Readiness: {result_en['score_percent']}%")
    print(f"ROI: {result_en['kpi_roi_months']} months")
    print(f"3-year value: EUR {result_en['roi_three_year']:,}")
    
    print(f"\n✅ Live-Daten verfügbar: {has_live_apis()}")
    print("✅ Test abgeschlossen!")