
# file: services/tool_matrix_enrich.py
# -*- coding: utf-8 -*-
"""
Tool matrix enrichment for KI‑Status‑Report.

- Loads baseline from data/tool_matrix.csv and data/tools_baseline.csv
- Normalizes fields and fills required columns (self_hosting, eu_residency, audit_logs)
- Provides a hook `enrich_with_live()` that can use the hybrid live layer (optional)
  to add fields like `saml_scim`, `dpa_url`, `audit_export` if available.
  The hook is defensive and will never break the report if the live layer fails.

This module is self‑contained and can be used by the analyzer or post‑processor.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger("tool_matrix_enrich")

DATA_DIR = Path("data")
CSV_MATRIX = DATA_DIR / "tool_matrix.csv"
CSV_BASELINE = DATA_DIR / "tools_baseline.csv"

REQUIRED_COLS = ["name", "category", "self_hosting", "eu_residency", "audit_logs", "link"]

@dataclass
class ToolRow:
    name: str
    category: str
    self_hosting: str
    eu_residency: str
    audit_logs: str
    link: str
    saml_scim: str = "unknown"
    dpa_url: str = ""
    audit_export: str = "unknown"

def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    out: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
    return out

def _coalesce(primary: Iterable[Dict[str, str]], fallback: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    """Merge by name; primary rows win, fallback fills gaps."""
    seen = { (row.get("name") or "").lower(): row for row in primary }
    for row in fallback:
        key = (row.get("name") or "").lower()
        if key and key not in seen:
            seen[key] = row
    return list(seen.values())

def _ensure_required(row: Dict[str, str]) -> ToolRow:
    def g(k: str, default: str = "") -> str:
        v = (row.get(k) or default).strip()
        return v or default
    return ToolRow(
        name=g("name"),
        category=g("category", "LLM/tool"),
        self_hosting=g("self_hosting", "unknown"),
        eu_residency=g("eu_residency", "unknown"),
        audit_logs=g("audit_logs", "unknown"),
        link=g("link", ""),
        saml_scim=g("saml_scim", "unknown"),
        dpa_url=g("dpa_url", ""),
        audit_export=g("audit_export", "unknown"),
    )

def load_tool_matrix() -> List[ToolRow]:
    primary = _read_csv(CSV_MATRIX)
    fallback = _read_csv(CSV_BASELINE)
    merged = _coalesce(primary, fallback)
    rows = [_ensure_required(r) for r in merged if (r.get("name") or "").strip()]
    # Deterministic order
    rows.sort(key=lambda r: (r.category.lower(), r.name.lower()))
    return rows

def enrich_with_live(rows: List[ToolRow]) -> List[ToolRow]:
    """Best‑effort enrichment using the hybrid live layer if available.
    This implementation is intentionally conservative: it returns input rows unchanged
    if no live layer function is present. To plug in the live layer, provide a function
    `hybrid_lookup(name: str) -> Dict[str, str]` in a module `websearch_utils_ext`.
    That function may supply keys: saml_scim, dpa_url, audit_export.
    """
    try:
        from websearch_utils_ext import hybrid_lookup  # type: ignore
    except Exception:
        return rows  # nothing to do
    out: List[ToolRow] = []
    for r in rows:
        try:
            ext = hybrid_lookup(r.name) or {}
        except Exception:
            ext = {}
        if ext:
            r.saml_scim = ext.get("saml_scim", r.saml_scim)
            r.dpa_url = ext.get("dpa_url", r.dpa_url)
            r.audit_export = ext.get("audit_export", r.audit_export)
        out.append(r)
    return out
