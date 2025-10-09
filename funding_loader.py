# funding_loader.py
# -*- coding: utf-8 -*-
"""
Lädt kuratierte Förderprogramme (Whitelist) und filtert nach Region.
CSV-Formate:
  data/funding_whitelist.csv  (empfohlen, gepflegt)
  data/funding_local.csv      (optional, projekt-individuell)

Spalten (CSV):
region,title,sponsor,url,type,rate,cap_eur,updated,notes
region: 'DE' (landesoffen), 'BE' (Berlin), 'BY' (Bayern) etc.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Dict, List

DATA_DIR = os.path.abspath(os.getenv("DATA_DIR") or os.path.join(os.getcwd(), "data"))

def _read_csv(path: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row = {k.strip(): (v or "").strip() for k, v in row.items()}
                if row.get("title") and row.get("url"):
                    out.append(row)
    except FileNotFoundError:
        return []
    except Exception:
        return []
    return out

def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.strip())
    except Exception:
        return datetime.min

def _load_all() -> List[Dict[str, str]]:
    items = []
    for name in ("funding_whitelist.csv", "funding_local.csv"):
        items.extend(_read_csv(os.path.join(DATA_DIR, name)))
    return items

def filter_funding(region: str = "DE", limit: int = 10) -> List[Dict[str, str]]:
    region = (region or "DE").upper()
    items = _load_all()
    # Region-Filter: exakte Region oder 'DE' (landesoffen)
    filt = [it for it in items if (it.get("region", "DE").upper() in (region, "DE"))]
    # Sortierung: neuestes "updated" zuerst, dann Sponsor
    filt.sort(key=lambda it: (_parse_dt(it.get("updated", "")), it.get("sponsor", "")), reverse=True)
    # Normalize Felder, damit gpt_analyze sie direkt rendern kann
    out = []
    for it in filt[:limit]:
        out.append({
            "title": it.get("title"),
            "url": it.get("url"),
            "source": it.get("sponsor") or "Förderprogramm",
            "domain": (it.get("url") or "").split("/")[2] if "://" in (it.get("url") or "") else "",
            "date": it.get("updated") or "",
            "rate": it.get("rate") or "",
            "cap_eur": it.get("cap_eur") or "",
            "type": it.get("type") or "",
            "notes": it.get("notes") or "",
        })
    return out
