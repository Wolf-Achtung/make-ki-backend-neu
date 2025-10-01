# File: eu_connectors.py
# -*- coding: utf-8 -*-
"""
Minimal EU connector functions for MAKE‑KI.

This module provides thin wrappers around a handful of European Union
endpoints.  Each function is designed to be resilient: network failures
and schema differences are silently handled, returning empty lists
instead of raising exceptions.  The results are normalised into a
uniform dictionary format with at least ``title`` and ``url`` keys so
that downstream report generation does not need to know the details of
each API.

Note that external HTTP requests may not be possible in all runtime
environments.  In such cases, the connector functions degrade
gracefully to empty lists.  When adding new connectors, follow the
existing patterns: wrap all requests in try/except, normalise the
output, and avoid leaking exceptions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _safe_get_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """Perform a GET request and return parsed JSON.

    All network errors are caught and logged.  If the response is
    successful (HTTP 200) the JSON body is returned; otherwise ``None``
    is returned.

    :param url: target URL
    :param params: query parameters to include
    :param timeout: request timeout in seconds
    :return: parsed JSON or ``None`` on error
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("EU API call failed: %s %s", url, exc)
        return None


def openaire_search_projects(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    """Search the OpenAIRE projects API and return a list of projects.

    :param query: free text search string (title filter)
    :param from_days: currently unused; reserved for future filtering
    :param max_results: maximum number of entries to return
    :return: list of normalised project dictionaries
    """
    url = "https://api.openaire.eu/search/projects"
    data = _safe_get_json(url, params={"format": "json", "title": query})
    items: List[Dict[str, str]] = []
    if not data:
        return items
    results = (
        data.get("response", {}).get("results", {}).get("result", [])
    )
    for r in results[: max_results]:
        md = r.get("metadata", {}).get("oaf:project", {})
        title = md.get("title", {}).get("$", "")
        code = md.get("code", "")
        proj_url = md.get("websiteurl", "")
        items.append(
            {
                "title": title or f"OpenAIRE Project {code}",
                "url": proj_url or "",
                "snippet": "",
                "date": "",
            }
        )
    return items


def cordis_search_projects(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    """Search CORDIS projects and return a list of matching entries.

    :param query: search query passed to the API
    :param from_days: currently unused; reserved for future filtering
    :param max_results: maximum number of results to return
    :return: list of normalised project dictionaries
    """
    url = "https://cordis.europa.eu/api/projects"
    data = _safe_get_json(url, params={"q": query, "format": "json"})
    items: List[Dict[str, str]] = []
    results = data.get("projects", []) if data else []
    for r in results[: max_results]:
        items.append(
            {
                "title": r.get("title", ""),
                "url": r.get("rcn_url", "") or r.get("url", ""),
                "snippet": r.get("objective", ""),
                "date": r.get("startDate", ""),
            }
        )
    return items


def funding_tenders_search(query: str, from_days: int = 60, max_results: int = 8) -> List[Dict[str, str]]:
    """Search EU Funding & Tenders opportunities by querying public domains.

    This implementation uses Tavily as a general search fallback to find
    funding calls on trusted EU domains.  It gracefully handles the case
    where Tavily is not available by returning an empty list.  Only a
    handful of top results are returned.

    :param query: free text search term
    :param from_days: how many days back to search (passed to Tavily)
    :param max_results: maximum number of results to return
    :return: list of normalised funding call dictionaries
    """
    domains = ["ec.europa.eu", "europa.eu"]
    # Resolve Tavily search function from either relative or absolute import.
    tav_search = None  # type: Optional[Any]
    try:
        # Try relative import if this module is part of a package
        from .websearch_utils import tavily_search as tav_search  # type: ignore
    except Exception:
        try:
            from websearch_utils import tavily_search as tav_search  # type: ignore
        except Exception:
            tav_search = None
    if tav_search is None:
        logger.info("Tavily search unavailable; skipping EU funding search")
        return []
    hits: List[Dict[str, Any]] = tav_search(
        f'{query} site:ec.europa.eu OR site:europa.eu "call" OR "tenders"',
        days=from_days,
        include_domains=domains,
        max_results=max_results,
    )
    items: List[Dict[str, str]] = []
    for h in hits[: max_results]:
        items.append(
            {
                "title": h.get("title", ""),
                "url": h.get("url", ""),
                "snippet": h.get("snippet", ""),
                "date": h.get("published", ""),
            }
        )
    return items
