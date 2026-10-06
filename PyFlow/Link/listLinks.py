"""Flow through model lists (FlexSim "push to list" / "pull from list").

Sending to a list does **not** move the item: the origin keeps it (as when its output is
full, so it manages its capacity and blocking as usual) and the list gets an entry pointing to
it (``origin``). A queue announces every item it holds, so a list acts as a global priority
queue over several queues without the items leaving them.

An element whose input pulls from a list asks, whenever it has space, for the best entry of
its query (combined with its own input strategy and capacity). When an entry matches, the
:class:`ListInputLink` moves that item from its origin to the puller: statistics are recorded
here, at the link, like :class:`~PyFlow.Link.generalLink.GeneralLink` does.

    queue.connect_to_list(jobs)                         # or queue.connect([jobs])
    machine.pull_from_list(jobs, "WHERE type == 'A' ORDER BY priority DESC, age DESC")

Elements that can send to a list implement ``holds_item(item)`` and ``release_item(item)``
(the bookkeeping of a successful send, for a specific item).
"""
from __future__ import annotations

from typing import Any, List, Union

from ..query import Query
from .link import Link


class ListOutputLink(Link):
    """Output of ``origin`` into ``model_list``: items are announced, not moved."""

    def __init__(self, origin: Any, model_list: Any):
        self.origin = origin
        self.list = model_list

    def announce(self, item: Any, origin: Any = None) -> None:
        if not self.list.contains(item):
            self.list.push(item, origin=origin or self.origin)

    def send(self, the_item: Any, origin: Any = None) -> bool:
        if self.list.contains(the_item):
            # retried by the origin (e.g. after a resume): the queries may match now
            self.list.reevaluate()
        else:
            self.list.push(the_item, origin=origin or self.origin)
        return False        # the item stays in its origin until a pull takes it

    def notify_available(self, source: Any = None) -> bool:
        return False

    def get_origins(self) -> List[Any]:
        return [self.origin]

    def get_destinations(self) -> List[Any]:
        return []


class ListInputLink(Link):
    """Input of ``puller`` from ``model_list``: one pull at a time while there is space."""

    def __init__(self, model_list: Any, puller: Any, query: Union[None, str, Query] = None, *, priority: float = 0):
        self.list = model_list
        self.puller = puller
        self.user_query = Query.of(query)
        self.priority = priority
        self.query = self._combined_query()
        self._backorder = None
        self.transfers = 0
        puller.model.add_list_link(self)

    def _combined_query(self) -> Query:
        user, puller = self.user_query, self.puller

        def where(scope) -> bool:
            entry = scope.entry
            origin = entry.origin
            # (whether the origin already holds the item is checked at delivery: an origin
            # announces an item in send() and registers it right after)
            if origin is not None and origin._output_blocks:
                return False
            if not puller.can_accept(entry.value, origin):
                return False
            return user.matches(scope)

        combined = Query(where=where, text=user.text)
        combined._order = user._order
        return combined

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """New run (the list was cleared): ask for items if there is space."""
        self._backorder = None
        self.transfers = 0
        self._request()

    def _request(self) -> None:
        if self._backorder is not None and self._backorder.pending:
            return
        self._backorder = None
        puller = self.puller
        if puller._input_blocks or puller.get_free_capacity() <= 0:
            return
        result = self.list.pull(self.query, puller=puller, on_fulfilled=self._on_fulfilled,
                                priority=self.priority, entries=True)
        if result.pending:
            self._backorder = result

    def notify_available(self, source: Any = None) -> bool:
        """The puller has space again (or was resumed)."""
        if self._backorder is not None and self._backorder.pending:
            self.list.reevaluate()
        else:
            self._request()
        return False

    def send(self, the_item: Any, origin: Any = None) -> bool:
        raise NotImplementedError("A list input link does not send items")

    # ------------------------------------------------------------------ transfer
    def _on_fulfilled(self, entries: List[Any]) -> None:
        if self.list.deliver == "immediate":
            # never transfer inside the origin's send(): it has not registered the item yet
            self.puller.model.schedule(lambda: self._deliver(entries), 0.0)
        else:
            self._deliver(entries)

    def _deliver(self, entries: List[Any]) -> None:
        self._backorder = None
        entry = entries[0]
        item, origin, puller = entry.value, entry.origin, self.puller
        still_there = origin is None or (not origin._output_blocks and origin.holds_item(item))
        if not still_there or not puller.can_accept(item, origin):
            if origin is None or origin.holds_item(item):
                self.list.restore(entry)        # still available for others (or for us later)
            self._request()
            return
        stats = puller.get_stats_collector()
        stats.on_entry(item)
        if not puller.receive(item):
            stats.rollback_entry(item)
            self.list.restore(entry)
            return
        if origin is not None:
            origin.get_stats_collector().on_exit(item)
            origin.release_item(item)
        self.transfers += 1
        self._request()

    def get_origins(self) -> List[Any]:
        return []

    def get_destinations(self) -> List[Any]:
        return [self.puller]


__all__ = ["ListOutputLink", "ListInputLink"]
