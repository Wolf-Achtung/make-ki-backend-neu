"""
postprocess_report.py
---------------------

This module exposes a helper function to post‑process AI‑generated report
dictionaries for the KI‑Status‑Report.  It enforces list limits, fills
missing fields for quick wins, adds owner and dependency columns to
roadmap entries and inserts trade‑off information into gamechanger
blocks.  The logic is intended to be locale aware (DE/EN) and can be
adjusted by passing the `locale` parameter.

Typical usage in a report pipeline::

    from postprocess_report import postprocess_report_dict
    report = postprocess_report_dict(report, locale="de")

You can then render the resulting dictionary to HTML/PDF.  Excess list
items are summarised into a single entry and missing keys are added
with ``None`` as a placeholder.  If new fields appear in future
versions of the generator, this function will leave them untouched.

The script makes no assumptions about the keys used for quick wins,
risks, recommendations or roadmap entries.  It simply looks for
commonly used keys ("quick_wins", "risks", "recommendations",
"roadmap") and applies heuristics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Iterable, MutableMapping, Optional


def _summarise_extras(items: Iterable[Any]) -> str:
    """Create a summary string from a sequence of extra list items.

    The function tries to extract a human‑readable name from each item
    (dict or string).  If no obvious name is found, the string
    representation of the item is used.  Items are separated by
    semicolons.
    """
    names: List[str] = []
    for item in items:
        if isinstance(item, MutableMapping):
            # Try common keys in priority order
            for key in (
                "title",
                "name",
                "risk",
                "recommendation",
                "text",
                "description",
            ):
                value = item.get(key)
                if value:
                    names.append(str(value))
                    break
            else:
                # Fallback to first value in dict
                first_val = next(iter(item.values()), None)
                if first_val is not None:
                    names.append(str(first_val))
        else:
            names.append(str(item))
    return "; ".join(names)


def _clamp_list(
    lst: List[Any],
    max_items: int,
    locale: str,
    type_name: str,
    preserve_keys: Optional[List[str]] = None,
) -> List[Any]:
    """Clamp a list to a maximum number of items.

    If the list length exceeds ``max_items``, the trailing items are
    summarised into a single dictionary entry.  The name of the
    aggregated item depends on the ``type_name`` (e.g. "quick_wins",
    "risks", "recommendations") and the locale.  For quick wins, the
    aggregated entry contains the fields ``title``, ``effort``, ``tool``,
    ``impact`` and ``start_today``; for other types, it contains
    ``title`` and ``description``.  You can pass ``preserve_keys`` to
    define which keys should be carried over verbatim from the extra
    items (unused by default).
    """
    if len(lst) <= max_items:
        return lst
    # Determine the appropriate title based on locale and type name
    agg_title_map = {
        "quick_wins": {"de": "Weitere Quick Wins", "en": "Additional Quick Wins"},
        "risks": {"de": "Weitere Risiken", "en": "Additional Risks"},
        "recommendations": {"de": "Weitere Empfehlungen", "en": "Additional Recommendations"},
    }
    locale_code = "de" if locale.lower().startswith("de") else "en"
    title = agg_title_map.get(type_name, {}).get(locale_code, "Additional")
    extras = lst[max_items:]
    summary = _summarise_extras(extras)
    if type_name == "quick_wins":
        # Build aggregated quick win entry
        aggregated = {
            "title": title,
            "effort": None,
            "tool": None,
            "impact": summary,
            "start_today": None,
        }
    else:
        aggregated = {
            "title": title,
            "description": summary,
        }
    return lst[:max_items] + [aggregated]


def postprocess_report_dict(report: Dict[str, Any], locale: str = "de") -> Dict[str, Any]:
    """Post‑process a report dictionary.

    This function modifies the input dict in place and returns it for
    convenience.  It clamps the number of quick wins, risks and
    recommendations, fills in missing quick win fields, adds owner
    and dependency placeholders to roadmap entries and ensures that
    gamechanger blocks contain a trade‑off.

    Parameters
    ----------
    report : dict
        The report dictionary produced by the AI pipeline.
    locale : str, optional
        Two‑letter language code (``de`` or ``en``) used to localise
        aggregated item titles.

    Returns
    -------
    dict
        The modified report dictionary.
    """
    # Clamp lists
    for key, max_count in (
        ("quick_wins", 3),
        ("risks", 3),
        ("recommendations", 5),
    ):
        if isinstance(report.get(key), list):
            # fill missing quick win fields before clamping
            if key == "quick_wins":
                for item in report[key]:
                    if isinstance(item, MutableMapping):
                        item.setdefault("title", None)
                        item.setdefault("effort", None)
                        item.setdefault("tool", None)
                        item.setdefault("impact", None)
                        item.setdefault("start_today", None)
            report[key] = _clamp_list(report[key], max_count, locale, key)
    # Roadmap entries
    for roadmap_key in ["roadmap", "roadmap_items", "12_months_roadmap", "twelve_months_roadmap"]:
        items = report.get(roadmap_key)
        if isinstance(items, list):
            for entry in items:
                if isinstance(entry, MutableMapping):
                    entry.setdefault("owner", None)
                    entry.setdefault("dependencies", None)
    # Gamechanger trade‑off
    for gc_key in ["gamechanger", "gamechanger_blocks", "innovation_and_gamechanger"]:
        blocks = report.get(gc_key)
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, MutableMapping):
                    block.setdefault("tradeoff", None)
    return report