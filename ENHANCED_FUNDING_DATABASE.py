# ENHANCED_FUNDING_DATABASE.py

FUNDING_PROGRAMS_2025 = {
    "bundesweit": [
        {
            "id": "digital-jetzt",
            "name": "Digital Jetzt",
            "provider": "BMWK",
            "type": "Zuschuss",
            "amount_min": 17000,
            "amount_max": 50000,
            "funding_rate": 40,  # Prozent
            "funding_rate_bonus": 50,  # für Wertschöpfungsketten
            "deadline": "2025-12-31",
            "requirements": {
                "company_size": {"min": 3, "max": 499},
                "min_investment": 17000,
                "eligible_costs": ["Software", "Hardware", "Beratung", "Qualifizierung"],
                "excluded": ["Baumaßnahmen", "Fahrzeuge", "Gebrauchte Wirtschaftsgüter"]
            },
            "processing_time_weeks": 12,
            "combination_allowed": ["go-digital", "KfW-Kredite"],
            "combination_forbidden": ["Andere BMWK-Digitalprogramme"],
            "success_rate": 75,
            "complexity": "mittel",
            "urls": {
                "info": "https://www.bmwk.de/Redaktion/DE/Dossier/digital-jetzt.html",
                "portal": "https://www.digitaljetzt-portal.de"
            },
            "tips": [
                "Investitionsplan detailliert aufschlüsseln",
                "Digitalisierungsplan für 2 Jahre erstellen",
                "Mehrere Angebote einholen"
            ]
        },
        {
            "id": "go-digital",
            "name": "go-digital",
            "provider": "BMWK",
            "type": "Beratungsförderung",
            "amount_min": 1100,
            "amount_max": 16500,
            "funding_rate": 50,
            "deadline": "laufend",
            "requirements": {
                "company_size": {"max": 100},
                "annual_revenue": {"max": 20000000},
                "sectors": ["Handwerk", "Handel", "Dienstleistung", "Industrie"],
                "modules": ["IT-Sicherheit", "Digitale Markterschließung", "Digitalisierte Geschäftsprozesse"]
            },
            "processing_time_weeks": 4,
            "combination_allowed": ["Digital Jetzt", "BAFA-Beratung"],
            "success_rate": 85,
            "complexity": "niedrig",
            "authorized_consultants": True,
            "tips": [
                "Nur autorisierte Beratungsunternehmen",
                "30 Beratertage maximal",
                "Eigenanteil 50% direkt an Berater"
            ]
        },
        {
            "id": "kfw-digitalisierung",
            "name": "KfW-Digitalisierungs- und Innovationskredit",
            "provider": "KfW",
            "type": "Kredit",
            "amount_min": 25000,
            "amount_max": 25000000,
            "interest_rate_from": 4.65,  # Stand 12/2024
            "deadline": "laufend",
            "requirements": {
                "company_age_years": {"min": 2},
                "use_cases": ["Digitalisierung", "Innovation", "KI", "Industrie 4.0"],
                "tilgungsfrei_jahre": {"max": 3}
            },
            "processing_time_weeks": 6,
            "combination_allowed": ["Alle Zuschuss-Programme"],
            "success_rate": 70,
            "complexity": "hoch",
            "bank_required": True
        }
    ],
    
    "laender": {
        "BY": [  # Bayern
            {
                "id": "digitalbonus-bayern",
                "name": "Digitalbonus Bayern Standard",
                "provider": "StMWi Bayern",
                "amount_max": 10000,
                "funding_rate": 50,
                "requirements": {
                    "company_size": {"min": 3, "max": 250},
                    "location": "Bayern",
                    "min_investment": 4000
                },
                "deadline": "2025-12-31",
                "budget_remaining": "Prüfung erforderlich",
                "tips": ["Schnell beantragen - Budget begrenzt"]
            }
        ],
        
        "BW": [  # Baden-Württemberg
            {
                "id": "digitalisierungspraemie-plus",
                "name": "Digitalisierungsprämie Plus",
                "provider": "Ministerium für Wirtschaft BW",
                "amount_max": 10000,
                "funding_rate": 40,
                "requirements": {
                    "company_size": {"max": 100},
                    "location": "Baden-Württemberg"
                },
                "special": "Bonus für Nachhaltigkeitsprojekte"
            }
        ],
        
        "BE": [  # Berlin
            {
                "id": "digitalpraemie-berlin",
                "name": "Digitalprämie Berlin",
                "provider": "IBB",
                "amount_max": 17000,
                "funding_rate": 50,
                "requirements": {
                    "company_size": {"max": 249},
                    "location": "Berlin",
                    "sectors_priority": ["Kultur", "Kreativ", "Tech"]
                },
                "deadline": "2025-06-30",
                "special": "KI-Projekte bevorzugt"
            }
        ]
    },
    
    "eu": [
        {
            "id": "digital-europe",
            "name": "Digital Europe Programme",
            "provider": "EU Commission",
            "amount_min": 50000,
            "amount_max": 15000000,
            "funding_rate": 50,
            "requirements": {
                "consortium": True,
                "countries_min": 3,
                "focus": ["KI", "Cybersecurity", "HPC", "Digital Skills"]
            },
            "complexity": "sehr hoch",
            "success_rate": 15
        }
    ]
}

def match_funding_programs_smart(answers: Dict[str, Any]) -> List[Dict]:
    """
    Intelligentes Matching von Förderprogrammen basierend auf Unternehmensparametern
    """
    matched_programs = []
    
    # Parameter extrahieren
    company_size = get_employee_count(answers.get('unternehmensgroesse'))
    bundesland = answers.get('bundesland', 'BE')
    budget = get_budget_amount(answers.get('budget'))
    revenue = get_revenue_estimate(answers.get('jahresumsatz', 'unbekannt'))
    
    # Scoring-Funktion
    def score_program(program: Dict) -> float:
        score = 0.0
        
        # Größen-Check
        req = program.get('requirements', {})
        size_req = req.get('company_size', {})
        if size_req:
            if size_req.get('min', 0) <= company_size <= size_req.get('max', 999):
                score += 30
            else:
                return 0  # Ausschluss
        
        # Budget-Fit
        if program.get('amount_min', 0) <= budget * 2:  # 2x Budget als Investition
            score += 20
        
        # Komplexität vs. Know-how
        complexity_map = {'niedrig': 1, 'mittel': 2, 'hoch': 3, 'sehr hoch': 4}
        program_complexity = complexity_map.get(program.get('complexity', 'mittel'), 2)
        knowledge_level = get_knowledge_level(answers.get('ki_knowhow'))
        
        if knowledge_level >= program_complexity:
            score += 20
        else:
            score -= 10
        
        # Erfolgswahrscheinlichkeit
        success_rate = program.get('success_rate', 50)
        score += success_rate * 0.3
        
        # Deadline-Bonus (Dringlichkeit)
        deadline = program.get('deadline', 'laufend')
        if deadline != 'laufend':
            try:
                deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
                days_remaining = (deadline_date - datetime.now()).days
                if days_remaining < 180:
                    score += 10  # Dringlichkeitsbonus
            except:
                pass
        
        # Regional-Bonus
        if bundesland in program.get('id', ''):
            score += 15
        
        return score
    
    # Bundesweite Programme
    for program in FUNDING_PROGRAMS_2025['bundesweit']:
        program_score = score_program(program)
        if program_score > 30:  # Mindest-Score
            matched_programs.append({
                **program,
                'match_score': program_score,
                'region': 'Bundesweit'
            })
    
    # Länderprogramme
    if bundesland in FUNDING_PROGRAMS_2025['laender']:
        for program in FUNDING_PROGRAMS_2025['laender'][bundesland]:
            program_score = score_program(program)
            if program_score > 30:
                matched_programs.append({
                    **program,
                    'match_score': program_score,
                    'region': bundesland
                })
    
    # EU-Programme (nur bei entsprechender Größe)
    if company_size >= 50:
        for program in FUNDING_PROGRAMS_2025.get('eu', []):
            program_score = score_program(program) * 0.7  # Komplexitäts-Malus
            if program_score > 25:
                matched_programs.append({
                    **program,
                    'match_score': program_score,
                    'region': 'EU'
                })
    
    # Sortieren und Top 6 zurückgeben
    matched_programs.sort(key=lambda x: x['match_score'], reverse=True)
    
    # Kombinationsempfehlungen hinzufügen
    if len(matched_programs) >= 2:
        add_combination_recommendations(matched_programs)
    
    return matched_programs[:6]

def add_combination_recommendations(programs: List[Dict]):
    """
    Fügt Kombinationsempfehlungen hinzu
    """
    combinations = []
    
    for i, prog1 in enumerate(programs[:3]):
        for prog2 in programs[i+1:4]:
            # Check if combination allowed
            allowed1 = prog1.get('combination_allowed', [])
            forbidden1 = prog1.get('combination_forbidden', [])
            
            can_combine = (
                prog2['id'] in allowed1 or 
                prog2['name'] in allowed1 or
                (prog2['id'] not in forbidden1 and prog2['name'] not in forbidden1)
            )
            
            if can_combine:
                combinations.append({
                    'programs': [prog1['name'], prog2['name']],
                    'total_funding': prog1.get('amount_max', 0) + prog2.get('amount_max', 0),
                    'strategy': determine_combination_strategy(prog1, prog2)
                })
    
    return combinations

def determine_combination_strategy(prog1: Dict, prog2: Dict) -> str:
    """
    Bestimmt optimale Kombinationsstrategie
    """
    if prog1['type'] == 'Beratungsförderung' and prog2['type'] == 'Zuschuss':
        return "Erst Beratung, dann Umsetzung"
    elif prog1['type'] == 'Zuschuss' and prog2['type'] == 'Kredit':
        return "Zuschuss für Software, Kredit für Hardware"
    else:
        return "Parallel beantragen für maximale Förderung"