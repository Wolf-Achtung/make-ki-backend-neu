# filename: backend/funding_loader.py
# -*- coding: utf-8 -*-
"""
Loader für Förderprogramme – dedupliziert, filtert nach Region.
"""

from __future__ import annotations

import csv
import logging
import os
from typing import Any, Dict, List

log = logging.getLogger("funding_loader")
if not log.handlers:
    import sys
    h = logging.StreamHandler(sys.stdout)
    log.addHandler(h)
log.setLevel(logging.INFO)

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))
FILES = ["foerdermittel.csv", "foerderprogramme.csv"]


def _load_csv(p: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not os.path.exists(p):
        return items
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            items.append({
                "title": r.get("title") or r.get("name") or "",
                "url": r.get("url") or r.get("link") or "",
                "region": (r.get("region") or r.get("state") or "BUND").upper(),
                "amount_hint": r.get("amount_hint") or "",
            })
    return items


def load_funding() -> List[Dict[str, Any]]:
    arr: List[Dict[str, Any]] = []
    for fn in FILES:
        arr.extend(_load_csv(os.path.join(DATA_DIR, fn)))
    seen = set()
    out: List[Dict[str, Any]] = []
    for it in arr:
        u = it.get("url")
        if u and u not in seen:
            seen.add(u)
            out.append(it)
    log.info("funding_loader: loaded %d items from csv", len(out))
    return out


def filter_funding(region: str = "DE", limit: int = 10) -> List[Dict[str, Any]]:
    items = load_funding()
    region = (region or "DE").upper()
    def ok(it: Dict[str, Any]) -> bool:
        r = (it.get("region") or "BUND").upper()
        return True if region in ("DE", "BUND") else (r == region or r.startswith(region))
    out = [it for it in items if ok(it)]
    return out[: max(1, int(limit))]
