"""Stat-extraction helpers for the MCP server (built on ``PyFlow.reporting``).

Stat-variable semantics worth knowing:
  - input_count  : items that entered this element (since the warm-up reset, if any)
  - output_count : items that left this element
  - content_*    : current / time-weighted average / max number of items held
  - staytime_*   : time an item spends inside the element (entry→exit); null if no exit
  - state, state_ratios : current state and fraction of time in each state
  - blockage_count [servers], type_counts [sinks], items_created [sources]

For sources, items are *generated* (not received), so input_count=0 and output_count is
the number of items dispatched. For Sink, items enter but never exit, so output_count=0.

"""

from __future__ import annotations

from typing import Any

from PyFlow.reporting import element_summary, resource_summary


def stats_for_element(element_id: str, element: Any, spec: dict) -> dict:
    """Return a JSON-serialisable stats dict for a single element (see PyFlow.reporting)."""
    summary = element_summary(element)
    summary.pop("name", None)
    summary.pop("class", None)
    return {"id": element_id, "type": spec["type"], "name": spec.get("name", element_id), **summary}


def resource_stats(resources: dict[str, Any]) -> list[dict]:
    """Statistics of every resource pool (utilization, queue, waiting times, per unit)."""
    return [{"id": rid, **resource_summary(pool)} for rid, pool in resources.items()]


def list_stats(lists: dict[str, Any]) -> list[dict]:
    """Statistics of every model list (content, waiting pulls, stay and wait times)."""
    return [{"id": lid, **lst.summary()} for lid, lst in lists.items()]


def all_stats(elements: dict[str, Any], element_specs: dict[str, dict]) -> list[dict]:
    """Return stats for every element in insertion order."""
    return [
        stats_for_element(eid, elements[eid], element_specs[eid])
        for eid in elements
    ]
