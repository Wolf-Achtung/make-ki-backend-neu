# quality_control.py

from typing import Dict, List, Tuple, Any
import re
from dataclasses import dataclass
from enum import Enum

class QualityLevel(Enum):
    FAILED = 0
    POOR = 1
    ACCEPTABLE = 2
    GOOD = 3
    EXCELLENT = 4
    GOLD_STANDARD = 5

@dataclass
class QualityCheck:
    """Einzelner Qualitäts-Check"""
    name: str
    passed: bool
    score: float
    message: str
    severity: str  # 'critical', 'major', 'minor'

class ReportQualityController:
    """
    Umfassendes Qualitätssicherungssystem für KI-Reports
    """
    
    def __init__(self):
        self.checks_performed = []
        self.overall_score = 0
        self.quality_level = QualityLevel.FAILED
        
    def validate_complete_report(self, 
                                context: Dict[str, Any], 
                                lang: str = 'de') -> Dict[str, Any]:
        """
        Führt vollständige Qualitätsprüfung durch
        """
        checks = []
        
        # 1. Datenintegrität
        checks.extend(self._check_data_integrity(context))
        
        # 2. Konsistenz
        checks.extend(self._check_consistency(context))
        
        # 3. Plausibilität
        checks.extend(self._check_plausibility(context))
        
        # 4. Vollständigkeit
        checks.extend(self._check_completeness(context))
        
        # 5. Sprachqualität
        checks.extend(self._check_language_quality(context, lang))
        
        # 6. Compliance
        checks.extend(self._check_compliance_requirements(context))
        
        # 7. Handlungsorientierung
        checks.extend(self._check_actionability(context))
        
        # Score berechnen
        self.overall_score = self._calculate_overall_score(checks)
        self.quality_level = self._determine_quality_level(self.overall_score)
        
        return {
            'passed': self.quality_level.value >= QualityLevel.ACCEPTABLE.value,
            'quality_level': self.quality_level.name,
            'overall_score': self.overall_score,
            'checks': checks,
            'critical_issues': [c for c in checks if c.severity == 'critical' and not c.passed],
            'improvements': self._generate_improvements(checks),
            'report_card': self._generate_report_card(checks)
        }
    
    def _check_data_integrity(self, context: Dict) -> List[QualityCheck]:
        """Prüft Datenintegrität und Encoding"""
        checks = []
        
        # Encoding-Check
        encoding_issues = 0
        for key, value in context.items():
            if isinstance(value, str):
                if any(char in value for char in ['Ã¼', 'Ã¤', 'Ã¶', 'ÃŸ', 'â€']):
                    encoding_issues += 1
        
        checks.append(QualityCheck(
            name="Encoding korrekt",
            passed=encoding_issues == 0,
            score=100 if encoding_issues == 0 else max(0, 100 - encoding_issues * 10),
            message=f"{encoding_issues} Encoding-Fehler gefunden" if encoding_issues > 0 else "Keine Encoding-Fehler",
            severity="major"
        ))
        
        # Zahlen-Konsistenz
        budget = context.get('roi_investment', 0)
        savings = context.get('roi_annual_saving', 0)
        roi_months = context.get('kpi_roi_months', 12)
        
        calculated_roi = (budget / (savings / 12)) if savings > 0 else 999
        roi_diff = abs(calculated_roi - roi_months)
        
        checks.append(QualityCheck(
            name="ROI-Berechnung konsistent",
            passed=roi_diff < 2,
            score=100 if roi_diff < 2 else max(0, 100 - roi_diff * 10),
            message=f"ROI-Abweichung: {roi_diff:.1f} Monate",
            severity="critical" if roi_diff > 6 else "major"
        ))
        
        return checks
    
    def _check_consistency(self, context: Dict) -> List[QualityCheck]:
        """Prüft Konsistenz zwischen Sektionen"""
        checks = []
        
        # Score-Konsistenz
        score = context.get('score_percent', 0)
        readiness_level = context.get('readiness_level', '')
        
        expected_level = self._get_expected_readiness_level(score)
        level_match = expected_level.lower() in readiness_level.lower()
        
        checks.append(QualityCheck(
            name="Readiness-Level konsistent",
            passed=level_match,
            score=100 if level_match else 60,
            message=f"Score {score}% passt zu Level '{readiness_level}'" if level_match else f"Score {score}% passt nicht zu '{readiness_level}'",
            severity="major"
        ))
        
        # Budget-Konsistenz über Sektionen
        if 'roadmap_html' in context:
            roadmap_budget_mentioned = str(context.get('roi_investment', 0)) in context['roadmap_html']
            checks.append(QualityCheck(
                name="Budget in Roadmap konsistent",
                passed=roadmap_budget_mentioned,
                score=100 if roadmap_budget_mentioned else 70,
                message="Budget konsistent verwendet" if roadmap_budget_mentioned else "Budget inkonsistent",
                severity="minor"
            ))
        
        return checks
    
    def _check_plausibility(self, context: Dict) -> List[QualityCheck]:
        """Prüft Plausibilität der Werte"""
        checks = []
        
        # ROI-Plausibilität
        budget = context.get('roi_investment', 1)
        savings = context.get('roi_annual_saving', 0)
        roi_factor = savings / budget if budget > 0 else 0
        
        plausible_roi = 0.5 <= roi_factor <= 4.0
        checks.append(QualityCheck(
            name="ROI plausibel",
            passed=plausible_roi,
            score=100 if plausible_roi else 40,
            message=f"ROI-Faktor {roi_factor:.1f}x ist {'plausibel' if plausible_roi else 'unrealistisch'}",
            severity="critical" if roi_factor > 5 else "major"
        ))
        
        # Effizienz-Plausibilität
        efficiency = context.get('kpi_efficiency', 0)
        automation = context.get('automatisierungsgrad', 50)
        
        max_efficiency = (100 - automation) * 0.8
        efficiency_plausible = efficiency <= max_efficiency
        
        checks.append(QualityCheck(
            name="Effizienzpotenzial realistisch",
            passed=efficiency_plausible,
            score=100 if efficiency_plausible else 60,
            message=f"{efficiency}% Effizienz bei {automation}% Automatisierung {'realistisch' if efficiency_plausible else 'zu hoch'}",
            severity="major"
        ))
        
        return checks
    
    def _check_completeness(self, context: Dict) -> List[QualityCheck]:
        """Prüft Vollständigkeit des Reports"""
        checks = []
        
        required_sections = [
            'exec_summary_html',
            'quick_wins_html',
            'roadmap_html',
            'risks_html',
            'recommendations_html'
        ]
        
        missing = []
        empty = []
        
        for section in required_sections:
            if section not in context:
                missing.append(section)
            elif not context[section] or len(context[section]) < 50:
                empty.append(section)
        
        checks.append(QualityCheck(
            name="Alle Pflicht-Sektionen vorhanden",
            passed=len(missing) == 0,
            score=100 if not missing else max(0, 100 - len(missing) * 20),
            message=f"Fehlende Sektionen: {missing}" if missing else "Alle Sektionen vorhanden",
            severity="critical"
        ))
        
        checks.append(QualityCheck(
            name="Sektionen mit Inhalt",
            passed=len(empty) == 0,
            score=100 if not empty else max(0, 100 - len(empty) * 15),
            message=f"Leere Sektionen: {empty}" if empty else "Alle Sektionen gefüllt",
            severity="major"
        ))
        
        return checks
    
    def _check_language_quality(self, context: Dict, lang: str) -> List[QualityCheck]:
        """Prüft Sprachqualität und Lesbarkeit"""
        checks = []
        
        # Flesch-Reading-Ease approximation
        sample_text = context.get('exec_summary_html', '')
        if sample_text:
            # Vereinfachte Lesbarkeits-Metrik
            avg_sentence_length = self._calculate_avg_sentence_length(sample_text)
            readability_ok = 10 <= avg_sentence_length <= 20
            
            checks.append(QualityCheck(
                name="Lesbarkeit optimal",
                passed=readability_ok,
                score=100 if readability_ok else 70,
                message=f"Durchschnittliche Satzlänge: {avg_sentence_length:.0f} Wörter",
                severity="minor"
            ))
        
        # Aktiv vs. Passiv
        passive_indicators = ['werden', 'wurde', 'wurden', 'worden'] if lang == 'de' else ['was', 'were', 'been', 'being']
        passive_count = sum(indicator in sample_text.lower() for indicator in passive_indicators)
        
        checks.append(QualityCheck(
            name="Aktive Sprache",
            passed=passive_count < 5,
            score=100 if passive_count < 5 else max(60, 100 - passive_count * 5),
            message=f"{passive_count} Passiv-Indikatoren gefunden",
            severity="minor"
        ))
        
        return checks
    
    def _check_compliance_requirements(self, context: Dict) -> List[QualityCheck]:
        """Prüft Compliance-Anforderungen"""
        checks = []
        
        compliance_score = context.get('kpi_compliance', 0)
        has_dpo = context.get('datenschutzbeauftragter') in ['ja', 'extern']
        
        # DSGVO-Check
        if compliance_score < 60 and not has_dpo:
            checks.append(QualityCheck(
                name="DSGVO-Risiko adressiert",
                passed=False,
                score=40,
                message="Kritischer DSGVO-Status ohne DSB",
                severity="critical"
            ))
        else:
            checks.append(QualityCheck(
                name="DSGVO-Basis vorhanden",
                passed=True,
                score=100,
                message="DSGVO-Grundlagen erfüllt",
                severity="minor"
            ))
        
        return checks
    
    def _check_actionability(self, context: Dict) -> List[QualityCheck]:
        """Prüft Handlungsorientierung"""
        checks = []
        
        # Quick Wins Konkretheit
        quick_wins = context.get('quick_wins_html', '')
        has_concrete_tools = bool(re.findall(r'ChatGPT|DeepL|Notion|Canva|tl;dv|Otter', quick_wins))
        has_time_frames = bool(re.findall(r'\d+\s*(Tag|Woch|Monat|Stund)', quick_wins))
        has_costs = bool(re.findall(r'\d+\s*(€|EUR)', quick_wins))
        
        actionability_score = sum([has_concrete_tools, has_time_frames, has_costs]) * 33
        
        checks.append(QualityCheck(
            name="Quick Wins konkret",
            passed=actionability_score >= 66,
            score=actionability_score,
            message=f"Tools: {has_concrete_tools}, Zeit: {has_time_frames}, Kosten: {has_costs}",
            severity="major"
        ))
        
        return checks
    
    def _calculate_overall_score(self, checks: List[QualityCheck]) -> float:
        """Berechnet Gesamt-Score mit Gewichtung"""
        if not checks:
            return 0
        
        weights = {
            'critical': 3.0,
            'major': 2.0,
            'minor': 1.0
        }
        
        weighted_sum = 0
        weight_total = 0
        
        for check in checks:
            weight = weights.get(check.severity, 1.0)
            weighted_sum += check.score * weight
            weight_total += weight
        
        return weighted_sum / weight_total if weight_total > 0 else 0
    
    def _determine_quality_level(self, score: float) -> QualityLevel:
        """Bestimmt Qualitätslevel basierend auf Score"""
        if score >= 95:
            return QualityLevel.GOLD_STANDARD
        elif score >= 85:
            return QualityLevel.EXCELLENT
        elif score >= 75:
            return QualityLevel.GOOD
        elif score >= 65:
            return QualityLevel.ACCEPTABLE
        elif score >= 50:
            return QualityLevel.POOR
        else:
            return QualityLevel.FAILED
    
    def _generate_improvements(self, checks: List[QualityCheck]) -> List[str]:
        """Generiert Verbesserungsvorschläge"""
        improvements = []
        
        for check in checks:
            if not check.passed:
                if check.severity == 'critical':
                    improvements.append(f"🔴 KRITISCH: {check.name} - {check.message}")
                elif check.severity == 'major':
                    improvements.append(f"🟡 WICHTIG: {check.name} - {check.message}")
        
        return improvements[:5]  # Top 5 Verbesserungen
    
    def _generate_report_card(self, checks: List[QualityCheck]) -> Dict:
        """Generiert Report-Zeugnis"""
        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        
        return {
            'grade': self.quality_level.name,
            'score': f"{self.overall_score:.1f}/100",
            'passed_checks': f"{passed}/{total}",
            'critical_issues': sum(1 for c in checks if c.severity == 'critical' and not c.passed),
            'ready_for_delivery': self.quality_level.value >= QualityLevel.GOOD.value
        }
    
    def _calculate_avg_sentence_length(self, text: str) -> float:
        """Berechnet durchschnittliche Satzlänge"""
        # HTML entfernen
        text = re.sub(r'<[^>]+>', '', text)
        # Sätze splitten
        sentences = re.split(r'[.!?]+', text)
        # Wörter zählen
        word_counts = [len(s.split()) for s in sentences if s.strip()]
        return sum(word_counts) / len(word_counts) if word_counts else 15
    
    def _get_expected_readiness_level(self, score: int) -> str:
        """Ermittelt erwartetes Readiness Level"""
        if score >= 85:
            return "Führend"
        elif score >= 70:
            return "Reif"
        elif score >= 50:
            return "Fortgeschritten"
        elif score >= 30:
            return "Grundlegend"
        else:
            return "Anfänger"


# Integration in Hauptprozess
def generate_quality_assured_report(answers: Dict, lang: str = 'de') -> Dict:
    """
    Generiert Report mit Qualitätssicherung
    """
    # 1. Report generieren
    context = analyze_briefing_enhanced(answers, lang)
    
    # 2. Qualität prüfen
    qc = ReportQualityController()
    quality_result = qc.validate_complete_report(context, lang)
    
    # 3. Bei schlechter Qualität: Nachbesserung
    if not quality_result['passed']:
        print(f"Qualität unzureichend: {quality_result['quality_level']}")
        
        # Kritische Fehler beheben
        for issue in quality_result['critical_issues']:
            print(f"Behebe: {issue.name}")
            context = fix_critical_issue(context, issue)
        
        # Erneut prüfen
        quality_result = qc.validate_complete_report(context, lang)
    
    # 4. Quality Badge hinzufügen
    context['quality_badge'] = quality_result['report_card']
    
    return context

def fix_critical_issue(context: Dict, issue: QualityCheck) -> Dict:
    """
    Behebt kritische Qualitätsprobleme
    """
    if 'ROI' in issue.name:
        # ROI neu berechnen
        context = recalculate_roi(context)
    elif 'Encoding' in issue.name:
        # Encoding fixen
        context = fix_encoding_issues(context)
    elif 'Sektion' in issue.name:
        # Fehlende Sektion generieren
        context = regenerate_missing_section(context, issue)
    
    return context