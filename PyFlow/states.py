"""Element states and their time accounting.

States are plain strings, so models can add their own (``"CLEANING"``) next to the
predefined constants. :class:`StateTracker` records every change and the time spent
in each state since the last reset (warm-up), not since t = 0.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple


class ElementState:
    """Predefined state names (SimuLean ``ElementState``)."""
    # element activity
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
    BLOCKED = "BLOCKED"
    RECEIVING = "RECEIVING"
    SETUP = "SETUP"
    TRAVELLING = "TRAVELLING"
    WAITING_FOR_OPERATOR = "WAITING_FOR_OPERATOR"   # SimuLean name, kept for custom elements
    WAITING_FOR_RESOURCE = "WAITING_FOR_RESOURCE"   # waiting for units of a ResourcePool
    # downtime (shown while a stop is active)
    STOPPED = "STOPPED"
    BREAKDOWN = "BREAKDOWN"
    SCHEDULED_DOWN = "SCHEDULED_DOWN"
    OFF_SHIFT = "OFF_SHIFT"

    ALL = (IDLE, PROCESSING, BLOCKED, RECEIVING, SETUP, TRAVELLING, WAITING_FOR_OPERATOR, WAITING_FOR_RESOURCE,
           STOPPED, BREAKDOWN, SCHEDULED_DOWN, OFF_SHIFT)


class StateTracker:
    """Current state, change log and accumulated time per state of one element."""

    def __init__(self, t0: float = 0.0, initial: str = ElementState.IDLE, *, keep_log: bool = True):
        self.keep_log = keep_log
        self.state = initial
        self.reset(t0, clear_log=True)

    def reset(self, t: float, *, clear_log: bool = False) -> None:
        """Restart the accounting at ``t`` keeping the current state (warm-up)."""
        self.t0 = t
        self.since = t
        self.durations: Dict[str, float] = {}
        if clear_log or not hasattr(self, "log"):
            self.log: List[Tuple[float, str]] = [(t, self.state)] if self.keep_log else []

    def restart(self, t: float, initial: str = ElementState.IDLE) -> None:
        """New run: back to ``initial`` with an empty log."""
        self.state = initial
        self.reset(t, clear_log=True)

    def set(self, state: str, t: float) -> Optional[str]:
        """Change to ``state`` at time ``t``. Returns the previous state, or ``None`` if unchanged."""
        if state == self.state:
            return None
        if t < self.since:
            raise ValueError(f"state change at t={t} before last change at t={self.since}")
        previous = self.state
        self.durations[previous] = self.durations.get(previous, 0.0) + (t - self.since)
        self.state = state
        self.since = t
        if self.keep_log:
            self.log.append((t, state))
        return previous

    def time_in_state(self, state: str, now: float) -> float:
        total = self.durations.get(state, 0.0)
        if state == self.state:
            total += now - self.since
        return total

    def ratio(self, state: str, now: float) -> float:
        elapsed = now - self.t0
        return self.time_in_state(state, now) / elapsed if elapsed > 0 else float(state == self.state)

    def breakdown(self, now: float) -> Dict[str, float]:
        """Time in every state visited since the last reset (sums to ``now - t0``)."""
        result = dict(self.durations)
        result[self.state] = result.get(self.state, 0.0) + (now - self.since)
        return {k: v for k, v in result.items() if v > 0 or k == self.state}

    def ratios(self, now: float) -> Dict[str, float]:
        elapsed = now - self.t0
        if elapsed <= 0:
            return {self.state: 1.0}
        return {k: v / elapsed for k, v in self.breakdown(now).items()}


__all__ = ["ElementState", "StateTracker"]
