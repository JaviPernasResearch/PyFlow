"""Helpers that extract stats from live PyFlow elements into plain dicts.

Stat-variable semantics worth knowing:
  - input_count  : total items that entered this element
  - output_count : total items that left this element
  - content_*    : current/avg/max number of items simultaneously held
  - staytime_*   : time an item spends inside the element (entry→exit)
  - staytime_current : stay time of the last item that exited (or 0 if none)

For InterArrivalSource, items are *generated* (not received), so input_count=0
and output_count=items_created. Content values are clipped to 0 because the
source never holds items — the StatLevelVariable would otherwise go negative.

For Sink, items enter but never exit, so output_count=0 and content_current
grows indefinitely. staytime_* fields are all 0 (items enter and are absorbed
immediately with no recorded exit event).
"""

from __future__ import annotations

from typing import Any


def stats_for_element(element_id: str, element: Any, spec: dict) -> dict:
    """Return a JSON-serialisable stats dict for a single element."""
    sc = element.get_stats_collector()

    # StatLevelVariable for content accumulates +1 on entry and -1 on exit.
    # Sources never record entries, so the level goes negative — clip to 0.
    content_current = max(0.0, sc.get_var_content_value())
    content_average = max(0.0, sc.get_var_content_average())
    content_max     = max(0.0, sc.get_var_content_max())

    return {
        "id": element_id,
        "type": spec["type"],
        "name": spec["name"],
        "input_count": sc.get_var_input_value(),
        "output_count": sc.get_var_output_value(),
        "content_current": content_current,
        "content_average": content_average,
        "content_max": content_max,
        "staytime_current": sc.get_var_staytime_value(),
        "staytime_average": sc.get_var_staytime_average(),
        "staytime_max": sc.get_var_staytime_max(),
        "staytime_min": sc.get_var_staytime_min(),
    }


def all_stats(elements: dict[str, Any], element_specs: dict[str, dict]) -> list[dict]:
    """Return stats for every element in insertion order."""
    return [
        stats_for_element(eid, elements[eid], element_specs[eid])
        for eid in elements
    ]
