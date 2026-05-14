"""Tracking element subclasses and stat-extraction helpers for the MCP server.

The two element subclasses defined here (TrackingMultiServer, TypeTrackingSink)
are drop-in replacements used transparently by factories.py. They add the extra
per-element metrics that the standard PyFlow stats collector does not track:
  - TrackingMultiServer.blockage_count : times a finished item was blocked downstream.
  - TypeTrackingSink.type_counts       : completed item count broken down by item type.

Stat-variable semantics worth knowing:
  - input_count  : total items that entered this element
  - output_count : total items that left this element
  - content_*    : current/avg/max number of items simultaneously held
  - staytime_*   : time an item spends inside the element (entry→exit)
  - staytime_current : stay time of the last item that exited (or 0 if none)

For InterArrivalSource / ScheduleSource, items are *generated* (not received),
so input_count=0 and output_count=items_created. Content values are clipped to 0
because the source never holds items.

For Sink, items enter but never exit, so output_count=0 and content_current
grows indefinitely. staytime_* fields are all 0 (no exit event recorded).
"""

from __future__ import annotations

from typing import Any

from PyFlow.Elements.multiServer import MultiServer
from PyFlow.Elements.sink import Sink
from PyFlow.Items.item import Item


# ---------------------------------------------------------------------------
# Tracking element subclasses (used by factories.py)
# ---------------------------------------------------------------------------

class TrackingMultiServer(MultiServer):
    """MultiServer that also counts how many times a finished item was blocked downstream."""

    def start(self) -> None:
        super().start()
        self.blockage_count: int = 0

    def complete_server_process(self, the_process) -> None:
        the_item = the_process.get_item()
        self.work_in_progress.remove(the_process)
        if self.get_output().send(the_item):
            self.idle_processes.append(the_process)
            self.current_items -= 1
            self.get_input().notify_available()
        else:
            self.blockage_count += 1
            self.completed.append(the_process)


class TypeTrackingSink(Sink):
    """Sink that also maintains a per-type item count dictionary."""

    def start(self) -> None:
        super().start()
        self.type_counts: dict[str, int] = {}

    def receive(self, the_item: Item) -> bool:
        item_type = the_item.type if the_item.type else "Default"
        self.type_counts[item_type] = self.type_counts.get(item_type, 0) + 1
        return super().receive(the_item)


def stats_for_element(element_id: str, element: Any, spec: dict) -> dict:
    """Return a JSON-serialisable stats dict for a single element."""
    sc = element.get_stats_collector()

    # StatLevelVariable for content accumulates +1 on entry and -1 on exit.
    # Sources never record entries, so the level goes negative — clip to 0.
    content_current = max(0.0, sc.get_var_content_value())
    content_average = max(0.0, sc.get_var_content_average())
    content_max     = max(0.0, sc.get_var_content_max())

    result = {
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

    # Gap 5 — blockage_count on TrackingMultiServer (always present for MultiServer elements)
    if hasattr(element, "blockage_count"):
        result["blockage_count"] = element.blockage_count

    # Gap 4 — type_counts on TypeTrackingSink (always present for Sink elements)
    if hasattr(element, "type_counts"):
        result["type_counts"] = dict(element.type_counts)

    return result


def all_stats(elements: dict[str, Any], element_specs: dict[str, dict]) -> list[dict]:
    """Return stats for every element in insertion order."""
    return [
        stats_for_element(eid, elements[eid], element_specs[eid])
        for eid in elements
    ]
