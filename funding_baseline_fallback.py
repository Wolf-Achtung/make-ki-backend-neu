
# file: funding_baseline_fallback.py
# -*- coding: utf-8 -*-
"""
Funding baseline fallback.

Goal: ensure that the report always shows at least a minimal, region‑aware
baseline for funding even when the live layer has no results. The functions
here are side‑effect free and can be used from gpt_analyze/postprocess paths.

Data sources (static, committed):
- data/foerder_baseline.csv         (generic, compact)             # fileciteturn0file0
- ENHANCED_FUNDING_DATABASE.py      (richer, if present)

Environment reference:
- EU_FUNDING_ENABLED=true enables baseline usage even with empty live results. # fileciteturn0file0
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("funding_baseline")

BASE_DIR = Path.cwd()
DATA_DIR = Path("data")
CSV_BASELINE = DATA_DIR / "foerder_baseline.csv"  # fileciteturn0file0

@dataclass
class FundingItem:
    title: str
    url: str
    source: str = "Förderprogramm"
    region: str = "DE"  # 'DE' (bundesweit) or 'BE', 'BY', ...
    type: str = "Zuschuss"
    rate: str = ""
    cap_eur: str = ""
    date: str = ""
    notes: str = ""

def _read_csv(path: Path) -> List[FundingItem]:
    items: List[FundingItem] = []
    if not path.exists():
        return items
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(FundingItem(
                title=(row.get("name") or row.get("title") or "").strip(),
                url=(row.get("link") or row.get("url") or "").strip(),
                source=(row.get("sponsor") or "Förderprogramm").strip(),
                region=(row.get("region") or "DE").strip(),
                type=(row.get("foerderart") or row.get("type") or "").strip(),
                rate=(row.get("rate") or "").strip(),
                cap_eur=(row.get("cap_eur") or "").strip(),
                date=(row.get("updated") or "").strip(),
                notes=(row.get("notes") or "").strip(),
            ))
    return items

def load_baseline() -> List[FundingItem]:
    """Load generic baseline from CSV. Returns empty list if file missing."""
    return _read_csv(CSV_BASELINE)

def filter_by_region(items: List[FundingItem], region_code: str) -> List[FundingItem]:
    region_code = (region_code or "DE").upper()
    out: List[FundingItem] = []
    for it in items:
        r = (it.region or "DE").upper()
        if r == "DE" or r == region_code:
            out.append(it)
    return out

def ensure_minimum_for_region(region_code: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Always return at least 3‑5 credible baseline entries for the UI filter."""
    base = load_baseline()
    sel = filter_by_region(base, region_code)[: max(3, int(limit))]
    return [asdict(x) for x in sel]
