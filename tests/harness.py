"""Deterministic test harness (pattern of SimuLean's StandaloneTests).

* ``Feeder``    emits an item every ``interval`` (first one at ``start``); rejected items
                are held and retried in FIFO order on ``unblock``.
* ``Collector`` sink that records ``(t, item)``; ``close()`` makes it refuse items so
                that blocking can be forced, ``open()`` accepts again and pulls upstream.
* ``at``        schedules an intervention ``fn()`` at absolute time ``t``.
"""
from collections import deque
from typing import Callable, List, Optional, Tuple

from PyFlow import Element, Item, Model


class Feeder(Element):
    def __init__(self, name: str, model: Model, interval: float, *, count: Optional[int] = None,
                 start: float = 0.0, item_type: str = "Default", labels: Optional[dict] = None):
        super().__init__(name, model)
        self.interval = interval
        self.count = count
        self.first = start
        self.item_type = item_type
        self.labels = labels or {}

    def start(self) -> None:
        self.emitted = 0
        self.sent: List[Tuple[float, Item]] = []
        self.held = deque()
        self.clock.schedule_event(self, self.first)

    def execute(self) -> None:
        item = self._new_item(item_type=self.item_type, labels=dict(self.labels))
        self.emitted += 1
        if self.held or not self.get_output().send(item):
            self.held.append(item)
        else:
            self.sent.append((self.clock.now, item))
        if self.count is None or self.emitted < self.count:
            self.clock.schedule_event(self, self.interval)

    def unblock(self) -> bool:
        if self.held and self.get_output().send(self.held[0]):
            self.sent.append((self.clock.now, self.held.popleft()))
            return True
        return False

    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("Feeder cannot receive items")

    def check_availability(self, the_item: Item) -> bool:
        return False


class Collector(Element):
    def __init__(self, name: str, model: Model):
        super().__init__(name, model)
        self.is_open = True

    def start(self) -> None:
        self.received: List[Tuple[float, Item]] = []

    @property
    def times(self) -> List[float]:
        return [t for t, _ in self.received]

    @property
    def ids(self) -> List[int]:
        return [item.item_number for _, item in self.received]

    def close(self) -> None:
        self.is_open = False

    def open(self) -> None:
        self.is_open = True
        while self.get_input() is not None and self.get_input().notify_available():
            pass

    def receive(self, the_item: Item) -> bool:
        self.received.append((self.clock.now, the_item))
        return True

    def check_availability(self, the_item: Item) -> bool:
        return self.is_open

    def unblock(self) -> bool:
        return False


def at(model: Model, t: float, fn: Callable[[], object]):
    return model.schedule_at(fn, t)
