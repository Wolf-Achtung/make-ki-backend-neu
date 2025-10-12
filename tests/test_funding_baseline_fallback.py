
import os, sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from funding_baseline_fallback import ensure_minimum_for_region

def test_fallback_returns_minimum_items():
    items = ensure_minimum_for_region("BE", limit=3)
    assert isinstance(items, list)
    assert len(items) >= 3
    # ensure shape
    assert {"title","url","source","region","type"} <= set(items[0].keys())
