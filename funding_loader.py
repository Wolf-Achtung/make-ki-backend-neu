# File: funding_loader.py
# -*- coding: utf-8 -*-
"""
Einfacher Loader für lokale Förderlisten:
- data/foerdermittel.csv (oder) data/foerderprogramme.csv
Erwartete Spalten (flexibel): title/name, url, region/bundesland, amount/budget, deadline (optional)
"""
from __future__ import annotations
import csv, os, logging
from typing import List, Dict

LOG = logging.getLogger("funding_loader")
LOG.setLevel(logging.INFO)

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
CANDIDATES = [os.path.join(DATA_DIR, "foerdermittel.csv"),
              os.path.join(DATA_DIR, "foerderprogramme.csv")]

def _read_csv_any() -> List[Dict[str,str]]:
    for path in CANDIDATES:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader((line for line in f if not line.strip().startswith("#")))
                rows = []
                for row in reader:
                    rows.append({k:(v or "").strip() for k,v in row.items()})
                LOG.info("funding_loader: loaded %d items from %s", len(rows), os.path.basename(path))
                return rows
    LOG.warning("funding_loader: no local funding CSV found.")
    return []

def filter_funding(region: str = "DE", limit: int = 10) -> List[Dict[str,str]]:
    rows = _read_csv_any()
    if not rows: return []
    r = region.upper()
    items = []
    for row in rows:
        title = row.get("title") or row.get("name") or ""
        url = row.get("url") or row.get("link") or ""
        reg = (row.get("region") or row.get("bundesland") or "DE").upper()
        amount = row.get("amount") or row.get("budget") or row.get("foerderquote") or ""
        # Bevorzuge Regionstreffer, sonst DE-weit
        score = 2 if reg == r else (1 if reg in ("DE","EU","EEA","BUND") else 0)
        items.append({"title": title, "url": url, "region": reg, "amount_hint": amount, "_score": score})
    items = sorted(items, key=lambda x: x["_score"], reverse=True)
    return [{k:v for k,v in it.items() if not k.startswith("_")} for it in items[:limit]]
