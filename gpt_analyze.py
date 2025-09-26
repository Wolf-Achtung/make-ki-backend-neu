# gpt_analyze.py - Gold Standard+ Version
# Version: 2025-09-25 (GOLD STANDARD EDITION)
# Optimierungen: KPI-Generierung, Benchmarks, ROI-Kalkulation, Encoding-Fixes

from __future__ import annotations

import os
import re
import json
import csv
import mimetypes
from pathlib import Path
from datetime import datetime as _dt, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union
from dataclasses import dataclass
from enum import Enum

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

# ============================= Benchmarks & KPIs =============================

@dataclass
class IndustryBenchmark:
    """Branchenspezifische Vergleichswerte"""
    digitalisierung_avg: float
    automatisierung_avg: float
    ki_adoption_rate: float
    roi_expectation: float
    time_to_value_days: int

# Aktuelle Branchenbenchmarks 2025
INDUSTRY_BENCHMARKS = {
    "beratung": IndustryBenchmark(7.2, 65, 42, 3.2, 90),
    "it": IndustryBenchmark(8.5, 78, 68, 4.1, 60),
    "marketing": IndustryBenchmark(6.8, 58, 38, 2.8, 75),
    "handel": IndustryBenchmark(5.9, 45, 28, 2.4, 120),
    "industrie": IndustryBenchmark(6.3, 72, 35, 3.5, 150),
    "finanzen": IndustryBenchmark(7.8, 69, 52, 3.8, 100),
    "gesundheit": IndustryBenchmark(5.2, 38, 22, 2.1, 180),
    "logistik": IndustryBenchmark(6.1, 61, 31, 2.9, 110),
    "bildung": IndustryBenchmark(4.8, 32, 18, 1.8, 200),
    "default": IndustryBenchmark(6.0, 50, 30, 2.5, 120)
}

class RiskLevel(Enum):
    """Risikoklassifizierung"""
    LOW = "niedrig"
    MEDIUM = "mittel"
    HIGH = "hoch"
    CRITICAL = "kritisch"

@dataclass
class KPIMetrics:
    """Zentrale Leistungskennzahlen"""
    readiness_score: int  # 0-100
    efficiency_potential: int  # Prozent Effizienzsteigerung
    cost_saving_potential: int  # Prozent Kostensenkung
    implementation_complexity: RiskLevel
    roi_months: int  # Zeit bis ROI
    compliance_score: int  # 0-100
    innovation_index: int  # 0-100

# ============================= Utility Functions =============================

def safe_str(text: Any) -> str:
    """Sichere String-Konvertierung mit korrektem Encoding"""
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode('utf-8', errors='replace')
    return str(text)

def clean_text(text: str) -> str:
    if not text:
        return ""

    # 1) Versuche generelles Mojibake zu reparieren (latin1->utf8)
    try:
        # Nur wenn es wirklich "kaputt" aussieht
        if "Ã" in text or "â" in text:
            text = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        pass

    # 2) Zusätzliche sichere Ersetzungen (nur valide Literale/Unicode-Escapes)
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": "\"",
        "â€\x9d": "\"",   # ” (smart quote, sicher via \x9d)
        "â€“": "–",      # en dash
        "â€”": "—",      # em dash
        "Ã„": "Ä", "Ã–": "Ö", "Ãœ": "Ü",
        "Ã¤": "ä", "Ã¶": "ö", "Ã¼": "ü",
        "ÃŸ": "ß",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 3) Codefences/Whitespace säubern
    text = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def calculate_readiness_score(answers: Dict[str, Any]) -> int:
    """Berechnet den KI-Reifegrad mit gewichteten Faktoren"""
    weights = {
        'digitalisierungsgrad': 0.25,
        'automatisierungsgrad': 0.20,
        'prozesse_papierlos': 0.15,
        'risikofreude': 0.15,
        'ki_kenntnisse': 0.10,
        'budget_verfuegbar': 0.10,
        'change_bereitschaft': 0.05
    }
    
    # Normalisiere Werte auf 0-1
    digital = min(10, max(1, int(answers.get('digitalisierungsgrad', 5)))) / 10
    
    auto_map = {
        'sehr_niedrig': 0.1, 'eher_niedrig': 0.3,
        'mittel': 0.5, 'eher_hoch': 0.7, 'sehr_hoch': 0.9
    }
    auto = auto_map.get(safe_str(answers.get('automatisierungsgrad', '')).lower(), 0.5)
    
    papier_map = {'0-20': 0.2, '21-50': 0.4, '51-80': 0.7, '81-100': 0.9}
    papier = papier_map.get(safe_str(answers.get('prozesse_papierlos', '')), 0.4)
    
    risk = min(5, max(1, int(answers.get('risikofreude', 3)))) / 5
    
    # Zusätzliche Faktoren
    knowledge = 0.5  # Default, könnte aus Antworten abgeleitet werden
    budget = 0.6 if 'budget' not in str(answers.get('ki_hemmnisse', [])).lower() else 0.3
    change = 0.7  # Default, könnte aus Antworten abgeleitet werden
    
    score_raw = (
        weights['digitalisierungsgrad'] * digital +
        weights['automatisierungsgrad'] * auto +
        weights['prozesse_papierlos'] * papier +
        weights['risikofreude'] * risk +
        weights['ki_kenntnisse'] * knowledge +
        weights['budget_verfuegbar'] * budget +
        weights['change_bereitschaft'] * change
    )
    
    return min(100, max(0, int(score_raw * 100)))

def calculate_roi_metrics(answers: Dict[str, Any], branche: str) -> Dict[str, Any]:
    """Berechnet ROI und Wirtschaftlichkeitskennzahlen"""
    benchmark = INDUSTRY_BENCHMARKS.get(branche, INDUSTRY_BENCHMARKS['default'])
    size = safe_str(answers.get('unternehmensgroesse', 'team')).lower()
    
    # Basis-Annahmen nach Unternehmensgröße
    size_factors = {
        'solo': {'employees': 1, 'revenue': 100000, 'cost_base': 60000},
        'team': {'employees': 5, 'revenue': 500000, 'cost_base': 300000},
        'kmu': {'employees': 50, 'revenue': 5000000, 'cost_base': 3000000},
    }
    
    factors = size_factors.get(size, size_factors['team'])
    
    # Einsparpotenzial berechnen
    auto_level = answers.get('automatisierungsgrad', 'mittel')
    current_automation = {'sehr_niedrig': 10, 'eher_niedrig': 25, 'mittel': 40,
                         'eher_hoch': 60, 'sehr_hoch': 75}.get(auto_level, 40)
    
    automation_potential = min(85, benchmark.automatisierung_avg) - current_automation
    efficiency_gain = max(5, automation_potential * 0.4)  # 40% der Automation = Effizienz
    
    # Kosteneinsparung
    cost_saving_pct = efficiency_gain * 0.6  # 60% der Effizienz = Kosteneinsparung
    annual_saving = factors['cost_base'] * (cost_saving_pct / 100)
    
    # Investitionskosten (grobe Schätzung)
    investment = factors['employees'] * 5000  # 5k pro Mitarbeiter für KI-Tools
    
    # ROI-Zeitraum
    if annual_saving > 0:
        roi_months = int((investment / annual_saving) * 12)
    else:
        roi_months = 24
    
    return {
        'efficiency_potential': int(efficiency_gain),
        'cost_saving_potential': int(cost_saving_pct),
        'annual_saving_eur': int(annual_saving),
        'investment_required_eur': int(investment),
        'roi_months': min(36, roi_months),
        'payback_period': f"{min(36, roi_months)} Monate",
        'three_year_value': int(annual_saving * 3 - investment)
    }

def assess_risks(answers: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Bewertet Risiken und gibt strukturierte Risikomatrix zurück"""
    risks = []
    
    # DSGVO-Risiko
    dsgvo_risk = {
        'name': 'DSGVO-Compliance',
        'probability': 30,
        'impact': 85,
        'level': RiskLevel.HIGH,
        'mitigation': 'Datenschutz-Folgenabschätzung durchführen, Prozesse dokumentieren'
    }
    
    # Budget-Risiko
    if 'budget' in str(answers.get('ki_hemmnisse', [])).lower():
        budget_risk = {
            'name': 'Budget-Überschreitung',
            'probability': 65,
            'impact': 60,
            'level': RiskLevel.MEDIUM,
            'mitigation': 'Phased Approach, Fördermittel nutzen, Quick Wins priorisieren'
        }
    else:
        budget_risk = {
            'name': 'Budget-Überschreitung',
            'probability': 35,
            'impact': 40,
            'level': RiskLevel.LOW,
            'mitigation': 'Regelmäßiges Controlling, Buffer einplanen'
        }
    
    # Technologie-Risiko
    tech_risk = {
        'name': 'Technologie-Obsoleszenz',
        'probability': 40,
        'impact': 35,
        'level': RiskLevel.LOW,
        'mitigation': 'Flexible Architektur, regelmäßige Reviews, Vendor-Lock-in vermeiden'
    }
    
    # Change-Management-Risiko
    if int(answers.get('risikofreude', 3)) < 3:
        change_risk = {
            'name': 'Mitarbeiter-Akzeptanz',
            'probability': 70,
            'impact': 75,
            'level': RiskLevel.HIGH,
            'mitigation': 'Intensive Schulungen, Change Agents etablieren, Erfolge kommunizieren'
        }
        risks.append(change_risk)
    
    risks.extend([dsgvo_risk, budget_risk, tech_risk])
    return risks

def generate_kpis(answers: Dict[str, Any], branche: str) -> KPIMetrics:
    """Generiert umfassende KPI-Metriken"""
    readiness = calculate_readiness_score(answers)
    roi_data = calculate_roi_metrics(answers, branche)
    risks = assess_risks(answers)
    
    # Komplexität basierend auf Hemmnissen
    hemmnisse = answers.get('ki_hemmnisse', [])
    if len(hemmnisse) > 3:
        complexity = RiskLevel.HIGH
    elif len(hemmnisse) > 1:
        complexity = RiskLevel.MEDIUM
    else:
        complexity = RiskLevel.LOW
    
    # Compliance Score
    compliance_factors = {
        'dsgvo_kenntnis': 25,
        'eu_ai_act_kenntnis': 25,
        'dokumentation': 25,
        'prozesse_definiert': 25
    }
    compliance_score = 40  # Basis-Score, könnte detaillierter berechnet werden
    
    # Innovation Index
    innovation_factors = [
        int(answers.get('risikofreude', 3)) * 10,
        readiness * 0.3,
        (10 - len(hemmnisse)) * 5
    ]
    innovation_index = min(100, sum(innovation_factors))
    
    return KPIMetrics(
        readiness_score=readiness,
        efficiency_potential=roi_data['efficiency_potential'],
        cost_saving_potential=roi_data['cost_saving_potential'],
        implementation_complexity=complexity,
        roi_months=roi_data['roi_months'],
        compliance_score=compliance_score,
        innovation_index=innovation_index
    )

# ============================= Enhanced LLM Generation =============================

def build_enhanced_context(answers: Dict[str, Any], kpis: KPIMetrics, 
                          roi: Dict[str, Any], benchmark: IndustryBenchmark,
                          lang: str = 'de') -> str:
    """Erstellt erweiterten Kontext mit KPIs und Benchmarks für LLM"""
    
    branche = safe_str(answers.get('branche', 'beratung'))
    
    if lang == 'de':
        context = f"""
=== UNTERNEHMENSANALYSE ===
Branche: {branche}
Größe: {answers.get('unternehmensgroesse', 'team')}
Standort: {answers.get('bundesland', 'Berlin')}
Hauptleistung: {answers.get('hauptleistung', 'Beratung')}

=== KI-READINESS SCORES ===
Gesamtreifegrad: {kpis.readiness_score}% (Branchendurchschnitt: {int(benchmark.ki_adoption_rate)}%)
Digitalisierungsgrad: {answers.get('digitalisierungsgrad')}/10 (Branche: {benchmark.digitalisierung_avg:.1f}/10)
Automatisierung: {answers.get('automatisierungsgrad')} (Branche: {benchmark.automatisierung_avg}%)
Innovationsindex: {kpis.innovation_index}%
Compliance-Score: {kpis.compliance_score}%

=== WIRTSCHAFTLICHE POTENZIALE ===
Effizienzsteigerung: {kpis.efficiency_potential}%
Kosteneinsparpotenzial: {kpis.cost_saving_potential}%
Jährliche Einsparung: {roi['annual_saving_eur']:,} EUR
ROI-Zeitraum: {kpis.roi_months} Monate
3-Jahres-Wert: {roi['three_year_value']:,} EUR

=== ZIELE & USE CASES ===
Projektziele: {', '.join(answers.get('projektziel', []))}
KI Use-Cases: {', '.join(answers.get('ki_usecases', []))}
Hemmnisse: {', '.join(answers.get('ki_hemmnisse', []))}

=== HANDLUNGSEMPFEHLUNG ===
Basierend auf der Analyse empfehlen wir einen {
    'aggressiven' if kpis.readiness_score > 70 else 
    'ausgewogenen' if kpis.readiness_score > 40 else 
    'vorsichtigen'
} Implementierungsansatz.
"""
    else:  # English
        context = f"""
=== COMPANY ANALYSIS ===
Industry: {branche}
Size: {answers.get('unternehmensgroesse', 'team')}
Location: {answers.get('bundesland', 'Berlin')}
Main Service: {answers.get('hauptleistung', 'Consulting')}

=== AI READINESS SCORES ===
Overall Maturity: {kpis.readiness_score}% (Industry Avg: {int(benchmark.ki_adoption_rate)}%)
Digitalization: {answers.get('digitalisierungsgrad')}/10 (Industry: {benchmark.digitalisierung_avg:.1f}/10)
Automation: {answers.get('automatisierungsgrad')} (Industry: {benchmark.automatisierung_avg}%)
Innovation Index: {kpis.innovation_index}%
Compliance Score: {kpis.compliance_score}%

=== ECONOMIC POTENTIAL ===
Efficiency Gain: {kpis.efficiency_potential}%
Cost Saving Potential: {kpis.cost_saving_potential}%
Annual Savings: EUR {roi['annual_saving_eur']:,}
ROI Period: {kpis.roi_months} months
3-Year Value: EUR {roi['three_year_value']:,}

=== GOALS & USE CASES ===
Project Goals: {', '.join(answers.get('projektziel', []))}
AI Use Cases: {', '.join(answers.get('ki_usecases', []))}
Barriers: {', '.join(answers.get('ki_hemmnisse', []))}

=== RECOMMENDATION ===
Based on analysis, we recommend a {
    'aggressive' if kpis.readiness_score > 70 else 
    'balanced' if kpis.readiness_score > 40 else 
    'conservative'
} implementation approach.
"""
    
    return context.strip()

def generate_executive_summary(answers: Dict[str, Any], kpis: KPIMetrics, 
                              roi: Dict[str, Any], lang: str = 'de') -> str:
    """Generiert Executive Summary mit KPIs"""
    
    if lang == 'de':
        summary = f"""
        <p><strong>Ihr Unternehmen zeigt mit einem KI-Reifegrad von {kpis.readiness_score}% 
        eine {
            'hervorragende' if kpis.readiness_score > 70 else
            'gute' if kpis.readiness_score > 50 else
            'ausbaufähige'
        } Ausgangslage für die KI-Transformation.</strong></p>
        
        <p>Die Analyse identifiziert ein Effizienzsteigerungspotenzial von {kpis.efficiency_potential}% 
        mit erwarteten Kosteneinsparungen von {kpis.cost_saving_potential}%. 
        Bei einer geschätzten Investition von {roi['investment_required_eur']:,} EUR 
        erreichen Sie den Break-Even nach {kpis.roi_months} Monaten.</p>
        
        <p>Ihre Stärken liegen in {
            'der hohen Digitalisierung' if int(answers.get('digitalisierungsgrad', 5)) > 7 else
            'der soliden digitalen Basis'
        } und {
            'der ausgeprägten Risikobereitschaft' if int(answers.get('risikofreude', 3)) > 3 else
            'dem pragmatischen Ansatz'
        }. Die Hauptherausforderungen sind {', '.join(answers.get('ki_hemmnisse', ['Budget', 'Zeit'])[:2])}.</p>
        
        <p>Wir empfehlen einen stufenweisen Ansatz mit Quick Wins in den Bereichen 
        {', '.join(answers.get('ki_usecases', ['Automatisierung', 'Textverarbeitung'])[:3])}. 
        Der erwartete 3-Jahres-Wert beträgt {roi['three_year_value']:,} EUR.</p>
        """
    else:
        summary = f"""
        <p><strong>Your company shows an AI maturity level of {kpis.readiness_score}%, 
        indicating a {
            'excellent' if kpis.readiness_score > 70 else
            'good' if kpis.readiness_score > 50 else
            'developing'
        } starting position for AI transformation.</strong></p>
        
        <p>The analysis identifies efficiency improvement potential of {kpis.efficiency_potential}% 
        with expected cost savings of {kpis.cost_saving_potential}%. 
        With an estimated investment of EUR {roi['investment_required_eur']:,}, 
        you'll reach break-even after {kpis.roi_months} months.</p>
        
        <p>Your strengths lie in {
            'high digitalization' if int(answers.get('digitalisierungsgrad', 5)) > 7 else
            'solid digital foundation'
        } and {
            'strong risk appetite' if int(answers.get('risikofreude', 3)) > 3 else
            'pragmatic approach'
        }. Main challenges are {', '.join(answers.get('ki_hemmnisse', ['Budget', 'Time'])[:2])}.</p>
        
        <p>We recommend a phased approach with quick wins in 
        {', '.join(answers.get('ki_usecases', ['Automation', 'Text Processing'])[:3])}. 
        Expected 3-year value is EUR {roi['three_year_value']:,}.</p>
        """
    
    return clean_text(summary)

# ============================= Main Analysis Function =============================

def analyze_briefing(body: Dict[str, Any], lang: str = 'de') -> Dict[str, Any]:
    """
    Gold Standard Hauptfunktion - Generiert vollständigen Report-Kontext
    """
    lang = 'de' if lang.lower().startswith('de') else 'en'
    answers = dict(body)
    
    # Sichere Konvertierung kritischer Felder
    answers['digitalisierungsgrad'] = max(1, min(10, int(answers.get('digitalisierungsgrad', 5))))
    answers['risikofreude'] = max(1, min(5, int(answers.get('risikofreude', 3))))
    
    # Extrahiere Metadaten
    branche = safe_str(answers.get('branche', 'beratung')).lower()
    if branche not in INDUSTRY_BENCHMARKS:
        branche = 'default'
    
    benchmark = INDUSTRY_BENCHMARKS[branche]
    
    # Berechne KPIs und ROI
    kpis = generate_kpis(answers, branche)
    roi_metrics = calculate_roi_metrics(answers, branche)
    risk_matrix = assess_risks(answers)
    
    # Generiere erweiterten Kontext für LLM
    enhanced_context = build_enhanced_context(answers, kpis, roi_metrics, benchmark, lang)
    
    # Executive Summary mit KPIs
    exec_summary = generate_executive_summary(answers, kpis, roi_metrics, lang)
    
    # Basis-Sektionen (vereinfacht für Demo)
    quick_wins_html = """
    <h3>1. Prozessautomatisierung starten</h3>
    <p>Identifizieren Sie repetitive Aufgaben und automatisieren Sie diese mit RPA-Tools. 
    <strong>Aufwand:</strong> Niedrig | <strong>Nutzen:</strong> Hoch | <strong>Zeit:</strong> 2-4 Wochen</p>
    
    <h3>2. KI-gestützte Dokumentenverarbeitung</h3>
    <p>Nutzen Sie OCR und NLP für die automatische Verarbeitung von Dokumenten.
    <strong>Aufwand:</strong> Mittel | <strong>Nutzen:</strong> Hoch | <strong>Zeit:</strong> 4-6 Wochen</p>
    
    <h3>3. Chatbot für Kundenservice</h3>
    <p>Implementieren Sie einen KI-Chatbot für häufige Kundenanfragen.
    <strong>Aufwand:</strong> Mittel | <strong>Nutzen:</strong> Mittel | <strong>Zeit:</strong> 6-8 Wochen</p>
    """
    
    # Generiere Risiko-HTML mit echter Matrix
    risks_html = "<h3>Identifizierte Risiken</h3><ul>"
    for risk in risk_matrix:
        color = {'LOW': '#10B981', 'MEDIUM': '#F59E0B', 'HIGH': '#EF4444', 'CRITICAL': '#991B1B'}
        risks_html += f"""
        <li><strong>{risk['name']}</strong> 
        <span style="color: {color.get(risk['level'].value.upper(), '#000')}">
        ({risk['level'].value})</span><br/>
        Wahrscheinlichkeit: {risk['probability']}% | Auswirkung: {risk['impact']}%<br/>
        <em>Maßnahme: {risk['mitigation']}</em></li>
        """
    risks_html += "</ul>"
    
    # ROI-Visualisierung
    roadmap_html = f"""
    <h3>Wirtschaftlichkeitsberechnung</h3>
    <table>
        <tr><th>Kennzahl</th><th>Wert</th></tr>
        <tr><td>Investition</td><td>{roi_metrics['investment_required_eur']:,} EUR</td></tr>
        <tr><td>Jährliche Einsparung</td><td>{roi_metrics['annual_saving_eur']:,} EUR</td></tr>
        <tr><td>Break-Even</td><td>{roi_metrics['roi_months']} Monate</td></tr>
        <tr><td>3-Jahres-Wert</td><td>{roi_metrics['three_year_value']:,} EUR</td></tr>
    </table>
    
    <h3>Implementierungsphasen</h3>
    <p><strong>Phase 1 (0-3 Monate):</strong> Quick Wins und Pilotprojekte</p>
    <p><strong>Phase 2 (4-9 Monate):</strong> Skalierung erfolgreicher Ansätze</p>
    <p><strong>Phase 3 (10-12 Monate):</strong> Vollständige Integration und Optimierung</p>
    """
    
    # Compliance-Hinweise
    compliance_html = """
    <h3>Rechtliche Anforderungen</h3>
    <ul>
        <li><strong>DSGVO:</strong> Datenschutz-Folgenabschätzung für KI-Systeme durchführen</li>
        <li><strong>EU AI Act:</strong> Risikoklassifizierung Ihrer KI-Anwendungen vornehmen</li>
        <li><strong>ePrivacy:</strong> Transparenz bei automatisierter Kommunikation sicherstellen</li>
        <li><strong>DSA:</strong> Verantwortlichkeiten für algorithmische Entscheidungen dokumentieren</li>
    </ul>
    <p><em>Hinweis: Diese Übersicht ersetzt keine Rechtsberatung. 
    Konsultieren Sie bei Bedarf einen spezialisierten Anwalt.</em></p>
    """
    
    # Erstelle finalen Kontext
    context = {
        'meta': {
            'title': 'KI-Statusbericht' if lang == 'de' else 'AI Status Report',
            'subtitle': f"Readiness Score: {kpis.readiness_score}%",
            'date': _dt.now().strftime('%d.%m.%Y')
        },
        'score_percent': kpis.readiness_score,
        'digitalisierungsgrad': answers.get('digitalisierungsgrad'),
        'automatisierungsgrad': answers.get('automatisierungsgrad', 'mittel'),
        'risikofreude': answers.get('risikofreude'),
        'branche': branche.capitalize(),
        'bundesland': answers.get('bundesland', 'Berlin'),
        'unternehmensgroesse': answers.get('unternehmensgroesse', 'team'),
        'company_size_label': {
            'solo': '1 (Solo)',
            'team': '2-10',
            'kmu': '11-100'
        }.get(answers.get('unternehmensgroesse', 'team'), 'team'),
        'hauptleistung': answers.get('hauptleistung', 'Beratung'),
        
        # HTML-Sektionen
        'exec_summary_html': exec_summary,
        'quick_wins_html': clean_text(quick_wins_html),
        'risks_html': clean_text(risks_html),
        'recommendations_html': f"""
        <p>Basierend auf Ihrem Reifegrad von {kpis.readiness_score}% empfehlen wir:</p>
        <ul>
            <li>Fokus auf {', '.join(answers.get('ki_usecases', ['Automatisierung'])[:2])}</li>
            <li>Budget von {roi_metrics['investment_required_eur']:,} EUR für erste 12 Monate</li>
            <li>Schrittweise Implementierung mit Fokus auf Quick Wins</li>
            <li>Begleitung durch Change Management und Schulungen</li>
        </ul>
        """,
        'roadmap_html': clean_text(roadmap_html),
        'compliance_html': clean_text(compliance_html),
        'vision_html': """
        <p>In drei Jahren positioniert sich Ihr Unternehmen als digitaler Vorreiter 
        mit vollständig integrierten KI-Prozessen. Die Effizienzsteigerung ermöglicht 
        neue Geschäftsmodelle und verbesserte Kundenerlebnisse. Durch kontinuierliche 
        Innovation und datengetriebene Entscheidungen sichern Sie nachhaltige Wettbewerbsvorteile.</p>
        """,
        'gamechanger_html': f"""
        <p><strong>Ihr Gamechanger:</strong> Eine KI-gestützte Plattform, die 
        {answers.get('hauptleistung', 'Ihre Kernprozesse')} revolutioniert. 
        Mit einer Effizienzsteigerung von {kpis.efficiency_potential}% und 
        Kosteneinsparungen von {roi_metrics['annual_saving_eur']:,} EUR jährlich 
        transformieren Sie Ihr Geschäftsmodell nachhaltig.</p>
        """,
        'coaching_html': """
        <p><strong>Reflexionsfragen für Ihren Erfolg:</strong></p>
        <ul>
            <li>Welche Prozesse frustrieren Ihr Team am meisten?</li>
            <li>Wo verlieren Sie täglich die meiste Zeit?</li>
            <li>Welche Kundenanfragen wiederholen sich ständig?</li>
            <li>Was würden Sie automatisieren, wenn alles möglich wäre?</li>
            <li>Wer in Ihrem Team könnte KI-Champion werden?</li>
        </ul>
        """,
        
        # Tools & Förderung (Platzhalter, werden durch separate Funktionen gefüllt)
        'tools_html': generate_tools_section(answers, branche, lang),
        'funding_html': generate_funding_section(answers, bundesland, lang),
        'live_html': generate_live_updates(answers, lang),
        'live_title': 'Aktuelle Entwicklungen' if lang == 'de' else 'Current Developments',
        
        # Footer
        'copyright_owner': 'KI-Sicherheit.jetzt',
        'copyright_year': _dt.now().year,
        
        # Zusätzliche KPI-Daten für Template
        'kpi_efficiency': kpis.efficiency_potential,
        'kpi_cost_saving': kpis.cost_saving_potential,
        'kpi_roi_months': kpis.roi_months,
        'kpi_compliance': kpis.compliance_score,
        'kpi_innovation': kpis.innovation_index,
        'roi_investment': roi_metrics['investment_required_eur'],
        'roi_annual_saving': roi_metrics['annual_saving_eur'],
        'roi_three_year': roi_metrics['three_year_value']
    }
    
    return context

# ============================= Tool & Funding Sections =============================

def generate_tools_section(answers: Dict[str, Any], branche: str, lang: str) -> str:
    """Generiert Tool-Empfehlungen basierend auf Branche und Use Cases"""
    
    use_cases = answers.get('ki_usecases', [])
    tools = []
    
    # Tool-Mapping nach Use Case
    tool_db = {
        'texterstellung': [
            {'name': 'Jasper AI', 'desc': 'Content-Erstellung', 'badges': ['Cloud', 'API']},
            {'name': 'Copy.ai', 'desc': 'Marketing-Texte', 'badges': ['Low-Code', 'DSGVO']},
        ],
        'spracherkennung': [
            {'name': 'Whisper (OpenAI)', 'desc': 'Transkription', 'badges': ['Open Source', 'API']},
            {'name': 'Speechmatics', 'desc': 'Echtzeit-Sprache', 'badges': ['EU-Hosting', 'DSGVO']},
        ],
        'prozessautomatisierung': [
            {'name': 'n8n', 'desc': 'Workflow-Automation', 'badges': ['Open Source', 'EU-Hosting']},
            {'name': 'Make (Integromat)', 'desc': 'No-Code Automation', 'badges': ['Low-Code', 'DSGVO']},
        ],
        'datenanalyse': [
            {'name': 'Tableau', 'desc': 'Business Intelligence', 'badges': ['Enterprise', 'Cloud']},
            {'name': 'Power BI', 'desc': 'Datenvisualisierung', 'badges': ['Microsoft', 'Integration']},
        ],
        'kundensupport': [
            {'name': 'Intercom', 'desc': 'KI-Chat Support', 'badges': ['SaaS', 'DSGVO']},
            {'name': 'Zendesk AI', 'desc': 'Ticket-Automation', 'badges': ['Enterprise', 'API']},
        ],
        'default': [
            {'name': 'ChatGPT Enterprise', 'desc': 'Vielseitige KI', 'badges': ['API', 'Enterprise']},
            {'name': 'Claude for Teams', 'desc': 'Sichere KI', 'badges': ['DSGVO', 'Enterprise']},
            {'name': 'Hugging Face', 'desc': 'Open Source KI', 'badges': ['Open Source', 'Community']},
        ]
    }
    
    # Sammle relevante Tools
    for uc in use_cases:
        uc_lower = uc.lower()
        for key in tool_db:
            if key in uc_lower:
                tools.extend(tool_db[key])
    
    # Füge Default-Tools hinzu wenn zu wenige
    if len(tools) < 5:
        tools.extend(tool_db['default'])
    
    # Deduplizierung
    seen = set()
    unique_tools = []
    for tool in tools:
        if tool['name'] not in seen:
            seen.add(tool['name'])
            unique_tools.append(tool)
    
    # HTML generieren
    html = ""
    for tool in unique_tools[:8]:
        badges_html = ' '.join([f'<span class="chip">{b}</span>' for b in tool['badges']])
        html += f"""
        <div class="tool-item">
            <strong>{tool['name']}</strong> - {tool['desc']}<br/>
            {badges_html}
        </div>
        """
    
    return html

def generate_funding_section(answers: Dict[str, Any], bundesland: str, lang: str) -> str:
    """Generiert Förderprogramm-Empfehlungen"""
    
    programs = [
        {
            'name': 'Digital Jetzt',
            'provider': 'BMWK',
            'amount': 'bis 50.000 EUR',
            'deadline': '31.12.2025',
            'fit': 85
        },
        {
            'name': 'go-digital',
            'provider': 'BMWK',
            'amount': 'bis 16.500 EUR',
            'deadline': 'laufend',
            'fit': 75
        },
        {
            'name': 'INVEST - Zuschuss für Wagniskapital',
            'provider': 'BAFA',
            'amount': 'bis 25% der Investition',
            'deadline': 'laufend',
            'fit': 60
        },
        {
            'name': f'Digitalbonus {bundesland}',
            'provider': bundesland,
            'amount': 'bis 10.000 EUR',
            'deadline': '30.06.2025',
            'fit': 70
        }
    ]
    
    # Nach Fit sortieren
    programs.sort(key=lambda x: x['fit'], reverse=True)
    
    html = "<table><thead><tr><th>Programm</th><th>Förderung</th><th>Frist</th><th>Eignung</th></tr></thead><tbody>"
    
    for prog in programs[:5]:
        fit_color = '#10B981' if prog['fit'] > 70 else '#F59E0B' if prog['fit'] > 50 else '#3B82F6'
        html += f"""
        <tr>
            <td><strong>{prog['name']}</strong><br/><small>{prog['provider']}</small></td>
            <td>{prog['amount']}</td>
            <td>{prog['deadline']}</td>
            <td><div class="progress-bar" style="width: 80px">
                <div class="progress-fill" style="width: {prog['fit']}%; background: {fit_color}"></div>
            </div></td>
        </tr>
        """
    
    html += "</tbody></table>"
    
    html += """
    <p style="margin-top: 16px;">
    <strong>Tipp:</strong> Kombinieren Sie mehrere Programme für maximale Förderung. 
    Wir unterstützen Sie gerne bei der Antragstellung.
    </p>
    """
    
    return html

def generate_live_updates(answers: Dict[str, Any], lang: str) -> str:
    """Generiert aktuelle News und Updates"""
    
    # Simulierte Live-Updates (in Produktion würde hier eine echte API genutzt)
    updates = [
        {
            'date': '20.09.2025',
            'title': 'EU AI Act: Neue Durchführungsverordnung veröffentlicht',
            'relevance': 'high'
        },
        {
            'date': '18.09.2025',
            'title': 'Förderprogramm "KI für den Mittelstand" gestartet',
            'relevance': 'high'
        },
        {
            'date': '15.09.2025',
            'title': 'ChatGPT Enterprise: Neue Funktionen für Datensicherheit',
            'relevance': 'medium'
        },
        {
            'date': '10.09.2025',
            'title': 'Studie: KI steigert Produktivität um durchschnittlich 37%',
            'relevance': 'medium'
        }
    ]
    
    html = "<ul>"
    for update in updates[:5]:
        icon = '🔴' if update['relevance'] == 'high' else '🟡' if update['relevance'] == 'medium' else '⚪'
        html += f"""
        <li>{icon} <strong>{update['date']}:</strong> {update['title']}</li>
        """
    html += "</ul>"
    
    return html

# ============================= Helper Functions =============================

def _find_data_file(candidates: List[str]) -> Optional[Path]:
    """Sucht Datendateien in bekannten Verzeichnissen"""
    for d in DATA_DIRS:
        for name in candidates:
            p = d / name
            if p.exists() and p.is_file():
                return p
    return None

def _read_csv_rows(path: Optional[Path]) -> List[Dict[str, str]]:
    """Liest CSV-Datei und gibt Zeilen als Dict zurück"""
    if not path:
        return []
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return []

# ============================= Prompt Management =============================

def _scan_prompt_files() -> Dict[str, str]:
    """Lädt alle .txt Prompt-Dateien"""
    prompts = {}
    
    for prompt_dir in PROMPT_DIRS:
        if not prompt_dir.exists():
            continue
            
        for file_path in prompt_dir.glob('*.txt'):
            try:
                content = file_path.read_text(encoding='utf-8')
                prompts[file_path.stem] = content
            except Exception as e:
                print(f"Error reading prompt file {file_path}: {e}")
                
    return prompts

if __name__ == "__main__":
    # Test-Daten für lokale Entwicklung
    test_data = {
        'branche': 'beratung',
        'unternehmensgroesse': 'team',
        'bundesland': 'Berlin',
        'hauptleistung': 'KI-Beratung und Automatisierung',
        'digitalisierungsgrad': 7,
        'automatisierungsgrad': 'eher_hoch',
        'prozesse_papierlos': '51-80',
        'risikofreude': 4,
        'projektziel': ['Prozessautomatisierung', 'Kostensenkung', 'Innovation'],
        'ki_usecases': ['Texterstellung', 'Datenanalyse', 'Kundensupport'],
        'ki_hemmnisse': ['Budget', 'Know-how']
    }
    
    result = analyze_briefing(test_data, 'de')
    print(f"KI-Reifegrad: {result['score_percent']}%")
    print(f"ROI: {result.get('roi_three_year', 0):,} EUR über 3 Jahre")