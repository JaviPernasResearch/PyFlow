"""States, pausable work, stops and events of every element (SimuLean ``ElementDowntime``).

* ``element.state`` is the visible (accounted) state. While a stop is effective its state
  (``BREAKDOWN``, ``OFF_SHIFT``...) is shown and the element's own state is kept as
  ``underlying_state``.
* ``element.schedule_work(fn, delay)`` returns a :class:`~PyFlow.work.WorkHandle`. Immediate
  stops pause all work of the element; it continues where it left off on resume.
* ``token = element.stop(state=..., mode="immediate" | "after_current", block_input=True,
  block_output=None)`` and ``element.resume(token)``. Stops can overlap: input/output blocks
  are counted and the element only runs again when every stop has ended. The most recent
  effective stop is the one shown. ``after_current`` stops let the current work finish and
  become visible when no work is pending; ``block_output`` defaults to ``mode == "immediate"``.
* ``element.on(event, fn)`` with events ``state_changed(element, old, new)``,
  ``item_entered(element, item)``, ``item_exited(element, item)``,
  ``stopped(element, token)`` and ``resumed(element, token)``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional

from .states import ElementState, StateTracker
from .work import WorkHandle


class StopMode:
    IMMEDIATE = "immediate"
    AFTER_CURRENT = "after_current"
    ALL = (IMMEDIATE, AFTER_CURRENT)

    @staticmethod
    def parse(mode: str) -> str:
        normalized = str(mode).strip().lower().replace("-", "_")
        normalized = {"aftercurrent": StopMode.AFTER_CURRENT}.get(normalized, normalized)
        if normalized not in StopMode.ALL:
            raise ValueError(f"E_INVALID_STOP_MODE: {mode!r}; use 'immediate' or 'after_current'")
        return normalized


@dataclass(frozen=True)
class StopRequest:
    """What a stop does. Immutable, so it can be shared safely between stops."""
    state: str = ElementState.STOPPED
    mode: str = StopMode.IMMEDIATE
    block_input: bool = True
    block_output: Optional[bool] = None
    code: Optional[str] = None
    reason: Optional[str] = None
    source: Any = None

    def __post_init__(self):
        object.__setattr__(self, "mode", StopMode.parse(self.mode))
        if not self.state:
            raise ValueError("E_INVALID_STATE: a stop needs a state name")

    @property
    def blocks_output(self) -> bool:
        return self.block_output if self.block_output is not None else self.mode == StopMode.IMMEDIATE


class StopToken:
    """Handle of an active (or finished) stop, returned by ``element.stop``."""

    def __init__(self, request: StopRequest, target, start_time: float):
        self.request = request
        self.target = target
        self.start_time = start_time
        self.end_time = math.nan
        self.active = True

    @property
    def state(self) -> str:
        return self.request.state

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def __repr__(self) -> str:
        end = "" if self.active else f"{self.end_time:g}"
        code = f" {self.request.code}" if self.request.code else ""
        return f"Stop[{self.target.name} {self.state}{code} t={self.start_time:g}..{end}]"


EVENTS = ("state_changed", "item_entered", "item_exited", "stopped", "resumed")


class ElementRuntime:
    """Mixin used by :class:`~PyFlow.Elements.element.Element`."""

    # ------------------------------------------------------------------ setup
    def _init_runtime(self) -> None:
        self._listeners: Dict[str, List[Callable]] = {}
        self._tracker = StateTracker(self.clock.now)
        self._underlying = ElementState.IDLE
        self._shown_stop: Optional[StopToken] = None
        self._work: List[WorkHandle] = []
        self._stops: List[StopToken] = []
        self._input_blocks = 0
        self._output_blocks = 0
        self._immediate_stops = 0
        self._pause_started_at = 0.0
        self.stop_count = 0
        self.last_pause_duration = 0.0

    def _reset_runtime(self) -> None:
        """New run: cancel work, drop stops, back to IDLE (called by ``Model.initialize``)."""
        for handle in list(self._work):
            handle.cancel()
        self._work.clear()
        self._stops.clear()
        self._input_blocks = self._output_blocks = self._immediate_stops = 0
        self._shown_stop = None
        self._underlying = ElementState.IDLE
        self.stop_count = 0
        self.last_pause_duration = 0.0
        self._tracker.restart(self.clock.now, ElementState.IDLE)

    # ------------------------------------------------------------------ events
    def on(self, event: str, fn: Callable) -> Callable[[], None]:
        """Subscribe ``fn`` to ``event``. Returns a function that unsubscribes it."""
        if event not in EVENTS:
            raise ValueError(f"E_UNKNOWN_EVENT: {event!r}; known events: {', '.join(EVENTS)}")
        self._listeners.setdefault(event, []).append(fn)
        return lambda: self._listeners[event].remove(fn) if fn in self._listeners[event] else None

    def _emit(self, event: str, *args) -> None:
        listeners = self._listeners.get(event)
        if listeners:
            for fn in list(listeners):
                fn(self, *args)

    # ------------------------------------------------------------------ states
    @property
    def state(self) -> str:
        return self._tracker.state

    @property
    def underlying_state(self) -> str:
        return self._underlying

    def _set_state(self, state: str) -> None:
        """Element's own state. Hidden (but remembered) while a stop is shown."""
        self._underlying = state
        if self._shown_stop is None and state != self._tracker.state:
            self._apply_state(state)

    def _apply_state(self, state: str) -> None:
        old = self._tracker.set(state, self.clock.sim_time)
        if old is not None and self._listeners:
            self._emit("state_changed", old, state)

    def time_in_state(self, state: str) -> float:
        return self._tracker.time_in_state(state, self.clock.now)

    def state_ratio(self, state: str) -> float:
        """Fraction of the time since the last statistics reset spent in ``state``."""
        return self._tracker.ratio(state, self.clock.now)

    def state_breakdown(self) -> Dict[str, float]:
        return self._tracker.breakdown(self.clock.now)

    def state_ratios(self) -> Dict[str, float]:
        return self._tracker.ratios(self.clock.now)

    @property
    def state_log(self):
        """``[(time, state entered), ...]`` since the start of the run."""
        return list(self._tracker.log)

    # ------------------------------------------------------------------ work
    def schedule_work(self, action: Callable[[], Any], delay: float, *, tag: Any = None) -> WorkHandle:
        """Run ``action`` after ``delay`` of *working* time (paused by immediate stops)."""
        handle = WorkHandle(self.clock, lambda: self._work_done(handle, action), delay, tag=tag)
        if self._immediate_stops:
            handle.pause()
        self._work.append(handle)
        return handle

    def _work_done(self, handle: WorkHandle, action: Callable[[], Any]) -> None:
        self._forget_work(handle)
        action()
        if self._stops and self._shown_stop is None:
            self._refresh_down_state()

    def _forget_work(self, handle: WorkHandle) -> None:
        if handle in self._work:
            self._work.remove(handle)

    def cancel_work(self, handle: WorkHandle) -> bool:
        if not handle.cancel():
            return False
        self._forget_work(handle)
        if self._stops and self._shown_stop is None:
            self._refresh_down_state()
        return True

    @property
    def pending_work_count(self) -> int:
        return len(self._work)

    # ------------------------------------------------------------------ stops
    @property
    def is_down(self) -> bool:
        return bool(self._stops)

    @property
    def is_input_blocked(self) -> bool:
        return self._input_blocks > 0

    @property
    def is_output_blocked(self) -> bool:
        return self._output_blocks > 0

    @property
    def is_work_paused(self) -> bool:
        return self._immediate_stops > 0

    @property
    def active_stops(self) -> List[StopToken]:
        return list(self._stops)

    def can_accept(self, the_item, origin=None) -> bool:
        """Used by links and output strategies: not stopped, available and accepted by the
        input strategy (which may look at the ``origin`` element)."""
        if self._input_blocks or not self.check_availability(the_item):
            return False
        strategy = self.input_strategy
        return strategy is None or strategy.accepts(self, the_item, origin)

    def stop(self, state: str = ElementState.STOPPED, mode: str = StopMode.IMMEDIATE, *,
             block_input: bool = True, block_output: Optional[bool] = None, code: Optional[str] = None,
             reason: Optional[str] = None, source: Any = None,
             request: Optional[StopRequest] = None) -> StopToken:
        """Stop the element (breakdown, shift end...). Returns the token for ``resume``."""
        if request is None:
            request = StopRequest(state, mode, block_input, block_output, code, reason, source)
        token = StopToken(request, self, self.clock.now)
        self._stops.append(token)
        self.stop_count += 1
        if request.block_input:
            self._input_blocks += 1
        if request.blocks_output:
            self._output_blocks += 1
        if request.mode == StopMode.IMMEDIATE:
            self._immediate_stops += 1
            if self._immediate_stops == 1:
                self._pause_all_work()
        self._refresh_down_state()
        self._emit("stopped", token)
        return token

    def resume(self, token: StopToken) -> bool:
        """End a stop. Returns ``False`` if the token is not an active stop of this element."""
        if token is None or not token.active or token not in self._stops:
            return False
        token.active = False
        token.end_time = self.clock.now
        self._stops.remove(token)
        request = token.request
        if request.block_input:
            self._input_blocks -= 1
        if request.blocks_output:
            self._output_blocks -= 1
        if request.mode == StopMode.IMMEDIATE:
            self._immediate_stops -= 1
            if self._immediate_stops == 0:
                self._resume_all_work()
        self._refresh_down_state()
        self._emit("resumed", token)
        if not self.is_output_blocked:
            self._retry_output()
        # Pull everything upstream can send now (a single notification, as in SimuLean, can
        # leave items stuck upstream when this element passes them straight through)
        link = self.get_input()
        while link is not None and not self._input_blocks and link.notify_available():
            pass
        return True

    def restate_stop(self, token: StopToken, state: str) -> bool:
        """Change the state shown by an active stop (e.g. WAITING_FOR_REPAIR -> BREAKDOWN when
        the technician arrives) without ending it: same stop, same blocking, same pause."""
        if token is None or not token.active or token not in self._stops:
            return False
        token.request = replace(token.request, state=state)
        self._refresh_down_state()
        return True

    def _retry_output(self) -> None:
        try:
            while self.unblock():
                pass
        except NotImplementedError:  # elements that never send (Sink)
            pass

    def _pause_all_work(self) -> None:
        self._pause_started_at = self.clock.now
        for handle in self._work:
            handle.pause()

    def _resume_all_work(self) -> None:
        self.last_pause_duration = self.clock.now - self._pause_started_at
        for handle in list(self._work):
            handle.resume()

    def _refresh_down_state(self) -> None:
        shown = None
        for token in reversed(self._stops):
            if token.request.mode == StopMode.IMMEDIATE or not self._work:
                shown = token
                break
        if shown is not None:
            self._shown_stop = shown
            self._apply_state(shown.state)
        elif self._shown_stop is not None:
            self._shown_stop = None
            self._apply_state(self._underlying)


__all__ = ["StopMode", "StopRequest", "StopToken", "ElementRuntime", "EVENTS"]
