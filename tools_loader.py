# filename: backend/tools_loader.py
# -*- coding: utf-8 -*-
"""
Loader/Filter für data/tools.csv(.json) – robust gegen List/str-Mischformen.
- 'industry' akzeptiert jetzt 'all', 'any', 'general', leer → Match-All
- weiche Größenprüfung (kein harter Ausschluss)
"""

from __future__ import annotations

import csv
import json
import logging
import os
from typing import Any, Dict, List

log = logging.getLogger("tools_loader")
if not log.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    log.addHandler(h)
log.setLevel(logging.INFO)

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))
TOOLS_CSV = os.path.join(DATA_DIR, "tools.csv")
TOOLS_JSON = os.path.join(DATA_DIR, "tools.json")


def _s(x: Any) -> str:
    if isinstance(x, list):
        return ", ".join(map(str, x))
    return "" if x is None else str(x)


def _load_csv(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append({k: _s(v) for k, v in row.items()})
    return items


def _load_json(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    try:
        data = json.load(open(path, "r", encoding="utf-8"))
        if isinstance(data, list):
            return [{k: _s(v) for k, v in it.items()} for it in data]
        return []
    except Exception as exc:
        log.warning("tools.json konnte nicht geladen werden: %s", exc)
        return []


def load_tools() -> List[Dict[str, Any]]:
    items = []
    items.extend(_load_csv(TOOLS_CSV))
    if not items:
        items.extend(_load_json(TOOLS_JSON))
    log.info("Tools geladen: %d", len(items))
    return items


def _industry_matches(industry_query: str, tool_industry: str) -> bool:
    iq = (industry_query or "*").strip().lower()
    ti = (tool_industry or "").strip().lower()
    if iq in ("*", "", "all", "any", "general"):
        return True
    if not ti or ti in ("all", "any", "general"):
        return True
    return iq in ti


def filter_tools(industry: str = "*", company_size: str = "", limit: int = 8) -> List[Dict[str, Any]]:
    all_items = load_tools()
    out: List[Dict[str, Any]] = []
    for it in all_items:
        if not _industry_matches(industry, _s(it.get("industry"))):
            continue
        # Größen-Fit nur als Soft-Signal (kein Ausschluss)
        out.append(it)

    def _rank(t: Dict[str, Any]) -> tuple:
        gdpr = (_s(t.get("gdpr_ai_act")) or "unknown").lower()
        gdpr_rank = {"yes": 0, "partial": 1, "unknown": 2}.get(gdpr, 2)
        region = (_s(t.get("vendor_region")) or "").lower()
        region_rank = 0 if ("eu" in region or "de" in region) else 1
        try:
            effort = int(_s(t.get("integration_effort_1to5")) or "3")
        except Exception:
            effort = 3
        return (gdpr_rank, region_rank, effort)

    out.sort(key=_rank)
    return out[: max(1, int(limit))]
