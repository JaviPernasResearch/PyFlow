"""JSON-ready statistics: elements, resource pools (and their units), task executers, lists
and downtime generators. :func:`model_summary` exports a whole model (built by code or from a
specification); ``BuiltModel.results`` and the MCP server use the same functions.

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
    ``unit_utilization`` per unit; ``units``: state, state ratios and completed task sequences
    of every unit (they are task executers)."""
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
        "idle_units_average": _num(pool.list.content.average(now)),
        "units": {u.name: u.summary() for u in pool.units},
    }


def downtime_summary(generator: Any) -> Dict[str, Any]:
    """Stops of one downtime generator since the last reset; for failures that need resources,
    also ``repairs`` and the time waiting for them (``repair_wait_*``) and the pools used."""
    result: Dict[str, Any] = {
        "name": generator.name,
        "kind": type(generator).__name__,
        "target": generator.target.name,
        "state": generator.state,
        "stop_count": generator.stop_count,
        "total_downtime": _num(generator.total_downtime),
    }
    requirements = getattr(generator, "repair_requirements", None)
    if requirements:
        repairs = generator.repairs
        result.update({
            "repair_resources": sorted({r.pool.name for r in requirements}),
            "repairs": repairs,
            "repair_wait_total": _num(generator.repair_wait_total),
            "repair_wait_average": _num(generator.repair_wait_total / repairs) if repairs else None,
            "repair_wait_max": _num(generator.repair_wait_max) if repairs else None,
        })
    return result


def model_summary(model: Any) -> Dict[str, Any]:
    """Everything a model has measured since the last statistics reset, keyed by name:
    ``elements`` (flow elements), ``resources`` (pools with their units), ``executers`` (task
    executers outside pools), ``lists`` (model lists, without the pools' own lists) and
    ``downtimes``."""
    from .executers import TaskExecuter
    pools = list(model.resources)
    pool_lists = {pool.list for pool in pools}
    return {
        "time": model.now,
        "seed": model.seed,
        "stats_since": model.stats_reset_time,
        "elements": {e.name: element_summary(e) for e in model.elements if not isinstance(e, TaskExecuter)},
        "resources": {pool.name: resource_summary(pool) for pool in pools},
        "executers": {e.name: e.summary() for e in model.elements
                      if isinstance(e, TaskExecuter) and e.pool is None},
        "lists": {name: lst.summary() for name, lst in model.lists.items() if lst not in pool_lists},
        "downtimes": [downtime_summary(g) for g in model.generators],
    }


__all__ = ["element_summary", "summarize", "resource_summary", "downtime_summary", "model_summary"]
