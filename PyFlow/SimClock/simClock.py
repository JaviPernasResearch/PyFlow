"""Discrete-event clock: a binary heap of events ordered by ``(time, seq)``.

Each :class:`SimClock` belongs to exactly one :class:`~PyFlow.model.Model`. Several
models (and therefore several clocks) can live in the same process without sharing
state.
"""
from __future__ import annotations

import heapq
import math
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple, Union

from .event import Event

if TYPE_CHECKING:
    from ..model import Model


class EventHandle:
    """Reference to a scheduled event. ``cancel()`` removes it from the calendar."""

    __slots__ = ("time", "seq", "target", "cancelled", "fired", "_clock")

    def __init__(self, time: float, seq: int, target: Union[Event, Callable[[], Any]], clock: "SimClock"):
        self.time = time
        self.seq = seq
        self.target = target
        self.cancelled = False
        self.fired = False
        self._clock = clock

    @property
    def pending(self) -> bool:
        return not (self.cancelled or self.fired)

    def cancel(self) -> bool:
        """Cancel the event. Returns ``True`` if it was still pending."""
        if not self.pending:
            return False
        self.cancelled = True
        self._clock._live -= 1
        return True

    def __repr__(self) -> str:
        state = "cancelled" if self.cancelled else "fired" if self.fired else "pending"
        return f"EventHandle(t={self.time}, seq={self.seq}, {state})"


class SimClock:
    """Event calendar of one model.

    * Simultaneous events fire in scheduling order (FIFO tie-break on a sequence number).
    * ``schedule_event`` returns an :class:`EventHandle` that can be cancelled (lazy deletion).
    * ``advance_clock(t)`` fires every event with time ``<= t`` and leaves ``now == t``.
    """


    def __init__(self, model: Optional["Model"] = None):
        self.sim_time: float = 0.0
        self.last_event_time: float = 0.0
        self._queue: List[Tuple[float, int, EventHandle]] = []
        self._seq: int = 0
        self._live: int = 0
        if model is None:
            from ..model import Model
            model = Model(_clock=self)
        self.model: "Model" = model

    @property
    def sim_elements(self) -> list:
        return self.model.elements

    def add_element(self, element: Any) -> None:
        self.model.add_element(element)

    # ------------------------------------------------------------------ time
    @property
    def now(self) -> float:
        return self.sim_time

    def get_simulation_time(self) -> float:
        return self.sim_time

    # ------------------------------------------------------------------ scheduling
    def schedule_event(self, the_event: Union[Event, Callable[[], Any]], time: float) -> EventHandle:
        """Schedule ``the_event`` to fire ``time`` units from now."""
        if not time >= 0:  # also rejects NaN
            raise ValueError(f"E_NEGATIVE_DELAY: cannot schedule an event {time!r} time units in the past")
        return self.schedule_at(the_event, self.sim_time + time)

    def schedule_at(self, the_event: Union[Event, Callable[[], Any]], time: float) -> EventHandle:
        """Schedule ``the_event`` at absolute simulation time ``time``."""
        if not time >= self.sim_time:
            raise ValueError(f"E_PAST_EVENT: cannot schedule at t={time!r} (now={self.sim_time})")
        handle = EventHandle(time, self._seq, the_event, self)
        heapq.heappush(self._queue, (time, self._seq, handle))
        self._seq += 1
        self._live += 1
        return handle

    def pending_events(self) -> int:
        """Number of scheduled, non-cancelled events."""
        return self._live

    def peek_next_time(self) -> float:
        """Time of the next pending event, or ``inf`` if the calendar is empty."""
        self._drop_cancelled()
        return self._queue[0][0] if self._queue else math.inf

    def _drop_cancelled(self) -> None:
        while self._queue and self._queue[0][2].cancelled:
            heapq.heappop(self._queue)

    def advance_clock(self, time: float) -> bool:
        """Fire every event with time ``<= time`` and leave the clock exactly at ``time``.

        If ``time`` is infinite the clock stops at the last fired event.
        Returns ``True`` if pending events remain, ``False`` if the calendar is empty.
        """
        if time < self.sim_time:
            raise ValueError(f"E_CLOCK_BACKWARDS: cannot advance to t={time} (now={self.sim_time})")
        queue = self._queue
        while queue:
            t, _, handle = queue[0]
            if handle.cancelled:
                heapq.heappop(queue)
                continue
            if t > time:
                break
            heapq.heappop(queue)
            handle.fired = True
            self._live -= 1
            self.sim_time = t
            self.last_event_time = t
            target = handle.target
            execute = getattr(target, "execute", None)
            if execute is not None:
                execute()
            else:
                target()
        if not math.isinf(time):
            self.sim_time = time
        return self._live > 0

    # ------------------------------------------------------------------ lifecycle
    def initialize(self) -> None:
        """Reset the model and start all of its elements (see ``Model.initialize``)."""
        self.model.initialize()

    def reset(self) -> None:
        """Empty the calendar and set the time back to 0 (elements stay registered)."""
        self.sim_time = 0.0
        self.last_event_time = 0.0
        # Discarded events must not be counted again if someone still holding their handle
        # (e.g. an element's pending work) cancels them after the reset.
        for _, _, handle in self._queue:
            handle.cancelled = True
        self._queue.clear()
        self._seq = 0
        self._live = 0
