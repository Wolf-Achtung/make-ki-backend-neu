# enhanced_main_integration.py

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import json
from pathlib import Path

# Import der optimierten Module
from gpt_analyze import analyze_briefing_enhanced
from quality_control import ReportQualityController, generate_quality_assured_report
from enhanced_funding_database import match_funding_programs_smart

logger = logging.getLogger(__name__)

class EnhancedReportGenerator:
    """
    Hauptklasse für die Report-Generierung mit allen Optimierungen
    """
    
    def __init__(self):
        self.qc = ReportQualityController()
        self.generation_stats = {}
        self.error_log = []
        
    async def generate_report(self, 
                             form_data: Dict[str, Any],
                             lang: str = 'de',
                             quality_threshold: int = 75) -> Dict[str, Any]:
        """
        Generiert Report mit vollständiger Qualitätskontrolle
        """
        start_time = datetime.now()
        
        try:
            # 1. Daten-Vorverarbeitung
            cleaned_data = self._preprocess_data(form_data)
            
            # 2. Report-Generierung mit Retry-Logic
            max_attempts = 3
            attempt = 0
            context = None
            
            while attempt < max_attempts:
                attempt += 1
                logger.info(f"Generierungsversuch {attempt}/{max_attempts}")
                
                try:
                    # Hauptgenerierung
                    context = await self._generate_with_timeout(
                        cleaned_data, 
                        lang,
                        timeout=120
                    )
                    
                    # Qualitätsprüfung
                    quality_result = self.qc.validate_complete_report(context, lang)
                    
                    if quality_result['overall_score'] >= quality_threshold:
                        logger.info(f"Report erfolgreich generiert. Qualität: {quality_result['quality_level']}")
                        break
                    else:
                        logger.warning(f"Qualität unzureichend: {quality_result['overall_score']:.1f}")
                        context = self._improve_report(context, quality_result)
                        
                except Exception as e:
                    logger.error(f"Fehler bei Versuch {attempt}: {str(e)}")
                    self.error_log.append({
                        'timestamp': datetime.now().isoformat(),
                        'attempt': attempt,
                        'error': str(e)
                    })
                    
                    if attempt == max_attempts:
                        # Fallback zu minimalem Report
                        context = self._generate_fallback_report(cleaned_data, lang)
            
            # 3. Post-Processing
            context = self._postprocess_report(context, lang)
            
            # 4. Statistiken sammeln
            self.generation_stats = {
                'generation_time': (datetime.now() - start_time).total_seconds(),
                'attempts': attempt,
                'quality_score': quality_result.get('overall_score', 0),
                'quality_level': quality_result.get('quality_level', 'UNKNOWN'),
                'errors': len(self.error_log)
            }
            
            # 5. Finale Validierung
            context['meta'].update({
                'quality_badge': quality_result.get('report_card', {}),
                'generation_stats': self.generation_stats,
                'timestamp': datetime.now().isoformat()
            })
            
            return context
            
        except Exception as e:
            logger.error(f"Kritischer Fehler in Report-Generierung: {str(e)}")
            return self._generate_error_report(str(e), lang)
    
    def _preprocess_data(self, form_data: Dict) -> Dict:
        """
        Bereinigt und validiert Eingabedaten
        """
        cleaned = {}
        
        # Encoding-Fixes
        for key, value in form_data.items():
            if isinstance(value, str):
                # Fix common encoding issues
                value = (value
                    .replace('Ã¼', 'ü')
                    .replace('Ã¤', 'ä')
                    .replace('Ã¶', 'ö')
                    .replace('ÃŸ', 'ß')
                    .replace('â€"', '–')
                    .replace('â€œ', '"')
                    .replace('â€', '"')
                    .replace('€', '€'))
            cleaned[key] = value
        
        # Validierung kritischer Felder
        required_fields = [
            'branche', 'unternehmensgroesse', 'bundesland',
            'digitalisierungsgrad', 'automatisierungsgrad'
        ]
        
        for field in required_fields:
            if field not in cleaned:
                # Setze sinnvolle Defaults
                defaults = {
                    'branche': 'beratung',
                    'unternehmensgroesse': '2-10',
                    'bundesland': 'BE',
                    'digitalisierungsgrad': 5,
                    'automatisierungsgrad': 'mittel'
                }
                cleaned[field] = defaults.get(field)
                logger.warning(f"Feld '{field}' fehlte, Default verwendet: {cleaned[field]}")
        
        return cleaned
    
    async def _generate_with_timeout(self, 
                                    data: Dict, 
                                    lang: str,
                                    timeout: int = 120) -> Dict:
        """
        Generiert Report mit Timeout
        """
        try:
            # Asyncio timeout für lange GPT-Calls
            context = await asyncio.wait_for(
                asyncio.to_thread(analyze_briefing_enhanced, data, lang),
                timeout=timeout
            )
            return context
        except asyncio.TimeoutError:
            logger.error(f"Timeout nach {timeout} Sekunden")
            raise Exception("Report-Generierung dauerte zu lange")
    
    def _improve_report(self, 
                       context: Dict, 
                       quality_result: Dict) -> Dict:
        """
        Verbessert Report basierend auf Qualitätsprüfung
        """
        improvements_made = []
        
        for issue in quality_result.get('critical_issues', []):
            if 'ROI' in issue.name:
                context = self._fix_roi_calculation(context)
                improvements_made.append('ROI korrigiert')
                
            elif 'Encoding' in issue.name:
                context = self._fix_encoding(context)
                improvements_made.append('Encoding gefixt')
                
            elif 'Sektion' in issue.name and 'fehlend' in issue.message.lower():
                missing_section = self._identify_missing_section(issue.message)
                if missing_section:
                    context = self._regenerate_section(context, missing_section)
                    improvements_made.append(f'Sektion {missing_section} regeneriert')
        
        logger.info(f"Verbesserungen durchgeführt: {improvements_made}")
        return context
    
    def _fix_roi_calculation(self, context: Dict) -> Dict:
        """
        Korrigiert ROI-Berechnungen
        """
        budget = context.get('roi_investment', 10000)
        
        # Realistische Einsparung berechnen
        max_saving = budget * 3.5  # Max 350% ROI im ersten Jahr
        current_saving = context.get('roi_annual_saving', 0)
        
        if current_saving > max_saving:
            context['roi_annual_saving'] = int(max_saving * 0.85)
            
        # ROI-Monate neu berechnen
        if context['roi_annual_saving'] > 0:
            context['kpi_roi_months'] = int(
                (budget / (context['roi_annual_saving'] / 12))
            )
        
        # 3-Jahres-Wert anpassen
        context['roi_three_year'] = int(
            context['roi_annual_saving'] * 3 - budget
        )
        
        return context
    
    def _postprocess_report(self, context: Dict, lang: str) -> Dict:
        """
        Finale Nachbearbeitung
        """
        # 1. Füge Live-Updates hinzu wenn APIs verfügbar
        if self._has_live_apis():
            context['live_html'] = self._generate_live_section(context, lang)
        
        # 2. Generiere Inhaltsverzeichnis dynamisch
        context['toc'] = self._generate_toc(context, lang)
        
        # 3. Füge Glossar hinzu
        context['glossary'] = self._generate_glossary(lang)
        
        # 4. Versionsinformationen
        context['meta']['version'] = '3.0.0'
        context['meta']['api_versions'] = {
            'gpt': 'gpt-4o-mini',
            'quality_control': '1.0',
            'funding_db': '2025-Q1'
        }
        
        return context
    
    def _generate_fallback_report(self, data: Dict, lang: str) -> Dict:
        """
        Generiert minimalen Fallback-Report
        """
        logger.warning("Fallback-Report wird generiert")
        
        # Basis-KPIs berechnen
        from gpt_analyze import calculate_realistic_kpis
        kpis = calculate_realistic_kpis(data)
        
        if lang == 'de':
            exec_summary = f"""
            <p>Basierend auf Ihren Angaben haben wir einen KI-Reifegrad von {kpis['readiness_score']}% ermittelt.
            Dies zeigt erhebliches Potenzial für Effizienzsteigerungen.</p>
            <p>Mit einem Investment von {kpis['roi_investment']} EUR können Sie jährlich 
            {kpis['roi_annual_saving']} EUR einsparen.</p>
            """
        else:
            exec_summary = f"""
            <p>Based on your information, we determined an AI maturity of {kpis['readiness_score']}%.
            This shows significant potential for efficiency improvements.</p>
            <p>With an investment of EUR {kpis['roi_investment']}, you can save 
            EUR {kpis['roi_annual_saving']} annually.</p>
            """
        
        return {
            **kpis,
            'exec_summary_html': exec_summary,
            'quick_wins_html': self._generate_basic_quick_wins(data, lang),
            'risks_html': self._generate_basic_risks(data, lang),
            'roadmap_html': self._generate_basic_roadmap(kpis, lang),
            'recommendations_html': '',
            'meta': {
                'fallback': True,
                'reason': 'Generation failed, using fallback'
            }
        }
    
    def _has_live_apis(self) -> bool:
        """Prüft Verfügbarkeit von Live-APIs"""
        import os
        return bool(os.getenv('TAVILY_API_KEY')) or bool(os.getenv('SERPAPI_KEY'))
    
    def _generate_error_report(self, error: str, lang: str) -> Dict:
        """Generiert Error-Report"""
        return {
            'error': True,
            'error_message': error,
            'exec_summary_html': f'<p>Ein Fehler ist aufgetreten: {error}</p>' if lang == 'de' else f'<p>An error occurred: {error}</p>',
            'meta': {'error': error, 'timestamp': datetime.now().isoformat()}
        }

# Test-Suite
class ReportTestSuite:
    """
    Umfassende Test-Suite für Report-Generierung
    """
    
    @staticmethod
    def run_all_tests():
        """Führt alle Tests durch"""
        tests = [
            ReportTestSuite.test_minimal_input,
            ReportTestSuite.test_complete_input,
            ReportTestSuite.test_encoding_issues,
            ReportTestSuite.test_extreme_values,
            ReportTestSuite.test_quality_thresholds,
            ReportTestSuite.test_language_variants
        ]
        
        results = []
        for test in tests:
            try:
                result = test()
                results.append({
                    'test': test.__name__,
                    'passed': result['passed'],
                    'message': result.get('message', 'OK')
                })
                print(f"✅ {test.__name__}: PASSED")
            except Exception as e:
                results.append({
                    'test': test.__name__,
                    'passed': False,
                    'message': str(e)
                })
                print(f"❌ {test.__name__}: FAILED - {str(e)}")
        
        # Zusammenfassung
        passed = sum(1 for r in results if r['passed'])
        print(f"\n{'='*50}")
        print(f"Test-Ergebnisse: {passed}/{len(results)} bestanden")
        
        return results
    
    @staticmethod
    def test_minimal_input():
        """Test mit minimalen Eingabedaten"""
        minimal_data = {
            'branche': 'beratung',
            'unternehmensgroesse': '2-10',
            'bundesland': 'BE'
        }
        
        generator = EnhancedReportGenerator()
        context = asyncio.run(generator.generate_report(minimal_data))
        
        assert 'score_percent' in context
        assert context['score_percent'] >= 25
        assert 'exec_summary_html' in context
        
        return {'passed': True}
    
    @staticmethod
    def test_complete_input():
        """Test mit vollständigen Daten"""
        complete_data = {
            'branche': 'it',
            'unternehmensgroesse': '11-100',
            'bundesland': 'BY',
            'hauptleistung': 'Software-Entwicklung',
            'digitalisierungsgrad': 8,
            'automatisierungsgrad': 'eher_hoch',
            'prozesse_papierlos': '81-100',
            'risikofreude': 4,
            'ki_usecases': ['texterstellung', 'datenanalyse', 'prozessautomatisierung'],
            'ki_hemmnisse': ['budget', 'knowhow'],
            'ki_knowhow': 'fortgeschritten',
            'datenschutzbeauftragter': 'ja',
            'budget': '10000-50000'
        }
        
        generator = EnhancedReportGenerator()
        context = asyncio.run(generator.generate_report(complete_data))
        
        # Prüfe erwartete hohe Scores
        assert context['score_percent'] >= 60
        assert context['kpi_compliance'] >= 70
        assert len(context.get('quick_wins_html', '')) > 100
        
        return {'passed': True}
    
    @staticmethod
    def test_encoding_issues():
        """Test Encoding-Probleme"""
        bad_data = {
            'branche': 'beratung',
            'hauptleistung': 'QualitÃ¤tsprÃ¼fung fÃ¼r groÃŸe Unternehmen',
            'unternehmensgroesse': '11-100',
            'bundesland': 'MÃ¼nchen'  # Absichtlich falsch
        }
        
        generator = EnhancedReportGenerator()
        context = asyncio.run(generator.generate_report(bad_data))
        
        # Prüfe ob Encoding gefixt wurde
        assert 'Ã¼' not in str(context)
        assert 'Ã¤' not in str(context)
        
        return {'passed': True}
    
    @staticmethod
    def test_extreme_values():
        """Test mit extremen Werten"""
        extreme_data = {
            'branche': 'beratung',
            'unternehmensgroesse': '1',
            'digitalisierungsgrad': 10,
            'automatisierungsgrad': 'sehr_hoch',
            'budget': 'ueber_50000',
            'risikofreude': 5
        }
        
        generator = EnhancedReportGenerator()
        context = asyncio.run(generator.generate_report(extreme_data))
        
        # ROI sollte trotzdem plausibel sein
        roi_factor = context['roi_annual_saving'] / context['roi_investment']
        assert 0.5 <= roi_factor <= 4.0, f"ROI-Faktor {roi_factor} unrealistisch"
        
        return {'passed': True}
    
    @staticmethod
    def test_quality_thresholds():
        """Test Qualitätsschwellen"""
        data = {
            'branche': 'handel',
            'unternehmensgroesse': '2-10',
            'bundesland': 'HH'
        }
        
        generator = EnhancedReportGenerator()
        
        # Test mit hoher Qualitätsschwelle
        context = asyncio.run(generator.generate_report(data, quality_threshold=85))
        
        quality_badge = context.get('meta', {}).get('quality_badge', {})
        assert quality_badge.get('ready_for_delivery', False)
        
        return {'passed': True}
    
    @staticmethod
    def test_language_variants():
        """Test beide Sprachen"""
        data = {
            'branche': 'marketing',
            'unternehmensgroesse': '11-100',
            'bundesland': 'BE'
        }
        
        generator = EnhancedReportGenerator()
        
        # Deutsch
        context_de = asyncio.run(generator.generate_report(data, lang='de'))
        assert 'Ihr' in context_de.get('exec_summary_html', '')
        
        # Englisch
        context_en = asyncio.run(generator.generate_report(data, lang='en'))
        assert 'Your' in context_en.get('exec_summary_html', '')
        
        return {'passed': True}

# Hauptausführung für Tests
if __name__ == "__main__":
    print("Starte umfassende Test-Suite...")
    print("="*50)
    
    # Führe alle Tests aus
    results = ReportTestSuite.run_all_tests()
    
    # Speichere Test-Report
    with open('test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'results': results,
            'summary': {
                'total': len(results),
                'passed': sum(1 for r in results if r['passed']),
                'failed': sum(1 for r in results if not r['passed'])
            }
        }, f, indent=2)
    
    print("\nTest-Ergebnisse gespeichert in test_results.json")