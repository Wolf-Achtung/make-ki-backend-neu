# filename: backend/funding_loader.py
# -*- coding: utf-8 -*-
"""
Loader für Förderprogramme aus data/foerdermittel.csv / foerderprogramme.csv.
Gibt einfache Objekte (title, url, region, amount_hint) zurück + Filter nach Region.
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
FM_FILES = ["foerdermittel.csv", "foerderprogramme.csv"]


def _load_csv(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return items
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            it = {
                "title": r.get("title") or r.get("name") or "",
                "url": r.get("url") or r.get("link") or "",
                "region": (r.get("region") or r.get("state") or "BUND").upper(),
                "amount_hint": r.get("amount_hint") or "",
            }
            items.append(it)
    return items


def load_funding() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fn in FM_FILES:
        out.extend(_load_csv(os.path.join(DATA_DIR, fn)))
    # Dedupe by URL
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for it in out:
        u = it.get("url")
        if u and u not in seen:
            seen.add(u)
            deduped.append(it)
    log.info("funding_loader: loaded %d items from csv", len(deduped))
    return deduped


def filter_funding(region: str = "DE", limit: int = 10) -> List[Dict[str, Any]]:
    items = load_funding()
    region = (region or "DE").upper()
    def _ok(it: Dict[str, Any]) -> bool:
        r = (it.get("region") or "BUND").upper()
        if region in ("DE", "BUND"):
            return True
        return r == region or r.startswith(region)
    out = [it for it in items if _ok(it)]
    return out[: max(1, int(limit))]
