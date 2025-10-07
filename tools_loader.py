# File: tools_loader.py
# -*- coding: utf-8 -*-
"""Loader für data/tools.csv – robust gegen Nicht-Strings, mit Ranking."""
from __future__ import annotations
import csv, os, logging
from typing import List, Dict, Optional

LOG = logging.getLogger("tools_loader")
LOG.setLevel(logging.INFO)

BASE_DIR = os.path.abspath(os.getenv("APP_BASE", os.getcwd()))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
TOOLS_CSV = os.path.join(DATA_DIR, "tools.csv")

REQUIRED_COLS = [
    "name","category","industry","target","use_case","gdpr_ai_act",
    "hosting_model","data_residency","pricing_eur","pricing_tier",
    "integration_effort_1to5","one_liner","homepage_url","vendor_region",
    "company_size_fit","last_checked"
]

VALID_GDPR = {"yes","partial","unknown"}
VALID_HOSTING = {"SaaS","Self-Hosted","Hybrid","Open-Source"}
VALID_RESIDENCY = {"EU","EEA","Global","Unknown"}
VALID_TIER = {"€","€€","€€€","€€€€"}
VALID_REGION = {"EU","US","Global","Other"}

def _read_csv(path: str) -> List[Dict[str,str]]:
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader((line for line in f if not line.strip().startswith("#")))
        rows = []
        for row in reader:
            r = {}
            for k, v in row.items():
                r[k] = ("" if v is None else str(v).strip())
            rows.append(r)
        return rows

def _validate_header(cols: List[str]) -> None:
    missing = [c for c in REQUIRED_COLS if c not in cols]
    if missing:
        raise ValueError(f"tools.csv fehlt Spalten: {missing}")

def _norm_choice(val: str, valid: set, default: str) -> str:
    s = str(val or "").strip()
    return s if s in valid else default

def _normalize_row(r: Dict[str,str]) -> Dict[str,str]:
    r["gdpr_ai_act"] = _norm_choice((r.get("gdpr_ai_act") or "").lower(), VALID_GDPR, "unknown")
    r["hosting_model"] = _norm_choice(r.get("hosting_model"), VALID_HOSTING, "SaaS")
    r["data_residency"] = _norm_choice(r.get("data_residency") or "Unknown", VALID_RESIDENCY, "Unknown")
    r["pricing_tier"] = _norm_choice(r.get("pricing_tier") or "€", VALID_TIER, "€")
    r["vendor_region"] = _norm_choice(r.get("vendor_region") or "Global", VALID_REGION, "Global")
    try:
        eff = int(float(r.get("integration_effort_1to5") or "3"))
        eff = max(1, min(5, eff))
    except Exception:
        eff = 3
    r["integration_effort_1to5"] = str(eff)
    # Strings erzwingen
    for k in ("industry","company_size_fit","name","homepage_url","one_liner","target","use_case"):
        r[k] = str(r.get(k) or "")
    return r

def load_all() -> List[Dict[str,str]]:
    if not os.path.exists(TOOLS_CSV):
        LOG.warning("tools.csv nicht gefunden: %s", TOOLS_CSV); return []
    rows = _read_csv(TOOLS_CSV)
    if not rows: return []
    _validate_header(list(rows[0].keys()))
    out = [_normalize_row(r) for r in rows]
    LOG.info("Tools geladen: %d", len(out))
    return out

def filter_tools(industry: str = "*", company_size: Optional[str] = None, limit: int = 10) -> List[Dict[str,str]]:
    all_tools = load_all()
    if not all_tools: return []
    ind = str(industry or "*").lower()
    cs = str(company_size or "").lower()

    def score(t: Dict[str,str]) -> int:
        s = 0
        tind = str(t.get("industry") or "").lower()
        s += 2 if tind == ind and ind != "*" else 0
        s += 1 if (t.get("industry") or "").strip() == "*" else 0
        if cs and cs in str(t.get("company_size_fit") or "").lower():
            s += 2
        s += 1 if t.get("gdpr_ai_act") == "yes" else 0
        s += 1 if t.get("hosting_model") in {"Self-Hosted","Open-Source"} else 0
        try: s += (6 - int(t.get("integration_effort_1to5") or "3"))
        except: pass
        return s

    ranked = sorted(all_tools, key=score, reverse=True)
    preferred = [t for t in ranked if str(t.get("industry") or "").lower() == ind and ind != "*"]
    generic = [t for t in ranked if (t.get("industry") or "").strip() == "*"]
    return (preferred + generic)[:limit]
