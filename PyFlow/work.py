"""Pausable work: a delayed action that can be paused and resumed (breakdowns, shifts).

    handle = element.schedule_work(on_done, 10.0)
    handle.pause()      # remaining time is frozen
    handle.resume()     # completes ``remaining`` later

Pauses nest: with two overlapping pauses the work only continues after both resumes.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .SimClock.simClock import EventHandle, SimClock


class WorkHandle:
    __slots__ = ("clock", "action", "duration", "remaining", "end_time", "started_at",
                 "_event", "_pauses", "done", "cancelled", "tag")

    def __init__(self, clock: SimClock, action: Callable[[], Any], duration: float, *, tag: Any = None):
        if not duration >= 0:
            raise ValueError(f"E_NEGATIVE_DELAY: work duration {duration!r}")
        self.clock = clock
        self.action = action
        self.duration = duration
        self.remaining = duration
        self.started_at = clock.now
        self.end_time: Optional[float] = None
        self._event: Optional[EventHandle] = None
        self._pauses = 0
        self.done = False
        self.cancelled = False
        self.tag = tag
        self._schedule()

    def _schedule(self) -> None:
        self.end_time = self.clock.now + self.remaining
        self._event = self.clock.schedule_event(self, self.remaining)

    # Event protocol
    def execute(self) -> None:
        self._event = None
        self.remaining = 0.0
        self.done = True
        self.action()

    @property
    def paused(self) -> bool:
        return self._pauses > 0

    @property
    def active(self) -> bool:
        """Scheduled and running (not paused, finished or cancelled)."""
        return self._event is not None

    def time_left(self) -> float:
        if self.active:
            return self.end_time - self.clock.now
        return self.remaining

    def pause(self) -> None:
        if self.done or self.cancelled:
            return
        self._pauses += 1
        if self._pauses == 1 and self._event is not None:
            self.remaining = self.end_time - self.clock.now
            self._event.cancel()
            self._event = None
            self.end_time = None

    def resume(self) -> None:
        if self.done or self.cancelled or self._pauses == 0:
            return
        self._pauses -= 1
        if self._pauses == 0:
            self._schedule()

    def cancel(self) -> bool:
        if self.done or self.cancelled:
            return False
        self.cancelled = True
        if self._event is not None:
            self._event.cancel()
            self._event = None
        return True

    def __repr__(self) -> str:
        state = "done" if self.done else "cancelled" if self.cancelled else "paused" if self.paused else "running"
        return f"WorkHandle({state}, remaining={self.time_left():g})"


__all__ = ["WorkHandle"]
