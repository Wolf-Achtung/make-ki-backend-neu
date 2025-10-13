# filename: services/tool_matrix_enrich.py
# -*- coding: utf-8 -*-
"""
Tool matrix enrichment for KI‑Status‑Report.

- Loads baseline from data/tool_matrix.csv and data/tools_baseline.csv
- Normalizes fields and fills required columns (self_hosting, eu_residency, audit_logs)
- Provides a hook `enrich_with_live()` that can use Tavily/Hybrid to add fields like
  `saml_scim`, `dpa_url`, `audit_export` if available.
- Defensive by default: if no live layer or key is present, returns input unchanged.

This module is self‑contained and can be used by the analyzer or post‑processor.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

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
    rows.sort(key=lambda r: (r.category.lower(), r.name.lower()))
    return rows

def enrich_with_live(rows: List[ToolRow]) -> List[ToolRow]:
    """
    Best‑effort enrichment using hybrid search (Tavily preferred) if keys are present.
    Reads SEARCH_INCLUDE_DOMAINS and LIVE_TIMEOUT_S from ENV for better signal.
    """
    try:
        from websearch_utils_ext import hybrid_lookup  # type: ignore
    except Exception as exc:
        logger.info("no hybrid enrichment hook: %s", exc)
        return rows

    out: List[ToolRow] = []
    for r in rows:
        try:
            ext = hybrid_lookup(r.name) or {}
        except Exception as exc:
            logger.warning("hybrid_lookup failed for %s: %s", r.name, exc)
            ext = {}
        if ext:
            r.saml_scim = ext.get("saml_scim", r.saml_scim)
            r.dpa_url = ext.get("dpa_url", r.dpa_url)
            r.audit_export = ext.get("audit_export", r.audit_export)
        out.append(r)
    return out

def export_enriched_csv(out_path: Path) -> int:
    """Utility: writes a CSV `tool_matrix_enriched.csv` for QA/inspection."""
    rows = load_tool_matrix()
    rows = enrich_with_live(rows)
    cols = ["name","category","self_hosting","eu_residency","audit_logs","link","saml_scim","dpa_url","audit_export"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            d = asdict(r)
            w.writerow([d.get(c, "") for c in cols])
    return len(rows)
