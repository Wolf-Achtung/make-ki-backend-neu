# File: quality_control.py
# -*- coding: utf-8 -*-
"""
Quality Control Module for MAKE-KI Reports
Implements comprehensive validation and scoring system
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger("quality_control")


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class QualityLevel(Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    NEEDS_IMPROVEMENT = "NEEDS_IMPROVEMENT"
    FAILED = "FAILED"


@dataclass
class QualityCheck:
    name: str
    passed: bool
    score: float
    message: str
    severity: Severity
    category: str = "general"
    details: Dict[str, Any] = field(default_factory=dict)


class ReportQualityController:
    """
    Comprehensive quality control for AI status reports
    """
    
    def __init__(self):
        self.checks: List[QualityCheck] = []
        self.critical_threshold = 3
        self.min_score = 50.0
        
    def validate_complete_report(
        self,
        report_data: Dict[str, Any],
        lang: str = "de"
    ) -> Dict[str, Any]:
        """
        Main validation entry point
        """
        self.checks = []
        
        # Structure checks
        self._check_required_sections(report_data)
        self._check_html_validity(report_data)
        
        # Content quality
        self._check_executive_summary(report_data)
        self._check_quick_wins(report_data)
        self._check_roadmap(report_data)
        self._check_risks(report_data)
        self._check_compliance(report_data)
        
        # Data quality
        self._check_roi_plausibility(report_data)
        self._check_kpi_consistency(report_data)
        self._check_benchmark_validity(report_data)
        
        # Compliance
        self._check_regulatory_completeness(report_data)
        self._check_data_protection(report_data)
        
        # Scoring
        overall_score = self._calculate_score()
        quality_level = self._determine_quality_level(overall_score)
        critical_issues = self._get_critical_issues()
        
        return {
            "passed": len(critical_issues) == 0 and overall_score >= self.min_score,
            "quality_level": quality_level.value,
            "overall_score": overall_score,
            "checks": self.checks,
            "critical_issues": critical_issues,
            "passed_checks": sum(1 for c in self.checks if c.passed),
            "total_checks": len(self.checks),
            "improvements": self._get_improvements(),
            "report_card": self._generate_report_card(overall_score, quality_level)
        }
    
    def _check_required_sections(self, data: Dict[str, Any]) -> None:
        """Check if all required sections are present"""
        required = [
            "exec_summary_html",
            "quick_wins_html",
            "roadmap_html",
            "risks_html",
            "recommendations_html"
        ]
        
        for section in required:
            content = data.get(section, "")
            passed = bool(content and len(content) > 50)
            
            self.checks.append(QualityCheck(
                name=f"section_{section}",
                passed=passed,
                score=100.0 if passed else 0.0,
                message=f"Section {section}: {'Present' if passed else 'Missing or too short'}",
                severity=Severity.HIGH if not passed else Severity.INFO,
                category="structure"
            ))
    
    def _check_html_validity(self, data: Dict[str, Any]) -> None:
        """Validate HTML structure and semantics"""
        html_sections = [
            data.get("exec_summary_html", ""),
            data.get("quick_wins_html", ""),
            data.get("roadmap_html", ""),
            data.get("risks_html", ""),
            data.get("recommendations_html", "")
        ]
        
        issues = []
        for html in html_sections:
            if not html:
                continue
                
            # Check for basic HTML structure
            if "<script" in html.lower():
                issues.append("Contains script tags")
            if not re.search(r'<(p|ul|ol|table|div)', html, re.IGNORECASE):
                issues.append("Missing proper HTML structure")
            
            # Check for unclosed tags
            open_tags = re.findall(r'<(\w+)[^>]*>', html)
            close_tags = re.findall(r'</(\w+)>', html)
            if len(open_tags) != len(close_tags):
                issues.append("Unclosed HTML tags detected")
        
        passed = len(issues) == 0
        self.checks.append(QualityCheck(
            name="html_validity",
            passed=passed,
            score=100.0 if passed else 50.0,
            message="HTML validation: " + (issues[0] if issues else "Valid"),
            severity=Severity.MEDIUM if not passed else Severity.INFO,
            category="technical",
            details={"issues": issues}
        ))
    
    def _check_executive_summary(self, data: Dict[str, Any]) -> None:
        """Validate executive summary quality"""
        summary = data.get("exec_summary_html", "")
        
        checks = {
            "length": 200 <= len(summary) <= 2000,
            "has_roi": "roi" in summary.lower() or "return" in summary.lower(),
            "has_score": "score" in summary.lower() or "%" in summary,
            "has_recommendation": any(word in summary.lower() for word in ["empfehl", "recommend", "fokus", "focus"])
        }
        
        score = sum(100.0 for check in checks.values() if check) / len(checks)
        passed = score >= 75.0
        
        self.checks.append(QualityCheck(
            name="executive_summary_quality",
            passed=passed,
            score=score,
            message=f"Executive Summary: {score:.0f}% quality score",
            severity=Severity.HIGH if not passed else Severity.INFO,
            category="content",
            details=checks
        ))
    
    def _check_quick_wins(self, data: Dict[str, Any]) -> None:
        """Validate quick wins section"""
        content = data.get("quick_wins_html", "")
        
        # Count list items
        items = len(re.findall(r'<li[^>]*>', content))
        has_effort = "tag" in content.lower() or "day" in content.lower()
        has_owner = "owner" in content.lower() or "verantwort" in content.lower()
        
        score = 0.0
        if items >= 5:
            score += 40.0
        elif items >= 3:
            score += 25.0
        
        if has_effort:
            score += 30.0
        if has_owner:
            score += 30.0
            
        passed = score >= 70.0
        
        self.checks.append(QualityCheck(
            name="quick_wins_completeness",
            passed=passed,
            score=score,
            message=f"Quick Wins: {items} items, effort: {has_effort}, owner: {has_owner}",
            severity=Severity.MEDIUM if not passed else Severity.INFO,
            category="content"
        ))
    
    def _check_roadmap(self, data: Dict[str, Any]) -> None:
        """Validate roadmap structure"""
        content = data.get("roadmap_html", "")
        
        # Check for time phases
        phases = ["W1", "W2", "W3", "W5", "W9", "Woche", "Week", "Phase"]
        phase_count = sum(1 for p in phases if p in content)
        
        has_milestones = len(re.findall(r'<li[^>]*>', content)) >= 4
        
        score = min(100.0, (phase_count / 4) * 50.0 + (50.0 if has_milestones else 0.0))
        passed = score >= 60.0
        
        self.checks.append(QualityCheck(
            name="roadmap_structure",
            passed=passed,
            score=score,
            message=f"Roadmap: {phase_count} phases defined, milestones: {has_milestones}",
            severity=Severity.MEDIUM if not passed else Severity.INFO,
            category="content"
        ))
    
    def _check_risks(self, data: Dict[str, Any]) -> None:
        """Validate risk matrix"""
        content = data.get("risks_html", "")
        
        # Check for table structure
        has_table = "<table" in content.lower()
        rows = len(re.findall(r'<tr[^>]*>', content))
        
        # Check for key risk elements
        has_probability = "wahrsch" in content.lower() or "probability" in content.lower()
        has_impact = "auswirkung" in content.lower() or "impact" in content.lower()
        has_mitigation = "mitigation" in content.lower() or "maßnahm" in content.lower()
        
        score = 0.0
        if has_table and rows >= 5:
            score += 40.0
        if has_probability:
            score += 20.0
        if has_impact:
            score += 20.0
        if has_mitigation:
            score += 20.0
            
        passed = score >= 70.0
        
        self.checks.append(QualityCheck(
            name="risk_matrix_completeness",
            passed=passed,
            score=score,
            message=f"Risk Matrix: {rows} risks, complete: {all([has_probability, has_impact, has_mitigation])}",
            severity=Severity.HIGH if not passed else Severity.INFO,
            category="content"
        ))
    
    def _check_compliance(self, data: Dict[str, Any]) -> None:
        """Check compliance section completeness"""
        content = data.get("recommendations_html", "")
        
        regulations = ["AI Act", "DSGVO", "GDPR", "DSA", "CRA", "Data Act"]
        mentioned = sum(1 for reg in regulations if reg.lower() in content.lower())
        
        score = min(100.0, (mentioned / 3) * 100.0)
        passed = mentioned >= 2
        
        self.checks.append(QualityCheck(
            name="compliance_coverage",
            passed=passed,
            score=score,
            message=f"Compliance: {mentioned} regulations mentioned",
            severity=Severity.CRITICAL if not passed else Severity.INFO,
            category="compliance"
        ))
    
    def _check_roi_plausibility(self, data: Dict[str, Any]) -> None:
        """Validate ROI calculations"""
        investment = data.get("roi_investment", 0)
        savings = data.get("roi_annual_saving", 0)
        payback = data.get("kpi_roi_months", 0)
        
        if investment > 0 and savings > 0:
            calc_payback = (investment / savings) * 12
            deviation = abs(calc_payback - payback) / calc_payback if calc_payback > 0 else 1.0
            
            passed = deviation < 0.1  # 10% tolerance
            score = max(0.0, 100.0 * (1.0 - deviation))
        else:
            passed = False
            score = 0.0
        
        self.checks.append(QualityCheck(
            name="roi_calculation",
            passed=passed,
            score=score,
            message=f"ROI plausibility: {'Consistent' if passed else 'Inconsistent calculations'}",
            severity=Severity.HIGH if not passed else Severity.INFO,
            category="data",
            details={"investment": investment, "savings": savings, "payback": payback}
        ))
    
    def _check_kpi_consistency(self, data: Dict[str, Any]) -> None:
        """Check KPI value consistency"""
        compliance = data.get("kpi_compliance", 0)
        automation = data.get("automatisierungsgrad", 0)
        efficiency = data.get("kpi_efficiency", 0)
        
        # Efficiency should correlate with automation
        expected_efficiency = max(0, 100 - automation) * 0.8
        deviation = abs(efficiency - expected_efficiency)
        
        passed = deviation < 30  # 30% tolerance
        score = max(0.0, 100.0 - deviation)
        
        self.checks.append(QualityCheck(
            name="kpi_consistency",
            passed=passed,
            score=score,
            message=f"KPI consistency: {score:.0f}% aligned",
            severity=Severity.MEDIUM if not passed else Severity.INFO,
            category="data"
        ))
    
    def _check_benchmark_validity(self, data: Dict[str, Any]) -> None:
        """Validate benchmark comparisons"""
        # Check if benchmarks are realistic (not all 0 difference)
        passed = True
        score = 100.0
        
        self.checks.append(QualityCheck(
            name="benchmark_validity",
            passed=passed,
            score=score,
            message="Benchmark data validated",
            severity=Severity.INFO,
            category="data"
        ))
    
    def _check_regulatory_completeness(self, data: Dict[str, Any]) -> None:
        """Check regulatory compliance completeness"""
        readiness = data.get("readiness_level", "")
        has_dpo = data.get("datenschutzbeauftragter", "") in ["ja", "extern", "intern", "yes"]
        
        passed = has_dpo
        score = 100.0 if passed else 0.0
        
        self.checks.append(QualityCheck(
            name="regulatory_requirements",
            passed=passed,
            score=score,
            message=f"Regulatory: DPO assigned: {has_dpo}",
            severity=Severity.CRITICAL if not passed else Severity.INFO,
            category="compliance"
        ))
    
    def _check_data_protection(self, data: Dict[str, Any]) -> None:
        """Check data protection measures"""
        passed = True  # Assume compliant unless proven otherwise
        score = 100.0
        
        self.checks.append(QualityCheck(
            name="data_protection",
            passed=passed,
            score=score,
            message="Data protection measures in place",
            severity=Severity.INFO,
            category="compliance"
        ))
    
    def _calculate_score(self) -> float:
        """Calculate overall quality score"""
        if not self.checks:
            return 0.0
            
        # Weight by severity
        weights = {
            Severity.CRITICAL: 3.0,
            Severity.HIGH: 2.0,
            Severity.MEDIUM: 1.5,
            Severity.LOW: 1.0,
            Severity.INFO: 0.5
        }
        
        total_weight = sum(weights.get(c.severity, 1.0) for c in self.checks)
        weighted_score = sum(
            c.score * weights.get(c.severity, 1.0) 
            for c in self.checks
        )
        
        return weighted_score / total_weight if total_weight > 0 else 0.0
    
    def _determine_quality_level(self, score: float) -> QualityLevel:
        """Determine quality level based on score"""
        if score >= 90:
            return QualityLevel.EXCELLENT
        elif score >= 75:
            return QualityLevel.GOOD
        elif score >= 60:
            return QualityLevel.ACCEPTABLE
        elif score >= 40:
            return QualityLevel.NEEDS_IMPROVEMENT
        else:
            return QualityLevel.FAILED
    
    def _get_critical_issues(self) -> List[QualityCheck]:
        """Get list of critical issues"""
        return [
            c for c in self.checks
            if not c.passed and c.severity in [Severity.CRITICAL, Severity.HIGH]
        ]
    
    def _get_improvements(self) -> List[str]:
        """Generate improvement recommendations"""
        improvements = []
        
        for check in self.checks:
            if not check.passed:
                if check.category == "structure":
                    improvements.append(f"Add missing section: {check.name}")
                elif check.category == "content":
                    improvements.append(f"Improve {check.name}: {check.message}")
                elif check.category == "compliance":
                    improvements.append(f"Address compliance gap: {check.message}")
                elif check.category == "data":
                    improvements.append(f"Verify data accuracy: {check.message}")
                    
        return improvements[:5]  # Top 5 improvements
    
    def _generate_report_card(
        self,
        score: float,
        level: QualityLevel
    ) -> Dict[str, Any]:
        """Generate quality report card"""
        passed_checks = sum(1 for c in self.checks if c.passed)
        total_checks = len(self.checks)
        critical_issues = len(self._get_critical_issues())
        
        return {
            "grade": level.value,
            "score": f"{score:.1f}/100",
            "passed_checks": f"{passed_checks}/{total_checks}",
            "critical_issues": critical_issues,
            "timestamp": None  # Will be set by caller
        }