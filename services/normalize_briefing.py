# -*- coding: utf-8 -*-

from __future__ import annotations
from typing import Dict, Any

__all__ = ["CANON", "normalize_briefing"]

CANON = {
    # German -> Canonical
    "zeitbudget": "time_capacity",
    "vorhandene_tools": "existing_tools",
    "regulierte_branche": "regulated_industry",
    "trainings_interessen": "training_interests",
    "vision_prioritaet": "vision_priority",
    "strategische_ziele": "strategic_goals",
    "datenqualitaet": "data_quality",
    "innovationskultur": "innovation_culture",
    # English -> Canonical (pass-through)
    "time_capacity": "time_capacity",
    "existing_tools": "existing_tools",
    "regulated_industry": "regulated_industry",
    "training_interests": "training_interests",
    "vision_priority": "vision_priority",
    "strategic_goals": "strategic_goals",
    "data_quality": "data_quality",
    "innovation_culture": "innovation_culture",
    # Common keys
    "ai_roadmap": "ai_roadmap",
    "governance": "governance",
    "branche": "branche",
    "unternehmensgroesse": "unternehmensgroesse",
    "bundesland": "bundesland",
}

def normalize_briefing(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map incoming DE/EN form keys onto a stable internal canon."""
    norm: Dict[str, Any] = {}
    for k, v in (data or {}).items():
        norm[CANON.get(k, k)] = v
    return norm
