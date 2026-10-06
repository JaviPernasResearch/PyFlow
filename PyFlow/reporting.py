"""JSON-ready summaries of element statistics (used by ``BuiltModel.results`` and the MCP server).

Fields per element:

* ``input_count`` / ``output_count``: items that entered / left since the last stats reset
* ``content_current`` / ``content_average`` (time-weighted WIP) / ``content_max``
* ``staytime_average`` / ``staytime_min`` / ``staytime_max`` / ``staytime_current`` (last exit)
* ``state``: current state; ``state_ratios``: fraction of time in each state since the reset
* extras when the element has them: ``blockage_count`` (servers), ``type_counts`` (sinks),
  ``items_created`` (sources)

Undefined values are reported as ``None``: ``staytime_*`` while no item has left the element
(always for sinks) and infinite values.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional


def _num(value: Any) -> Optional[float]:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def element_summary(element: Any) -> Dict[str, Any]:
    sc = element.get_stats_collector()
    exits = sc.var_staytime.get_stats_count()
    stay = (lambda value: _num(value) if exits else None)
    result: Dict[str, Any] = {
        "name": element.name,
        "class": type(element).__name__,
        "input_count": _num(sc.get_var_input_value()),
        "output_count": _num(sc.get_var_output_value()),
        "content_current": max(0.0, _num(sc.get_var_content_value()) or 0.0),
        "content_average": max(0.0, _num(sc.get_var_content_average()) or 0.0),
        "content_max": max(0.0, _num(sc.get_var_content_max()) or 0.0),
        "staytime_current": stay(sc.get_var_staytime_value()),
        "staytime_average": stay(sc.get_var_staytime_average()),
        "staytime_max": stay(sc.get_var_staytime_max()),
        "staytime_min": stay(sc.get_var_staytime_min()),
        "state": element.state,
        "state_ratios": {state: round(ratio, 12) for state, ratio in element.state_ratios().items()},
    }
    if hasattr(element, "blockage_count"):
        result["blockage_count"] = element.blockage_count
    if hasattr(element, "type_counts"):
        result["type_counts"] = dict(element.type_counts)
    from .Elements.source import Source
    if isinstance(element, Source):
        result["items_created"] = element.number_items
    return result


def summarize(elements: Dict[str, Any] | Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """``{key: element_summary}`` for a dict ``{key: element}`` or an iterable (keyed by name)."""
    if isinstance(elements, dict):
        return {key: element_summary(e) for key, e in elements.items()}
    return {e.name: element_summary(e) for e in elements}


def resource_summary(pool: Any) -> Dict[str, Any]:
    """Statistics of a :class:`~PyFlow.resources.ResourcePool` since the last reset.

    ``utilization`` = time-weighted busy units / capacity; ``queue_*`` = requests waiting
    (time-weighted average, max, now); ``wait_*`` = time from request to grant of the requests
    that include this pool (a joint request, e.g. operator + robot, counts its whole wait for
    both pools, since they are granted together);
    ``unit_utilization`` per unit."""
    now = pool.model.now
    return {
        "name": pool.name,
        "kind": pool.kind,
        "capacity": pool.capacity,
        "utilization": _num(pool.utilization(now)),
        "busy_average": _num(pool.busy.average(now)),
        "busy_max": _num(pool.busy.max_value),
        "busy_current": _num(pool.busy.value),
        "queue_average": _num(pool.queue.average(now)),
        "queue_max": _num(pool.queue.max_value),
        "queue_current": _num(pool.queue.value),
        "requests": pool.requests,
        "grants": pool.grants,
        "wait_average": _num(pool.wait_total / pool.wait_count) if pool.wait_count else None,
        "wait_max": _num(pool.wait_max) if pool.wait_count else None,
        "unit_utilization": {name: _num(u) for name, u in pool.unit_utilization(now).items()},
    }


__all__ = ["element_summary", "summarize", "resource_summary"]
