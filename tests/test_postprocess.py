import pytest

from postprocess_report import postprocess_report_dict


def test_list_clamping_de():
    report = {
        "quick_wins": [
            {"title": "A", "effort": "1h"},
            {"title": "B"},
            {"title": "C"},
            {"title": "D"},  # extra
        ],
        "risks": [
            {"title": "R1"},
            {"title": "R2"},
            {"title": "R3"},
            {"title": "R4"},
        ],
        "recommendations": [
            {"title": "K1"}, {"title": "K2"}, {"title": "K3"}, {"title": "K4"}, {"title": "K5"}, {"title": "K6"}
        ],
    }
    processed = postprocess_report_dict(report, locale="de")
    # Quick wins: 3 + aggregated entry
    assert len(processed["quick_wins"]) == 4
    assert processed["quick_wins"][3]["title"] == "Weitere Quick Wins"
    # Risks: 3 + aggregated
    assert len(processed["risks"]) == 4
    assert processed["risks"][3]["title"] == "Weitere Risiken"
    # Recommendations: 5 + aggregated
    assert len(processed["recommendations"]) == 6
    assert processed["recommendations"][5]["title"] == "Weitere Empfehlungen"


def test_add_owner_dependencies_and_tradeoff():
    report = {
        "roadmap": [
            {"month": "1", "task": "Do stuff"},
            {"month": "2", "task": "More stuff", "owner": "Alice"},
        ],
        "gamechanger_blocks": [
            {"title": "Block1"},
            {"title": "Block2", "tradeoff": "None"},
        ],
    }
    processed = postprocess_report_dict(report, locale="en")
    # Owner and dependencies keys exist
    for entry in processed["roadmap"]:
        assert "owner" in entry
        assert "dependencies" in entry
    # First block now has a tradeoff key
    assert processed["gamechanger_blocks"][0].get("tradeoff") is None
    # Second block preserves provided tradeoff
    assert processed["gamechanger_blocks"][1]["tradeoff"] == "None"