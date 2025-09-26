# gpt_analyze.py - Gold Standard+ Final Version KOMPLETT
# Version: 2025-12-19 (PRODUCTION READY)
# Features: Vollständige Fragebogen-Integration, KPI-Berechnung, Tool-Matching, Förder-Analyse

from __future__ import annotations

import os
import re
import json
import csv
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

# ============================= Branchenbenchmarks 2025 =============================

@dataclass
class IndustryBenchmark:
    """Aktuelle Branchendurchschnittswerte für KI-Adoption"""
    digitalisierung_avg: float  # 1-10 Skala
    automatisierung_avg: float  # Prozent
    ki_adoption_rate: float     # Prozent der Unternehmen mit KI
    roi_expectation: float      # Faktor (z.B. 3.2 = 320% ROI)
    time_to_value_days: int     # Durchschnitt bis erste Ergebnisse

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
            "fit_score": 95
        },
        {
            "name": "Jasper AI",
            "desc": "Marketing-Content Automation",
            "use_case": "Blog, Social Media, Ads",
            "cost": "Ab 39€/Monat",
            "complexity": "Mittel",
            "time_to_value": "3-5 Tage",
            "badges": ["API", "Templates", "Team"],
            "fit_score": 80
        }
    ],
    "spracherkennung": [
        {
            "name": "Whisper (lokal)",
            "desc": "Open Source Transkription",
            "use_case": "Meetings, Interviews",
            "cost": "Kostenlos",
            "complexity": "Mittel",
            "time_to_value": "1 Tag Setup",
            "badges": ["Open Source", "Lokal", "Kostenlos"],
            "fit_score": 90
        },
        {
            "name": "tl;dv",
            "desc": "Meeting-Recorder mit KI",
            "use_case": "Zoom/Teams Meetings",
            "cost": "Kostenlos / Pro 20€",
            "complexity": "Einfach",
            "time_to_value": "Sofort",
            "badges": ["DSGVO", "Integration", "Freemium"],
            "fit_score": 85
        }
    ],
    "prozessautomatisierung": [
        {
            "name": "n8n",
            "desc": "Open Source Workflow Tool",
            "use_case": "API-Integration, Workflows",
            "cost": "Kostenlos selbst-hosted",
            "complexity": "Mittel",
            "time_to_value": "1-2 Wochen",
            "badges": ["Open Source", "EU-Hosting", "Kostenlos"],
            "fit_score": 92
        },
        {
            "name": "Make (Integromat)",
            "desc": "Visual Workflow Builder",
            "use_case": "Automatisierung ohne Code",
            "cost": "Ab 9€/Monat",
            "complexity": "Einfach",
            "time_to_value": "2-3 Tage",
            "badges": ["Low-Code", "DSGVO", "Templates"],
            "fit_score": 88
        }
    ],
    "datenanalyse": [
        {
            "name": "Metabase",
            "desc": "Open Source BI Tool",
            "use_case": "Dashboards, Reports",
            "cost": "Kostenlos / Cloud ab 85€",
            "complexity": "Mittel",
            "time_to_value": "1 Woche",
            "badges": ["Open Source", "DSGVO", "Self-Host"],
            "fit_score": 85
        },
        {
            "name": "Tableau",
            "desc": "Enterprise BI Platform",
            "use_case": "Komplexe Analysen",
            "cost": "Ab 15€/User/Monat",
            "complexity": "Hoch",
            "time_to_value": "2-4 Wochen",
            "badges": ["Enterprise", "Cloud", "Support"],
            "fit_score": 75
        }
    ],
    "kundensupport": [
        {
            "name": "Typebot",
            "desc": "Open Source Chatbot",
            "use_case": "Website-Chat, FAQ",
            "cost": "Kostenlos selbst-hosted",
            "complexity": "Einfach",
            "time_to_value": "1-2 Tage",
            "badges": ["Open Source", "DSGVO", "No-Code"],
            "fit_score": 90
        },
        {
            "name": "Crisp",
            "desc": "Customer Messaging",
            "use_case": "Live-Chat + KI-Assistent",
            "cost": "Kostenlos / Pro ab 25€",
            "complexity": "Sehr einfach",
            "time_to_value": "30 Minuten",
            "badges": ["DSGVO", "Freemium", "Widget"],
            "fit_score": 87
        }
    ],
    "wissensmanagement": [
        {
            "name": "Outline",
            "desc": "Team Knowledge Base",
            "use_case": "Dokumentation, Wiki",
            "cost": "Kostenlos bis 5 User",
            "complexity": "Einfach",
            "time_to_value": "1 Tag",
            "badges": ["Open Source", "Markdown", "Search"],
            "fit_score": 88
        },
        {
            "name": "BookStack",
            "desc": "Dokumentations-Platform",
            "use_case": "Handbücher, Prozesse",
            "cost": "Kostenlos",
            "complexity": "Einfach",
            "time_to_value": "2-3 Tage",
            "badges": ["Open Source", "Self-Host", "WYSIWYG"],
            "fit_score": 85
        }
    ],
    "marketing": [
        {
            "name": "Canva Magic",
            "desc": "KI-Design Tool",
            "use_case": "Social Media, Präsentationen",
            "cost": "Kostenlos / Pro ab 12€",
            "complexity": "Sehr einfach",
            "time_to_value": "Sofort",
            "badges": ["Templates", "KI-Features", "Team"],
            "fit_score": 92
        },
        {
            "name": "Buffer AI",
            "desc": "Social Media Automation",
            "use_case": "Post-Planung mit KI",
            "cost": "Ab 15€/Monat",
            "complexity": "Einfach",
            "time_to_value": "1 Tag",
            "badges": ["Scheduling", "Analytics", "KI-Text"],
            "fit_score": 85
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
            "fit_medium": 90
        },
        {
            "name": "go-digital",
            "provider": "BMWK",
            "amount": "Bis 16.500€ (50% Förderquote)",
            "deadline": "Laufend",
            "requirements": "Bis 100 Mitarbeiter",
            "use_case": "Digitalisierung, IT-Sicherheit, Online-Marketing",
            "fit_small": 90,
            "fit_medium": 85
        },
        {
            "name": "INNO-KOM",
            "provider": "BMWi",
            "amount": "Bis 550.000€",
            "deadline": "Laufend",
            "requirements": "Forschungsprojekte",
            "use_case": "F&E, Prototypen",
            "fit_small": 60,
            "fit_medium": 75
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
            "fit_medium": 100
        },
        {
            "name": "Digitalprämie Berlin",
            "provider": "IBB",
            "amount": "Bis 17.000€",
            "deadline": "30.06.2025",
            "requirements": "Berliner KMU",
            "use_case": "Software, Prozessoptimierung",
            "fit_small": 85,
            "fit_medium": 80
        }
    ],
    "bayern": [
        {
            "name": "Digitalbonus Bayern",
            "provider": "StMWi",
            "amount": "Bis 10.000€",
            "deadline": "31.12.2025",
            "requirements": "KMU in Bayern",
            "use_case": "IT-Sicherheit, Software",
            "fit_small": 85,
            "fit_medium": 80
        }
    ],
    "nrw": [
        {
            "name": "Mittelstand.innovativ!",
            "provider": "EFRE.NRW",
            "amount": "Bis 15.000€",
            "deadline": "Laufend",
            "requirements": "KMU in NRW",
            "use_case": "Innovation, Digitalisierung",
            "fit_small": 80,
            "fit_medium": 85
        }
    ]
}
# ============================= Live-Daten Integration =============================
# Fügen Sie diesen Code in gpt_analyze.py nach den Import-Statements ein

import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# ============================= Live Search APIs =============================

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
            print(f"Tavily API error: {e}")
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
            print(f"SerpAPI error: {e}")
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
        funding_query = f"Fördermittel KI Digitalisierung {bundesland} {datetime.now().year} Antragsfrist"
        news["funding"] = self.search_tavily(funding_query, days=30, max_results=4)
        
        # Trends
        trends_query = f"KI Trends {branche} Mittelstand Deutschland 2025"
        news["trends"] = self.search_tavily(trends_query, days=30, max_results=3)
        
        return news

# ============================= Live Förderprogramme =============================

def fetch_live_funding_programs(bundesland: str, company_size: str) -> List[Dict[str, Any]]:
    """Holt aktuelle Förderprogramme via API"""
    fetcher = LiveDataFetcher()
    
    # Basis-Query
    size_text = "KMU" if company_size in ['2-10', '11-100'] else "Einzelunternehmer"
    queries = [
        f"Förderprogramme Digitalisierung {bundesland} {size_text} {datetime.now().year}",
        f"Digital Jetzt BMWK Antragsfrist {datetime.now().year}",
        f"go-digital Förderung {bundesland} Deadline"
    ]
    
    programs = []
    seen_titles = set()
    
    for query in queries:
        # Versuche erst Tavily (aktueller)
        results = fetcher.search_tavily(query, days=60, max_results=5)
        
        # Fallback zu SerpAPI
        if not results:
            results = fetcher.search_serpapi(query, location=bundesland, max_results=5)
        
        for result in results:
            title = result.get("title", "")
            if not title or title in seen_titles:
                continue
                
            seen_titles.add(title)
            
            # Versuche Deadline zu extrahieren
            content = f"{title} {result.get('snippet', '')} {result.get('date', '')}"
            deadline = extract_deadline_from_text(content)
            
            # Versuche Fördersumme zu extrahieren
            amount = extract_amount_from_text(content)
            
            programs.append({
                "name": clean_program_name(title),
                "url": result.get("url", ""),
                "amount": amount or "Auf Anfrage",
                "deadline": deadline or "Laufend",
                "source": "Live-Daten",
                "relevance": calculate_relevance_score(title, content, bundesland, company_size)
            })
    
    # Sortiere nach Relevanz
    programs.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    
    return programs[:8]  # Top 8 Programme

def extract_deadline_from_text(text: str) -> Optional[str]:
    """Extrahiert Deadline aus Text"""
    if not text:
        return None
        
    text = text.lower()
    
    # Muster für Datumsangaben
    patterns = [
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})",  # 31.12.2025
        r"(\d{1,2})\.\s*([a-zäöü]+)\s+(\d{4})",  # 31. Dezember 2025
        r"bis\s+(\d{1,2})\.(\d{1,2})\.(\d{4})",  # bis 31.12.2025
        r"frist:?\s*(\d{1,2})\.(\d{1,2})\.(\d{4})",  # Frist: 31.12.2025
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                # Konvertiere zu einheitlichem Format
                groups = match.groups()
                if len(groups) == 3:
                    day, month, year = groups
                    if month.isdigit():
                        return f"{day.zfill(2)}.{month.zfill(2)}.{year}"
            except:
                continue
                
    # Keywords für laufende Programme
    if any(word in text for word in ["laufend", "fortlaufend", "keine frist", "dauerhaft"]):
        return "Laufend"
        
    return None

def extract_amount_from_text(text: str) -> Optional[str]:
    """Extrahiert Fördersumme aus Text"""
    if not text:
        return None
        
    # Muster für Beträge
    patterns = [
        r"bis\s+zu\s+([\d.]+)\s*(?:€|EUR|Euro)",
        r"max(?:imal)?\s+([\d.]+)\s*(?:€|EUR|Euro)",
        r"([\d.]+)\s*(?:€|EUR|Euro)\s+(?:förderung|zuschuss)",
        r"förder(?:summe|betrag):?\s*([\d.]+)\s*(?:€|EUR|Euro)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = match.group(1).replace(".", "")
            try:
                amount_int = int(amount)
                if amount_int >= 1000:
                    return f"Bis {amount_int:,} €".replace(",", ".")
            except:
                continue
                
    # Prozentangaben
    if "50%" in text or "50 %" in text:
        return "50% Förderquote"
    if "40%" in text or "40 %" in text:
        return "40% Förderquote"
        
    return None

def clean_program_name(title: str) -> str:
    """Bereinigt Programmnamen"""
    # Entferne typische Zusätze
    title = re.sub(r'\s*[-–]\s*.*?(Förderung|Programm|Antrag).*', '', title)
    title = re.sub(r'\s*\|.*', '', title)
    title = re.sub(r'\s*\(.*?\)', '', title)
    
    # Kürze zu lange Titel
    if len(title) > 50:
        title = title[:47] + "..."
        
    return title.strip()

def calculate_relevance_score(title: str, content: str, bundesland: str, company_size: str) -> int:
    """Berechnet Relevanz-Score für Förderprogramm"""
    score = 50  # Basis
    
    text = (title + " " + content).lower()
    
    # Keywords erhöhen Score
    keywords = {
        "digital": 10,
        "ki": 15,
        "künstliche intelligenz": 15,
        "mittelstand": 10,
        "kmu": 10,
        "automatisierung": 10,
        "software": 8,
        "beratung": 8,
        bundesland.lower(): 20,
        "2025": 10,
        str(datetime.now().year): 10
    }
    
    for keyword, points in keywords.items():
        if keyword in text:
            score += points
            
    # Negative Keywords
    if any(word in text for word in ["abgelaufen", "beendet", "ausgeschöpft"]):
        score -= 30
        
    return min(100, max(0, score))

# ============================= Live Tools Discovery =============================

def fetch_live_tools(use_cases: List[str], budget: str) -> List[Dict[str, Any]]:
    """Entdeckt neue KI-Tools basierend auf Use Cases"""
    fetcher = LiveDataFetcher()
    
    prefer_free = "unter_2000" in budget or "2000" in budget
    
    tools = []
    seen_names = set()
    
    for use_case in use_cases[:3]:  # Top 3 Use Cases
        if prefer_free:
            query = f"{use_case} KI Tool kostenlos Open Source DSGVO 2025"
        else:
            query = f"{use_case} KI Tool Enterprise DSGVO compliant deutsch 2025"
            
        results = fetcher.search_tavily(query, days=60, max_results=5)
        
        for result in results:
            title = result.get("title", "")
            url = result.get("url", "")
            
            # Extrahiere Tool-Name
            tool_name = extract_tool_name(title)
            if not tool_name or tool_name in seen_names:
                continue
                
            seen_names.add(tool_name)
            
            # Analysiere Features
            content = result.get("snippet", "")
            features = extract_tool_features(content)
            
            tools.append({
                "name": tool_name,
                "url": url,
                "use_case": use_case,
                "features": features,
                "source": "Live-Discovery"
            })
            
    return tools[:10]

def extract_tool_name(title: str) -> Optional[str]:
    """Extrahiert Tool-Namen aus Titel"""
    # Entferne generische Teile
    title = re.sub(r'(Review|Test|Comparison|Die besten|Top \d+).*', '', title)
    title = re.sub(r'[-–:].*', '', title)
    
    # Erste 1-3 Wörter sind meist der Tool-Name
    words = title.strip().split()[:3]
    if words:
        return " ".join(words).strip()
    return None

def extract_tool_features(content: str) -> List[str]:
    """Extrahiert Features aus Beschreibung"""
    features = []
    
    feature_keywords = {
        "dsgvo": "DSGVO-konform",
        "gdpr": "GDPR-compliant",
        "open source": "Open Source",
        "kostenlos": "Kostenlos",
        "free": "Kostenlose Version",
        "api": "API verfügbar",
        "integration": "Integrationen",
        "deutsch": "Deutsche Oberfläche",
        "eu": "EU-Hosting"
    }
    
    content_lower = content.lower()
    for keyword, feature in feature_keywords.items():
        if keyword in content_lower:
            features.append(feature)
            
    return features[:4]  # Max 4 Features

# ============================= Integration in Hauptfunktion =============================

def generate_live_updates_section(answers: Dict[str, Any]) -> str:
    """Generiert Live-Updates Sektion mit echten Daten"""
    
    branche = safe_str(answers.get('branche', 'beratung'))
    bundesland = safe_str(answers.get('bundesland', 'Berlin'))
    
    fetcher = LiveDataFetcher()
    news = fetcher.get_current_ai_news(branche, bundesland)
    
    html = "<h3>Aktuelle Entwicklungen für Sie</h3>"
    
    # Regulatorische Updates
    if news["regulations"]:
        html += "<h4>🔍 Compliance & Regulierung</h4><ul>"
        for item in news["regulations"][:2]:
            title = item.get("title", "")
            url = item.get("url", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{clean_text(title)}</a></li>'
        html += "</ul>"
    
    # Neue Tools
    if news["tools"]:
        html += "<h4>🛠️ Neue KI-Tools</h4><ul>"
        for item in news["tools"][:3]:
            title = item.get("title", "")
            url = item.get("url", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{clean_text(title)}</a></li>'
        html += "</ul>"
    
    # Förderprogramme
    if news["funding"]:
        html += "<h4>💰 Aktuelle Fördermöglichkeiten</h4><ul>"
        for item in news["funding"][:2]:
            title = item.get("title", "")
            url = item.get("url", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{clean_text(title)}</a></li>'
        html += "</ul>"
    
    # Trends
    if news["trends"]:
        html += "<h4>📈 Branchentrends</h4><ul>"
        for item in news["trends"][:2]:
            title = item.get("title", "")
            url = item.get("url", "")
            if title and url:
                html += f'<li><a href="{url}" target="_blank">{clean_text(title)}</a></li>'
        html += "</ul>"
    
    if not any([news["regulations"], news["tools"], news["funding"], news["trends"]]):
        html += "<p>Aktuell keine neuen Updates verfügbar.</p>"
    
    return html

def enhanced_match_funding_programs(answers: Dict[str, Any]) -> str:
    """Erweiterte Förderprogramm-Matching mit Live-Daten"""
    
    bundesland = safe_str(answers.get('bundesland', 'Berlin'))
    size = safe_str(answers.get('unternehmensgroesse', '2-10'))
    
    # Basis-Programme aus Datenbank
    static_programs = match_funding_programs_static(answers)  # Original-Funktion
    
    # Live-Programme
    live_programs = fetch_live_funding_programs(bundesland, size)
    
    # Kombiniere und dedupliziere
    all_programs = []
    seen_names = set()
    
    # Erst statische Programme
    for prog in static_programs:
        name = prog.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            all_programs.append(prog)
    
    # Dann Live-Programme
    for prog in live_programs:
        name = prog.get("name", "")
        if name and name not in seen_names:
            seen_names.add(name)
            all_programs.append(prog)
    
    # Generiere erweiterte HTML-Tabelle
    html = """
    <table>
        <thead>
            <tr>
                <th>Programm</th>
                <th>Förderung</th>
                <th>Frist</th>
                <th>Quelle</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for prog in all_programs[:8]:  # Top 8
        source_badge = "📊 Datenbank" if prog.get("source") != "Live-Daten" else "🔴 Live"
        html += f"""
        <tr>
            <td>
                <strong>{prog.get('name', 'Unbekannt')}</strong><br/>
                <small>{prog.get('provider', '')} - {prog.get('use_case', '')}</small>
            </td>
            <td>{prog.get('amount', 'Auf Anfrage')}</td>
            <td>{prog.get('deadline', 'Laufend')}</td>
            <td>{source_badge}</td>
        </tr>
        """
    
    html += """
        </tbody>
    </table>
    <div class="info-box" style="margin-top: 15px;">
        <div class="info-box-title">💡 Hinweis zu Live-Daten</div>
        Mit 🔴 markierte Programme wurden gerade aktuell recherchiert. 
        Prüfen Sie die Details vor Antragstellung.
    </div>
    """
    
    return html
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
    text = text.replace('–', '-').replace('"', '"').replace('"', '"')
    
    # Remove code fences
    text = re.sub(r'^```[a-zA-Z0-9_-]*\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    
    # Clean whitespace
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

# ============================= KPI-Berechnung aus Fragebogen =============================

def calculate_kpis_from_answers(answers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Berechnet alle KPIs basierend auf den tatsächlichen Fragebogen-Antworten
    """
    # Extrahiere Basis-Werte aus Fragebogen
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
    knowledge = knowledge_map.get(safe_str(answers.get('ki_kenntnisse', 'fortgeschritten')).lower(), 50)
    
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
        '11-100': {'employees': 50, 'revenue': 4000000, 'cost_base': 2500000}
    }
    factors = size_factors.get(size, size_factors['2-10'])
    
    # Budget aus Fragebogen
    budget_map = {
        'unter_2000': 1500,
        '2000-10000': 6000,
        '2.000-10.000': 6000,
        '10000-50000': 25000,
        'ueber_50000': 75000
    }
    budget_text = safe_str(answers.get('budget', '2000-10000')).lower().replace(' ', '').replace('€', '')
    budget = budget_map.get(budget_text, 6000)
    
    # Effizienzpotenzial basierend auf aktuellem Stand
    efficiency_gap = 100 - auto  # Je weniger automatisiert, desto mehr Potenzial
    efficiency_potential = int(efficiency_gap * 0.6)  # Realistisch 60% des Gaps
    
    # Kosteneinsparung
    cost_saving_potential = int(efficiency_potential * 0.7)  # 70% der Effizienz = Kosten
    annual_saving = int(factors['cost_base'] * (cost_saving_potential / 100))
    
    # ROI-Berechnung
    if annual_saving > 0:
        roi_months = min(36, max(3, int((budget / annual_saving) * 12)))
    else:
        roi_months = 24
        
    # Compliance Score aus Governance-Antworten
    compliance = 30  # Basis
    if safe_str(answers.get('datenschutzbeauftragter', '')).lower() in ['ja', 'yes']:
        compliance += 25
    if safe_str(answers.get('dsgvo_folgenabschaetzung', '')).lower() in ['ja', 'teilweise', 'yes']:
        compliance += 20
    if safe_str(answers.get('eu_ai_act_kenntnis', '')).lower() in ['gut', 'sehr_gut', 'good']:
        compliance += 20
    if safe_str(answers.get('richtlinien_governance', '')).lower() in ['ja', 'teilweise', 'yes']:
        compliance += 15
        
    # Innovation Index
    has_innovation_team = safe_str(answers.get('innovationsteam', '')).lower() in ['ja', 'yes', 'internes_team']
    innovation = int(
        risk * 15 +                                    # Risikobereitschaft
        (knowledge/100) * 30 +                         # KI-Kenntnisse
        (20 if has_innovation_team else 0) +           # Innovationsteam
        (digital/10) * 35                              # Digitalisierung
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

# ============================= Content-Generierung =============================

def match_tools_to_company(answers: Dict[str, Any]) -> str:
    """Matched Tools basierend auf Use Cases"""
    use_cases = answers.get('ki_usecases', [])
    budget = answers.get('budget', '2000-10000')
    
    prefer_free = 'unter_2000' in budget or '2000' in budget
    
    matched_tools = []
    
    for uc in use_cases:
        uc_key = safe_str(uc).lower().replace(' ', '').replace('-', '')
        
        for db_key in TOOL_DATABASE.keys():
            if db_key in uc_key or uc_key in db_key:
                tools = TOOL_DATABASE[db_key]
                
                if prefer_free:
                    tools = sorted(tools, key=lambda x: (
                        'Kostenlos' not in x['badges'],
                        -x['fit_score']
                    ))
                else:
                    tools = sorted(tools, key=lambda x: -x['fit_score'])
                
                if tools:
                    matched_tools.append(tools[0])
                break
    
    html = ""
    for tool in matched_tools[:6]:
        badges_html = ' '.join([f'<span class="chip">{b}</span>' for b in tool['badges']])
        html += f"""
        <div class="tool-item">
            <div class="tool-name">{tool['name']}</div>
            <div class="tool-desc">{tool['desc']} - {tool['use_case']}</div>
            <div style="margin-top: 5px;">
                <strong>Kosten:</strong> {tool['cost']} | 
                <strong>Aufwand:</strong> {tool['complexity']} | 
                <strong>Zeit bis Nutzen:</strong> {tool['time_to_value']}
            </div>
            <div style="margin-top: 5px;">{badges_html}</div>
        </div>
        """
    
    return html if matched_tools else "<p>Individuelle Tool-Beratung empfohlen.</p>"

def match_funding_programs(answers: Dict[str, Any]) -> str:
    """Matched Förderprogramme"""
    bundesland = safe_str(answers.get('bundesland', 'berlin')).lower()
    size = safe_str(answers.get('unternehmensgroesse', '2-10'))
    
    fit_key = 'fit_small' if size in ['solo', '2-10', '1'] else 'fit_medium'
    
    programs = []
    
    for prog in FUNDING_PROGRAMS['bundesweit']:
        prog['fit'] = prog[fit_key]
        programs.append(prog)
    
    if bundesland in FUNDING_PROGRAMS:
        for prog in FUNDING_PROGRAMS[bundesland]:
            prog['fit'] = prog[fit_key]
            programs.append(prog)
    
    programs = sorted(programs, key=lambda x: -x['fit'])
    
    html = """
    <table>
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
    
    for prog in programs[:5]:
        fit_color = '#10B981' if prog['fit'] > 80 else '#F59E0B' if prog['fit'] > 60 else '#3B82F6'
        html += f"""
        <tr>
            <td>
                <strong>{prog['name']}</strong><br/>
                <small>{prog['provider']} - {prog['use_case']}</small>
            </td>
            <td>{prog['amount']}</td>
            <td>{prog['deadline']}</td>
            <td>
                <div class="progress-bar" style="width: 80px;">
                    <div class="progress-fill" style="width: {prog['fit']}%; background: {fit_color};"></div>
                </div>
                <small>{prog['fit']}% Passung</small>
            </td>
        </tr>
        """
    
    html += """
        </tbody>
    </table>
    <div class="info-box" style="margin-top: 15px;">
        <div class="info-box-title">💡 Förder-Tipp</div>
        Kombinieren Sie Programme für maximale Unterstützung. Wir helfen bei der Antragstellung.
    </div>
    """
    
    return html

def generate_data_driven_executive_summary(answers: Dict[str, Any], kpis: Dict[str, Any]) -> str:
    """Executive Summary mit echten Daten"""
    strengths = []
    if kpis['digitalisierungsgrad'] >= 8:
        strengths.append("exzellente digitale Infrastruktur")
    if kpis['risikofreude'] >= 4:
        strengths.append("hohe Innovationsbereitschaft")
    if kpis['automatisierungsgrad'] >= 70:
        strengths.append("fortgeschrittene Automatisierung")
    
    hemmnisse = answers.get('ki_hemmnisse', [])
    challenges = []
    for h in hemmnisse:
        h_lower = safe_str(h).lower()
        if 'budget' in h_lower:
            challenges.append("Budgetrestriktionen")
        elif 'zeit' in h_lower:
            challenges.append("Zeitressourcen")
        elif 'know' in h_lower:
            challenges.append("Kompetenzaufbau")
    
    branche = safe_str(answers.get('branche', 'beratung')).lower()
    benchmark = INDUSTRY_BENCHMARKS.get(branche, INDUSTRY_BENCHMARKS['default'])
    
    summary = f"""
    <p><strong>Mit einem KI-Reifegrad von {kpis['readiness_score']}% positioniert sich Ihr Unternehmen 
    {'deutlich über' if kpis['readiness_score'] > 70 else 'im' if kpis['readiness_score'] > 50 else 'unter'} 
    dem Branchendurchschnitt.</strong></p>
    
    <p>Die Analyse zeigt ein <strong>Effizienzsteigerungspotenzial von {kpis['kpi_efficiency']}%</strong> 
    mit erwarteten <strong>Kosteneinsparungen von {kpis['roi_annual_saving']:,} EUR jährlich</strong>. 
    Bei einer Investition von {kpis['roi_investment']:,} EUR erreichen Sie den 
    <strong>Break-Even nach {kpis['kpi_roi_months']} Monaten</strong>.</p>
    
    <p>Ihre Stärken: {', '.join(strengths) if strengths else 'solide Ausgangsbasis'}. 
    Herausforderungen: {', '.join(challenges) if challenges else 'überschaubar'}. 
    3-Jahres-Wertpotenzial: <strong>{kpis['roi_three_year']:,} EUR</strong>.</p>
    """
    
    return clean_text(summary)

def generate_quick_wins(answers: Dict[str, Any], kpis: Dict[str, Any]) -> str:
    """Quick Wins Generation"""
    html = "<h3>1. Automatisierte Dokumentenerstellung</h3>"
    html += "<p>Nutzen Sie DeepL Write für Angebote und E-Mails. "
    html += "<strong>Zeitersparnis: 5-8 Stunden/Woche</strong>, Einrichtung: 1 Tag.</p>"
    
    html += "<h3>2. Meeting-Automatisierung</h3>"
    html += "<p>tl;dv für automatische Protokolle. "
    html += "<strong>Kosteneinsparung: 2.000€/Monat</strong> durch wegfallende manuelle Arbeit.</p>"
    
    html += "<h3>3. Chatbot für FAQs</h3>"
    html += "<p>Typebot (Open Source) für Standardanfragen. "
    html += "<strong>30% weniger Support-Tickets</strong> in 4 Wochen.</p>"
    
    return html

def generate_risk_analysis(answers: Dict[str, Any]) -> str:
    """Risikoanalyse"""
    html = "<h3>Identifizierte Risiken</h3>"
    
    if answers.get('datenschutzbeauftragter') != 'ja':
        html += "<p><strong>🔴 Datenschutz-Risiko:</strong> Kein DSB benannt. "
        html += "<em>Maßnahme:</em> Externen DSB beauftragen (200-500€/Monat).</p>"
    
    html += "<p><strong>🟡 Compliance-Risiko:</strong> DSFA unvollständig. "
    html += "<em>Maßnahme:</em> Template nutzen, 2-3 Tage Aufwand.</p>"
    
    html += "<p><strong>🟢 Technologie-Risiko:</strong> Tools veralten schnell. "
    html += "<em>Maßnahme:</em> Quartalsweise Reviews.</p>"
    
    return html

def generate_roadmap(answers: Dict[str, Any], kpis: Dict[str, Any]) -> str:
    """Roadmap Generation"""
    html = "<h3>Phase 1: Quick Wins (0-30 Tage)</h3>"
    html += "<p>Start mit identifizierten Quick Wins. Budget: 20% der Investition.</p>"
    
    html += "<h3>Phase 2: Skalierung (31-90 Tage)</h3>"
    html += "<p>Integration in Regelbetrieb. Schulung der Mitarbeiter.</p>"
    
    html += "<h3>Phase 3: Optimierung (91-180 Tage)</h3>"
    html += f"<p>ROI nach {kpis['kpi_roi_months']} Monaten. "
    html += f"Jährliche Einsparung: {kpis['roi_annual_saving']:,} EUR.</p>"
    
    return html

def generate_other_sections(answers: Dict[str, Any], kpis: Dict[str, Any]) -> Dict[str, str]:
    """Generiert alle weiteren Sektionen"""
    
    sections = {}
    
    # Compliance
    sections['compliance'] = """
    <h3>Compliance-Status</h3>
    <p>DSGVO-Grundlagen vorhanden. EU AI Act Vorbereitung läuft.
    Nächste Schritte: DSFA vervollständigen, KI-Governance dokumentieren.</p>
    """
    
    # Vision
    sections['vision'] = f"""
    <h3>Ihre KI-Zukunft 2027</h3>
    <p>KI-Reifegrad: {min(95, kpis['readiness_score'] + 30)}%. 
    Effizienzsteigerung realisiert: {kpis['kpi_efficiency']}%.
    Neue Geschäftsmodelle etabliert.</p>
    """
    
    # Coaching
    sections['coaching'] = """
    <h3>Reflexionsfragen</h3>
    <ul>
    <li>Wo verlieren Sie täglich Zeit?</li>
    <li>Welche Anfragen wiederholen sich?</li>
    <li>Wer könnte KI-Champion werden?</li>
    </ul>
    """
    
    # Recommendations
    sections['recommendations'] = f"""
    <div class="info-box">
    <div class="info-box-title">Top-Empfehlung</div>
    <p>Starten Sie mit Prozessautomatisierung. 
    Potenzial: {kpis['kpi_efficiency']}% Effizienz, 
    {kpis['roi_annual_saving']:,} EUR/Jahr Einsparung.</p>
    </div>
    """
    
    # Gamechanger
    sections['gamechanger'] = f"""
    <p>KI-Plattform für Ihre Branche. 
    {kpis['kpi_efficiency']}% Effizienzsteigerung, 
    {kpis['roi_annual_saving']:,} EUR jährliche Einsparung.</p>
    """
    
    return sections

# ============================= Hauptfunktion =============================

def analyze_briefing(body: Dict[str, Any], lang: str = 'de') -> Dict[str, Any]:
    """
    Hauptfunktion - Verarbeitet Fragebogen und generiert Report
    """
    lang = 'de' if lang.lower().startswith('de') else 'en'
    answers = dict(body)
    
    # KPIs berechnen
    kpis = calculate_kpis_from_answers(answers)
    
    # Metadaten
    branche = safe_str(answers.get('branche', 'beratung'))
    bundesland = safe_str(answers.get('bundesland', 'Berlin'))
    hauptleistung = safe_str(answers.get('hauptleistung', 'Beratung'))
    
    # Content generieren
    exec_summary_html = generate_data_driven_executive_summary(answers, kpis)
    tools_html = match_tools_to_company(answers)
    funding_html = match_funding_programs(answers)
    quick_wins_html = generate_quick_wins(answers, kpis)
    risks_html = generate_risk_analysis(answers)
    roadmap_html = generate_roadmap(answers, kpis)
    
    # Weitere Sektionen
    other_sections = generate_other_sections(answers, kpis)
    
    # Context zusammenstellen
    context = {
        'meta': {
            'title': 'KI-Statusbericht',
            'subtitle': f"Readiness: {kpis['readiness_score']}%",
            'date': _dt.now().strftime('%d.%m.%Y')
        },
        'score_percent': kpis['readiness_score'],
        'branche': branche.capitalize(),
        'bundesland': bundesland,
        'company_size_label': {
            '1': '1 (Solo)',
            'solo': '1 (Solo)', 
            '2-10': '2-10 Mitarbeiter',
            '11-100': '11-100 Mitarbeiter'
        }.get(safe_str(answers.get('unternehmensgroesse', '2-10')), '2-10'),
        'hauptleistung': hauptleistung,
        
        # KPIs
        'kpi_efficiency': kpis['kpi_efficiency'],
        'kpi_cost_saving': kpis['kpi_cost_saving'],
        'kpi_roi_months': kpis['kpi_roi_months'],
        'kpi_compliance': kpis['kpi_compliance'],
        'kpi_innovation': kpis['kpi_innovation'],
        'roi_investment': kpis['roi_investment'],
        'roi_annual_saving': kpis['roi_annual_saving'],
        'roi_three_year': kpis['roi_three_year'],
        'digitalisierungsgrad': kpis['digitalisierungsgrad'],
        'automatisierungsgrad': answers.get('automatisierungsgrad', 'mittel'),
        'risikofreude': kpis['risikofreude'],
        
        # HTML Sektionen
        'exec_summary_html': exec_summary_html,
        'quick_wins_html': quick_wins_html,
        'risks_html': risks_html,
        'recommendations_html': other_sections['recommendations'],
        'roadmap_html': roadmap_html,
        'compliance_html': other_sections['compliance'],
        'vision_html': other_sections['vision'],
        'gamechanger_html': other_sections['gamechanger'],
        'coaching_html': other_sections['coaching'],
        'tools_html': tools_html,
        'funding_html': funding_html,
        
        # Footer
        'copyright_owner': 'KI-Sicherheit.jetzt',
        'copyright_year': _dt.now().year
    }
    
    # Clean all HTML
    for key, value in context.items():
        if isinstance(value, str) and '_html' in key:
            context[key] = clean_text(value)
    
    return context
# ============================= Erweiterte analyze_briefing Funktion =============================

def analyze_briefing_with_live_data(body: Dict[str, Any], lang: str = 'de') -> Dict[str, Any]:
    """
    Erweiterte Hauptfunktion mit Live-Daten Integration
    """
    # Basis-Analyse
    context = analyze_briefing(body, lang)
    
    # Prüfe ob Live-APIs verfügbar
    has_tavily = bool(os.getenv('TAVILY_API_KEY'))
    has_serpapi = bool(os.getenv('SERPAPI_KEY') or os.getenv('SERPAPI_API_KEY'))
    
    if has_tavily or has_serpapi:
        # Erweitere mit Live-Daten
        try:
            # Live Updates Sektion
            context['live_html'] = generate_live_updates_section(body)
            context['live_title'] = 'Aktuelle Entwicklungen (Live-Daten)'
            
            # Erweiterte Förderprogramme
            if has_tavily:
                context['funding_html'] = enhanced_match_funding_programs(body)
            
            # Live Tool Discovery
            if has_tavily and body.get('ki_usecases'):
                live_tools = fetch_live_tools(
                    body.get('ki_usecases', []),
                    body.get('budget', '2000-10000')
                )
                
                # Füge zu Tools hinzu wenn gefunden
                if live_tools:
                    tools_addon = "<h3>Neu entdeckte Tools (Live)</h3><ul>"
                    for tool in live_tools[:3]:
                        tools_addon += f"<li><strong>{tool['name']}</strong> - {tool['use_case']}"
                        if tool.get('features'):
                            tools_addon += f" ({', '.join(tool['features'][:2])})"
                        tools_addon += "</li>"
                    tools_addon += "</ul>"
                    
                    context['tools_html'] = context.get('tools_html', '') + tools_addon
            
            # Status-Indikator
            context['meta']['live_data'] = True
            context['meta']['sources'] = []
            if has_tavily:
                context['meta']['sources'].append('Tavily')
            if has_serpapi:
                context['meta']['sources'].append('Google/SerpAPI')
                
        except Exception as e:
            print(f"Live-Daten Fehler: {e}")
            # Fallback zu statischen Daten
            context['live_html'] = "<p>Live-Daten temporär nicht verfügbar.</p>"
    
    return context
# ============================= Test =============================

if __name__ == "__main__":
    # Test mit Beispieldaten
    test_data = {
        'branche': 'beratung',
        'unternehmensgroesse': '2-10',
        'bundesland': 'Berlin',
        'hauptleistung': 'KI-Beratung und Automatisierung',
        'digitalisierungsgrad': 10,
        'prozesse_papierlos': '81-100',
        'automatisierungsgrad': 'eher_hoch',
        'risikofreude': 5,
        'ki_usecases': ['texterstellung', 'prozessautomatisierung', 'kundensupport'],
        'ki_hemmnisse': ['budget', 'zeit'],
        'datenschutzbeauftragter': 'ja',
        'budget': '2.000-10.000 €'
    }
    
    result = analyze_briefing(test_data, 'de')
    
    print("\n=== REPORT GENERIERT ===")
    print(f"KI-Reifegrad: {result['score_percent']}%")
    print(f"ROI: {result['kpi_roi_months']} Monate")
    print(f"3-Jahres-Wert: {result['roi_three_year']:,} EUR")
    print("\nAlle Sektionen erfolgreich generiert!")