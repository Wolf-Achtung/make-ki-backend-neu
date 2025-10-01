"""
eu_funding_api.py
--------------------

Dieses Modul stellt einfache Connector‑Funktionen für die wichtigsten EU‑Förder­programmschnittstellen
zur Verfügung. Die Funktionen kapseln HTTP‑Aufrufe an das OpenAIRE Graph API, die CORDIS Data Extraction
API sowie die EU Funding & Tenders Search API. Jede Funktion gibt eine Liste von Dictionaries zurück,
die grundlegende Felder wie Name, Betrag/Volumen, Deadline und URL enthalten.

Hinweis: Diese Implementierung ist als Vorlage gedacht. Aufgrund fehlender Netzwerk­konnektivität zur
Laufzeit innerhalb der Hosting‑Umgebung ist keine echte Anfrage möglich. In Umgebungen mit Internetzugang
können die Funktionen unverändert genutzt werden. Wenn ein API‑Key erforderlich ist, wird er aus der
Umgebungsvariable gelesen (z. B. ``CORDIS_API_KEY`` oder ``EU_PORTAL_API_KEY``). Fehlt der API‑Key,
werden leere Ergebnisse zurückgegeben.

Alle Funktionen fangen Exceptions ab und loggen diese über das ``logging``‑Modul.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import json
import requests

log = logging.getLogger("eu_funding_api")


def _http_get_json(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Optional[Dict[str, Any]]:
    """Hilfsfunktion für GET‑Requests, gibt JSON oder None zurück."""
    try:
        resp = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        log.warning("HTTP GET %s returned %s", url, resp.status_code)
    except Exception as e:
        log.warning("HTTP GET %s failed: %s", url, e)
    return None


def _http_post_json(url: str, json_data: Dict[str, Any], params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Optional[Dict[str, Any]]:
    """Hilfsfunktion für POST‑Requests mit JSON‑Body, gibt JSON oder None zurück."""
    try:
        resp = requests.post(url, params=params or {}, json=json_data, headers=headers or {}, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        log.warning("HTTP POST %s returned %s", url, resp.status_code)
    except Exception as e:
        log.warning("HTTP POST %s failed: %s", url, e)
    return None


def fetch_openaire_projects(keywords: str, country: str = "DE", size: int = 50) -> List[Dict[str, Any]]:
    """Ruft Projekte vom OpenAIRE Search API ab und extrahiert Basisinformationen.

    :param keywords: Suchbegriffe, z. B. "artificial intelligence" oder branchenspezifische Kombinationen.
    :param country: ISO‑Ländercode (z. B. DE für Deutschland).
    :param size: Anzahl der zurückgegebenen Projekte (Default: 50).
    :return: Liste von Programmdaten (dict mit name, amount, deadline, url).
    """
    url = "http://api.openaire.eu/search/projects"
    params = {
        "funder": "EC",
        "keywords": keywords,
        "country": country,
        "format": "json",
        "size": str(size),
    }
    data = _http_get_json(url, params=params)
    if not data or "projects" not in data:
        return []
    results = []
    for proj in data.get("projects", []):
        name = proj.get("title", "").strip()
        # In OpenAIRE gibt es keine unmittelbare "amount"‑Angabe, stattdessen Budget im Projektobjekt
        amount = proj.get("totalCost") or proj.get("ecMaxContribution") or ""
        deadline = proj.get("endDate") or ""
        url = proj.get("id") or ""
        results.append({
            "name": name,
            "amount": str(amount) if amount else "",
            "deadline": str(deadline) if deadline else "",
            "url": str(url) if url else "",
            "source": "OpenAIRE",
        })
    return results


def fetch_cordis_projects(programme: str = "HORIZON", topics: Optional[List[str]] = None, country: str = "DE", status: str = "SIGNED", max_results: int = 50) -> List[Dict[str, Any]]:
    """Ruft Projekte über die CORDIS Data Extraction API ab.

    Die API erfordert einen API‑Key, der in der Umgebungsvariablen ``CORDIS_API_KEY`` liegen sollte.
    """
    api_key = os.getenv("CORDIS_API_KEY")
    if not api_key:
        log.info("CORDIS_API_KEY not set; skipping CORDIS API call")
        return []
    url = "https://cordis.europa.eu/dataextractions/api"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {
        "programme": programme,
        "country": country,
    }
    if topics:
        body["topics"] = topics
    if status:
        body["status"] = status
    data = _http_post_json(url, body, headers=headers)
    results = []
    if not data or "projects" not in data:
        return results
    for proj in data.get("projects", [])[:max_results]:
        name = proj.get("title", "").strip()
        amount = proj.get("budget", "") or proj.get("totalCost", "")
        deadline = proj.get("endDate", "")
        url_proj = proj.get("url", "")
        results.append({
            "name": name,
            "amount": str(amount) if amount else "",
            "deadline": str(deadline) if deadline else "",
            "url": str(url_proj) if url_proj else "",
            "source": "CORDIS",
        })
    return results


def fetch_eu_portal_calls(text: str, programme_period: str = "2021 - 2027", max_results: int = 50) -> List[Dict[str, Any]]:
    """Ruft aktuelle Calls aus dem EU Funding & Tenders Portal (Search API) ab.

    :param text: Freitext‑Suche (z. B. "artificial intelligence" oder branchenspezifische Keywords)
    :param programme_period: Programmperiode (Default: "2021 - 2027").
    :param max_results: Maximale Anzahl der zurückgegebenen Einträge.
    :return: Liste von Programmdaten (Name, Amount, Deadline, Url).
    """
    api_key = os.getenv("EU_PORTAL_API_KEY", "SEDIA")
    url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    # Parameter für GET (API-Key und Pagination)
    params = {
        "apiKey": api_key,
        "pageSize": str(max_results),
        "pageNumber": "1",
        "text": text,
    }
    # Query für POST: offene Calls, Programmperiode Horizon Europe 2021-2027
    query = {
        "bool": {
            "must": [
                {"terms": {"type": ["1", "2"]}},
                # Status 31094502 = open calls (31094501 war closed)
                {"terms": {"status": ["31094502"]}},
                {"term": {"programmePeriod": programme_period}},
            ]
        }
    }
    headers = {}
    data = _http_post_json(url, query, params=params, headers=headers)
    if not data or "hits" not in data:
        return []
    calls = []
    # API liefert unter hits.hits eine Liste von Calls
    for hit in data.get("hits", {}).get("hits", []):
        source_data = hit.get("_source", {})
        name = source_data.get("title", "").strip()
        # amount ist meist nicht explizit angegeben; Budget kann im Field "budget" oder "grant" stehen
        amount = source_data.get("budget", "") or source_data.get("estimatedBudget", "")
        deadline = source_data.get("deadlineDate", "") or source_data.get("closingDate", "")
        url_call = source_data.get("url", "") or source_data.get("projectUrl", "")
        calls.append({
            "name": name,
            "amount": str(amount) if amount else "",
            "deadline": str(deadline) if deadline else "",
            "url": str(url_call) if url_call else "",
            "source": "EUPortal",
        })
    return calls
