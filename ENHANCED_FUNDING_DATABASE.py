# ENHANCED_FUNDING_DATABASE.py
# Aktualisierte Förderdatenbank 2025 mit intelligenter Matching-Funktion
# Version: 2.0.0 (2025-01-28)

from datetime import datetime
from typing import Dict, Any, List, Optional

# ============================= FUNDING DATABASE 2025 =============================

FUNDING_PROGRAMS_2025 = {
    "bundesweit": [
        {
            "name": "go-digital",
            "provider": "BMWK",
            "amount": "Bis 16.500€ (50% Förderquote)",
            "deadline": "31.12.2025",
            "requirements": "Bis 100 Mitarbeiter, Jahresumsatz max. 20 Mio €",
            "use_case": "Digitalisierung, IT-Sicherheit, Online-Marketing",
            "fit_small": 95,
            "fit_medium": 90,
            "url": "https://www.innovation-beratung-foerderung.de/go-digital",
            "status": "AKTIV",
            "processing_time": "4-6 Wochen",
            "success_rate": 85
        },
        {
            "name": "KfW-Digitalisierungskredit",
            "provider": "KfW",
            "amount": "Bis 25 Mio. € Kredit (günstiger Zins)",
            "deadline": "Laufend",
            "requirements": "KMU und Midcaps",
            "use_case": "Digitale Transformation, Software, Hardware, KI",
            "fit_small": 70,
            "fit_medium": 90,
            "url": "https://www.kfw.de/380",
            "status": "AKTIV",
            "processing_time": "2-4 Wochen",
            "success_rate": 75
        },
        {
            "name": "BAFA Unternehmensberatung",
            "provider": "BAFA",
            "amount": "Bis 3.200€ (50-80% Förderquote)",
            "deadline": "Laufend",
            "requirements": "KMU, max. 249 Mitarbeiter",
            "use_case": "KI-Beratung, Digitalisierungsstrategie",
            "fit_small": 90,
            "fit_medium": 85,
            "url": "https://www.bafa.de/unternehmensberatung",
            "status": "AKTIV",
            "processing_time": "3-4 Wochen",
            "success_rate": 80
        },
        {
            "name": "Mittelstand-Digital",
            "provider": "BMWK",
            "amount": "Kostenlose Beratung & Workshops",
            "deadline": "Laufend",
            "requirements": "KMU aller Branchen",
            "use_case": "KI-Einführung, Prozessoptimierung",
            "fit_small": 100,
            "fit_medium": 100,
            "url": "https://www.mittelstand-digital.de",
            "status": "AKTIV",
            "processing_time": "Sofort",
            "success_rate": 100
        },
        {
            "name": "ZIM - Zentrales Innovationsprogramm",
            "provider": "BMWK",
            "amount": "Bis 550.000€",
            "deadline": "Laufend",
            "requirements": "KMU bis 499 Mitarbeiter",
            "use_case": "F&E-Projekte, KI-Entwicklung",
            "fit_small": 60,
            "fit_medium": 85,
            "url": "https://www.zim.de",
            "status": "AKTIV",
            "processing_time": "8-12 Wochen",
            "success_rate": 65
        },
        {
            # Neu: KOMPASS-Programm für Solo-Selbstständige (ESF Plus 2021-2027)
            # Dieses Programm fördert passgenaue Qualifizierungen und Beratungen
            # zur Krisenvorsorge und Zukunftssicherung von Solo-Selbstständigen. 
            "name": "KOMPASS – Kompakte Hilfe für Solo-Selbstständige",
            "provider": "BMAS / ESF-Plus",
            "amount": "Bis 4.500€ Zuschuss (90% Förderquote)",
            "deadline": "Laufend",
            "requirements": "Solo-Selbstständige aller Branchen",
            "use_case": "Qualifizierung, Weiterbildung, Coaching",
            "fit_small": 100,
            "fit_medium": 60,
            "url": "https://www.esf.de/portal/DE/ESF-Plus-2021-2027/Foerderprogramme/b/kompass.html",
            "status": "AKTIV",
            "processing_time": "1-2 Wochen",
            "success_rate": 75
        }
    ],
    "berlin": [
        {
            "name": "Digitalprämie Berlin",
            "provider": "IBB",
            "amount": "Bis 17.000€ (50% Förderquote)",
            "deadline": "31.12.2025",
            "requirements": "Berliner KMU, 3-249 Mitarbeiter",
            "use_case": "Software, Hardware, E-Commerce, KI",
            "fit_small": 90,
            "fit_medium": 85,
            "url": "https://www.ibb.de/digitalpraemie",
            "status": "AKTIV",
            "processing_time": "6-8 Wochen",
            "success_rate": 70
        },
        {
            "name": "Berlin Mittelstand 4.0",
            "provider": "Berlin Partner",
            "amount": "Kostenlose Beratung",
            "deadline": "Laufend",
            "requirements": "Berliner KMU",
            "use_case": "Digitalisierung, KI-Beratung",
            "fit_small": 100,
            "fit_medium": 100,
            "url": "https://www.berlin-partner.de",
            "status": "AKTIV",
            "processing_time": "1-2 Wochen",
            "success_rate": 95
        }
    ],
    "bayern": [
        {
            "name": "Digitalbonus Bayern",
            "provider": "StMWi",
            "amount": "Bis 10.000€ (50% Förderquote)",
            "deadline": "30.06.2025",
            "requirements": "Bayerische KMU, 3-249 Mitarbeiter",
            "use_case": "IT-Sicherheit, Software, Digitalisierung, KI",
            "fit_small": 85,
            "fit_medium": 80,
            "url": "https://www.digitalbonus.bayern",
            "status": "AKTIV",
            "processing_time": "4-6 Wochen",
            "success_rate": 75
        }
    ],
    "nrw": [
        {
            "name": "Mittelstand.innovativ!",
            "provider": "EFRE.NRW",
            "amount": "Bis 15.000€ Innovationsgutscheine",
            "deadline": "Laufend",
            "requirements": "KMU in NRW",
            "use_case": "Innovation, Digitalisierung, KI-Beratung",
            "fit_small": 85,
            "fit_medium": 90,
            "url": "https://www.efre.nrw.de",
            "status": "AKTIV",
            "processing_time": "3-4 Wochen",
            "success_rate": 80
        }
    ],
    "baden-wuerttemberg": [
        {
            "name": "Digitalisierungsprämie Plus BW",
            "provider": "Ministerium für Wirtschaft BW",
            "amount": "Bis 10.000€",
            "deadline": "31.12.2025",
            "requirements": "KMU in BW",
            "use_case": "Digitale Technologien, Software, KI",
            "fit_small": 85,
            "fit_medium": 80,
            "url": "https://wm.baden-wuerttemberg.de",
            "status": "AKTIV",
            "processing_time": "5-7 Wochen",
            "success_rate": 70
        }
    ],
    "hessen": [
        {
            "name": "Distr@l",
            "provider": "Hessen Trade & Invest",
            "amount": "Bis 10.000€",
            "deadline": "Laufend",
            "requirements": "Hessische KMU",
            "use_case": "Digitalisierung im Handel, E-Commerce",
            "fit_small": 80,
            "fit_medium": 75,
            "url": "https://www.digitalstrategie-hessen.de",
            "status": "AKTIV",
            "processing_time": "4-5 Wochen",
            "success_rate": 75
        }
    ]
}

def match_funding_programs_smart(answers: Dict[str, Any]) -> List[Dict]:
    """
    Intelligente Förderprogramm-Matching Funktion
    """
    # Extrahiere relevante Daten
    bundesland_code = str(answers.get('bundesland', 'BE')).upper()
    size = str(answers.get('unternehmensgroesse', '2-10')).lower()
    budget = answers.get('investitionsbudget', '2000-10000')
    use_cases = answers.get('ki_usecases', [])
    
    # Mapping für Bundesländer
    bundesland_map = {
        'BE': 'berlin',
        'BY': 'bayern', 
        'BW': 'baden-wuerttemberg',
        'NW': 'nrw',
        'HE': 'hessen'
    }
    
    bundesland = bundesland_map.get(bundesland_code, None)
    
    # Bestimme Unternehmensgröße
    fit_key = 'fit_small' if size in ['1', 'solo', '2-10'] else 'fit_medium'
    
    matched_programs = []
    
    # Bundesweite Programme
    for prog in FUNDING_PROGRAMS_2025.get('bundesweit', []):
        score = prog[fit_key]
        
        # Bonus für aktive Programme
        if prog.get('status') == 'AKTIV':
            score += 5
            
        # Bonus für hohe Erfolgsquote
        if prog.get('success_rate', 0) > 80:
            score += 5
            
        matched_programs.append({
            **prog,
            'final_score': score,
            'region': 'Bundesweit'
        })
    
    # Länder-spezifische Programme
    if bundesland and bundesland in FUNDING_PROGRAMS_2025:
        for prog in FUNDING_PROGRAMS_2025[bundesland]:
            score = prog[fit_key] + 10  # Bonus für regionale Programme
            
            if prog.get('status') == 'AKTIV':
                score += 5
                
            matched_programs.append({
                **prog,
                'final_score': score,
                'region': bundesland.capitalize()
            })
    
    # Sortiere nach Score
    matched_programs.sort(key=lambda x: x['final_score'], reverse=True)
    
    return matched_programs[:8]  # Top 8 Programme

def get_funding_timeline(programs: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Gruppiert Programme nach Antragsfristen
    """
    timeline = {
        'sofort': [],
        'q1_2025': [],
        'q2_2025': [],
        'laufend': []
    }
    
    for prog in programs:
        deadline = prog.get('deadline', 'Laufend')
        
        if 'Laufend' in deadline or 'laufend' in deadline:
            timeline['laufend'].append(prog)
        elif 'Kostenlos' in prog.get('amount', '') or 'Sofort' in prog.get('processing_time', ''):
            timeline['sofort'].append(prog)
        elif '03.2025' in deadline or '04.2025' in deadline or '05.2025' in deadline:
            timeline['q1_2025'].append(prog)
        elif '06.2025' in deadline or '07.2025' in deadline or '08.2025' in deadline:
            timeline['q2_2025'].append(prog)
        else:
            timeline['laufend'].append(prog)
    
    return timeline

def calculate_total_funding_potential(programs: List[Dict]) -> int:
    """
    Berechnet maximales Förderpotenzial
    """
    total = 0
    
    for prog in programs[:3]:  # Top 3 kombinierbar
        amount_str = prog.get('amount', '')
        
        # Extrahiere Zahlen aus String
        if 'Kostenlos' in amount_str:
            continue
        elif '16.500' in amount_str or '16500' in amount_str:
            total += 16500
        elif '17.000' in amount_str or '17000' in amount_str:
            total += 17000
        elif '10.000' in amount_str or '10000' in amount_str:
            total += 10000
        elif '15.000' in amount_str or '15000' in amount_str:
            total += 15000
        elif '3.200' in amount_str or '3200' in amount_str:
            total += 3200
    
    return total

def generate_funding_recommendation(answers: Dict[str, Any]) -> str:
    """
    Generiert personalisierte Förderempfehlung
    """
    programs = match_funding_programs_smart(answers)
    
    if not programs:
        return "Keine passenden Förderprogramme gefunden."
    
    best = programs[0]
    total_potential = calculate_total_funding_potential(programs)
    
    recommendation = f"""
    <div class="funding-recommendation">
        <h3>Ihre Top-Förderchance: {best['name']}</h3>
        <p><strong>Fördersumme:</strong> {best['amount']}</p>
        <p><strong>Passung:</strong> {best['final_score']}%</p>
        <p><strong>Bearbeitungszeit:</strong> {best.get('processing_time', 'k.A.')}</p>
        <p><strong>Erfolgsquote:</strong> {best.get('success_rate', 'k.A.')}%</p>
        
        <h4>Maximales Förderpotenzial (kombiniert): {total_potential:,} EUR</h4>
        
        <p><strong>Nächste Schritte:</strong></p>
        <ol>
            <li>Antragsunterlagen von {best['url']} herunterladen</li>
            <li>Kostenvoranschläge einholen</li>
            <li>Antrag bis {best['deadline']} einreichen</li>
        </ol>
    </div>
    """
    
    return recommendation

# Export für gpt_analyze.py
__all__ = [
    'FUNDING_PROGRAMS_2025',
    'match_funding_programs_smart',
    'get_funding_timeline',
    'calculate_total_funding_potential',
    'generate_funding_recommendation'
]