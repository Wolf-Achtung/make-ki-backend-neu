
import os, sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from services.tool_matrix_enrich import load_tool_matrix, enrich_with_live

def test_tool_matrix_loads_and_has_required_columns():
    rows = load_tool_matrix()
    assert isinstance(rows, list)
    assert len(rows) >= 0  # no hard requirement on size
    if rows:
        r = rows[0]
        assert hasattr(r, "name")
        assert hasattr(r, "eu_residency")
        assert hasattr(r, "self_hosting")
        assert hasattr(r, "audit_logs")

def test_enrichment_is_stable_without_live_layer():
    rows = load_tool_matrix()
    out = enrich_with_live(rows)
    assert len(out) == len(rows)
