"""Downtime generators: breakdowns (MTBF/MTTR), timetables and shifts (SimuLean parity).

Generators register with the model of their target and are started by
``model.initialize()`` *after* the elements (element start clears stops).

    MtbfMttrDowntime(machine, ttf="ExponentialMean~3600", ttr="ExponentialMean~300")
    TimetableDowntime(machine, [DowntimeInterval(100, 30, "SCHEDULED_DOWN")])
    ShiftDowntime(machine, WeeklyShiftPattern.parse("Mon-Fri 06:00-22:00"))
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from .simcalendar import SimCalendar, WeeklyShiftPattern
from .states import ElementState
from .stops import StopMode, StopToken


@dataclass(frozen=True)
class DowntimeInterval:
    start: float
    duration: float
    state: Optional[str] = None     # None: the generator's state
    mode: Optional[str] = None      # None: the generator's mode
    code: Optional[str] = None
    reason: Optional[str] = None

    @property
    def end(self) -> float:
        return self.start + self.duration


class OverlapPolicy:
    ALLOW = "allow"          # overlapping intervals produce overlapping stops
    SERIALIZE = "serialize"  # an interval starting inside the previous one is moved to its end
    MERGE = "merge"          # overlapping intervals are joined (first interval's state/code)
    ALL = (ALLOW, SERIALIZE, MERGE)


class DowntimeBasis:
    CALENDAR = "calendar"    # time to failure counts all time
    BUSY = "busy"            # time to failure counts only time in ``busy_states``
    ALL = (CALENDAR, BUSY)


class _Call:
    """Event that calls a function (lets generators cancel their own events)."""
    __slots__ = ("fn",)

    def __init__(self, fn: Callable[[], Any]):
        self.fn = fn

    def execute(self) -> None:
        self.fn()


class DowntimeGenerator:
    """Base class. ``state``/``mode``/``block_input``/``block_output`` define the stops."""

    default_state = ElementState.BREAKDOWN
    default_mode = StopMode.IMMEDIATE

    def __init__(self, target, *, state: Optional[str] = None, mode: Optional[str] = None,
                 block_input: bool = True, block_output: Optional[bool] = None, name: Optional[str] = None):
        self.target = target
        self.model = target.model
        self.clock = target.clock
        self.state = state or self.default_state
        self.mode = StopMode.parse(mode or self.default_mode)
        self.block_input = block_input
        self.block_output = block_output
        self.name = name or f"{type(self).__name__}:{target.name}"
        self._events = []
        self._open: List[StopToken] = []
        self.stop_count = 0
        self.total_downtime = 0.0
        self._listeners: Dict[str, List[Callable]] = {}
        self.model.add_generator(self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.target.name}, state={self.state}, stops={self.stop_count})"

    # events: stop_started(generator, token), stop_ended(generator, token)
    def on(self, event: str, fn: Callable) -> None:
        if event not in ("stop_started", "stop_ended"):
            raise ValueError(f"E_UNKNOWN_EVENT: {event!r}")
        self._listeners.setdefault(event, []).append(fn)

    def _emit(self, event: str, token: StopToken) -> None:
        for fn in self._listeners.get(event, ()):
            fn(self, token)

    def start(self) -> None:
        self.cancel_pending()
        self._open.clear()
        self.stop_count = 0
        self.total_downtime = 0.0
        self._on_start()

    def reset_stats(self) -> None:
        self.stop_count = len(self._open)
        self.total_downtime = 0.0

    def _on_start(self) -> None:
        pass

    def cancel_pending(self) -> None:
        for event in self._events:
            event.cancel()
        self._events.clear()

    def _schedule(self, fn: Callable[[], Any], delay: float):
        handle = self.clock.schedule_event(_Call(fn), max(0.0, delay))
        self._events.append(handle)
        if len(self._events) > 64:
            self._events = [e for e in self._events if e.pending]
        return handle

    def begin_stop(self, state: Optional[str] = None, mode: Optional[str] = None,
                   code: Optional[str] = None, reason: Optional[str] = None) -> StopToken:
        token = self.target.stop(state or self.state, mode or self.mode, block_input=self.block_input,
                                 block_output=self.block_output, code=code, reason=reason, source=self)
        self._open.append(token)
        self.stop_count += 1
        self._emit("stop_started", token)
        return token

    def end_stop(self, token: StopToken) -> bool:
        if token in self._open:
            self._open.remove(token)
        if not self.target.resume(token):
            return False
        self.total_downtime += token.duration
        self._emit("stop_ended", token)
        return True


class TimetableDowntime(DowntimeGenerator):
    """Stops at fixed times. Intervals already over at start are skipped and an interval in
    progress is clipped to its remaining part."""

    default_state = ElementState.SCHEDULED_DOWN

    def __init__(self, target, intervals: Iterable[DowntimeInterval], *, overlap: str = OverlapPolicy.ALLOW, **kw):
        super().__init__(target, **kw)
        overlap = str(overlap).lower()
        if overlap not in OverlapPolicy.ALL:
            raise ValueError(f"E_INVALID_OVERLAP: {overlap!r}; use one of {OverlapPolicy.ALL}")
        self.overlap = overlap
        self.intervals = self.normalize(intervals, overlap)

    @staticmethod
    def normalize(intervals: Iterable[DowntimeInterval], overlap: str) -> List[DowntimeInterval]:
        ordered = sorted(intervals, key=lambda iv: iv.start)  # stable: ties keep input order
        if overlap == OverlapPolicy.ALLOW:
            return ordered
        result: List[DowntimeInterval] = []
        for iv in ordered:
            if result and iv.start < result[-1].end:
                last = result[-1]
                if overlap == OverlapPolicy.SERIALIZE:
                    iv = replace(iv, start=last.end)
                else:  # MERGE
                    result[-1] = replace(last, duration=max(last.end, iv.end) - last.start)
                    continue
            result.append(iv)
        return result

    def _on_start(self) -> None:
        self._next = 0
        self._schedule_next()

    def _schedule_next(self) -> None:
        now = self.clock.now
        while self._next < len(self.intervals):
            iv = self.intervals[self._next]
            if iv.duration > 0 and iv.end > now:
                start = max(iv.start, now)
                self._schedule(lambda iv=iv, start=start: self._fire(iv, iv.end - start), start - now)
                return
            self._next += 1

    def _fire(self, iv: DowntimeInterval, duration: float) -> None:
        token = self.begin_stop(iv.state, iv.mode, iv.code, iv.reason)
        self._schedule(lambda: self.end_stop(token), duration)
        self._next += 1
        self._schedule_next()


class MtbfMttrDowntime(DowntimeGenerator):
    """Random failures: time to failure ``ttf`` and time to repair ``ttr`` (sampler specs).

    ``basis="calendar"``: the time to failure counts from the end of the previous repair.
    ``basis="busy"``: it only counts while the element's visible state is in ``busy_states``
    (default ``{PROCESSING}``), so idle, blocked or off-shift time does not wear the machine.

    ``repair_resources``: units needed to repair (technicians, a crane...): ``ResourcePool``
    or ``ResourceRequirement`` objects (``during`` is ignored: they are held for the whole
    repair). After a failure the element shows ``repair_wait_state`` (``WAITING_FOR_REPAIR``)
    until all of them are granted, then ``state`` (``BREAKDOWN``) for ``ttr``; the units are
    released when the repair ends. ``repair_priority`` orders the request against other
    requests on the same pools (higher first; production requests use the item priority).
    """

    def __init__(self, target, ttf: Any, ttr: Any, *, first_failure: Any = None,
                 basis: str = DowntimeBasis.CALENDAR, busy_states: Iterable[str] = (ElementState.PROCESSING,),
                 code: str = "MTBF", repair_resources: Optional[Sequence[Any]] = None,
                 repair_priority: float = 0, repair_wait_state: str = ElementState.WAITING_FOR_REPAIR, **kw):
        super().__init__(target, **kw)
        from .resources import as_requirements
        self.repair_requirements = as_requirements(repair_resources)
        for req in self.repair_requirements:
            if req.pool.model is not self.model:
                raise ValueError(f"E_INVALID_RESOURCE: pool {req.pool.name!r} belongs to another model")
        needed: Dict[Any, int] = {}
        for req in self.repair_requirements:
            needed[req.pool] = needed.get(req.pool, 0) + req.quantity
        for pool, quantity in needed.items():
            if quantity > pool.capacity:
                raise ValueError(f"E_RESOURCE_INSUFFICIENT: the repair of {target.name!r} needs {quantity} unit(s) "
                                 f"of {pool.name!r} at once but the pool has {pool.capacity}")
        self.repair_priority = repair_priority
        self.repair_wait_state = repair_wait_state
        basis = str(basis).lower()
        if basis not in DowntimeBasis.ALL:
            raise ValueError(f"E_INVALID_BASIS: {basis!r}; use one of {DowntimeBasis.ALL}")
        self.basis = basis
        self.busy_states = frozenset(busy_states)
        self.code = code
        self.ttf = self.model.bind_sampler(ttf, f"{self.name}.ttf")
        self.ttr = self.model.bind_sampler(ttr, f"{self.name}.ttr")
        self.first_failure = (self.model.bind_sampler(first_failure, f"{self.name}.first")
                              if first_failure is not None else None)
        self._token: Optional[StopToken] = None
        self._failure_event = None
        self._started = False
        self._allocation = None
        self._repair_request = None
        self._reset_repair_stats()
        if self.basis == DowntimeBasis.BUSY:
            target.on("state_changed", self._on_state_changed)

    def _draw_ttf(self, first: bool = False) -> float:
        sampler = self.first_failure if first and self.first_failure is not None else self.ttf
        return max(0.0, sampler.sample())

    def _reset_repair_stats(self) -> None:
        self.repairs = 0                 # repairs started
        self.repair_wait_total = 0.0     # time from failure to repair start (waiting for resources)
        self.repair_wait_max = 0.0

    def reset_stats(self) -> None:
        super().reset_stats()
        self._reset_repair_stats()

    def _on_start(self) -> None:
        self._token = None
        self._failure_event = None
        self._allocation = None          # the manager was cleared by Model.initialize
        self._repair_request = None
        self._reset_repair_stats()
        self._started = True
        if self.basis == DowntimeBasis.CALENDAR:
            self._failure_event = self._schedule(self._fail, self._draw_ttf(first=True))
        else:
            self._remaining_busy = self._draw_ttf(first=True)
            if self.target.state in self.busy_states:
                self._arm()

    def _fail(self) -> None:
        self._failure_event = None
        if not self.repair_requirements:
            self._token = self.begin_stop(self.state, self.mode, self.code)
            self._start_repair(None)
            return
        self._token = self.begin_stop(self.repair_wait_state, self.mode, self.code)
        failed_at = self.clock.now
        self._repair_request = self.model.resources.request(
            self.repair_requirements, self, lambda allocation: self._start_repair(allocation, failed_at),
            priority=self.repair_priority, kind="repair")

    def _start_repair(self, allocation, failed_at: Optional[float] = None) -> None:
        self._repair_request = None
        self._allocation = allocation
        self.repairs += 1
        if failed_at is not None:
            wait = self.clock.now - failed_at
            self.repair_wait_total += wait
            self.repair_wait_max = max(self.repair_wait_max, wait)
            self.target.restate_stop(self._token, self.state)
        self._schedule(self._repair, max(0.0, self.ttr.sample()))

    def _repair(self) -> None:
        if self._allocation is not None:
            allocation, self._allocation = self._allocation, None
            self.model.resources.release(allocation)
        token, self._token = self._token, None
        if self.basis == DowntimeBasis.CALENDAR:
            self.end_stop(token)
            self._failure_event = self._schedule(self._fail, self._draw_ttf())
        else:
            self._remaining_busy = self._draw_ttf()   # before resume: resume may arm
            self.end_stop(token)
            if self.target.state in self.busy_states:
                self._arm()

    # busy-time basis
    def _arm(self) -> None:
        if self._failure_event is not None or self._token is not None:
            return
        self._armed_at = self.clock.now
        self._failure_event = self._schedule(self._fail, self._remaining_busy)

    def _disarm(self) -> None:
        if self._failure_event is None:
            return
        self._failure_event.cancel()
        self._failure_event = None
        self._remaining_busy = max(0.0, self._remaining_busy - (self.clock.now - self._armed_at))

    def _on_state_changed(self, element, old: str, new: str) -> None:
        if not self._started or (self._token is not None and self._token.active):
            return  # our own breakdown
        was, now = old in self.busy_states, new in self.busy_states
        if was and not now:
            self._disarm()
        elif now and not was:
            self._arm()


class ShiftDowntime(DowntimeGenerator):
    """Stops the element outside the working windows of a weekly shift pattern.
    Defaults: state ``OFF_SHIFT``, mode ``after_current`` (the current job is finished)."""

    default_state = ElementState.OFF_SHIFT
    default_mode = StopMode.AFTER_CURRENT

    def __init__(self, target, pattern: WeeklyShiftPattern, **kw):
        super().__init__(target, **kw)
        if isinstance(pattern, str):
            pattern = WeeklyShiftPattern.parse(pattern)
        self.pattern = pattern

    def _on_start(self) -> None:
        self._token = None
        self._tick()

    def _tick(self) -> None:
        calendar: SimCalendar = self.model.calendar
        date = calendar.to_datetime(self.clock.now)
        working = self.pattern.is_working(date)
        if working and self._token is not None:
            self.end_stop(self._token)
            self._token = None
        elif not working and self._token is None:
            self._token = self.begin_stop(self.state, self.mode, "SHIFT", "Off shift")
        change = self.pattern.next_change(date)
        if change is not None:
            self._schedule(self._tick, calendar.to_sim_time(change) - self.clock.now)


# ---------------------------------------------------------------------------
# Downtime tables
# ---------------------------------------------------------------------------

@dataclass
class DowntimeTableMapping:
    """Column names and conversions for :func:`downtimes_from_table`."""
    target_column: Optional[str] = None       # None: every row belongs to target ""
    start_column: str = "start"
    end_column: Optional[str] = None
    duration_column: Optional[str] = "duration"
    code_column: Optional[str] = None
    reason_column: Optional[str] = None
    duration_scale: float = 1.0
    state_by_code: Optional[Mapping[str, str]] = None
    default_state: str = ElementState.STOPPED
    mode_by_code: Optional[Mapping[str, str]] = None
    default_mode: str = StopMode.IMMEDIATE
    factor_by_code: Optional[Mapping[str, float]] = None
    ignored_codes: Sequence[str] = ()


def _lookup(table: Optional[Mapping[str, Any]], code: Optional[str]):
    if not table or code is None:
        return None
    lowered = {str(k).lower(): v for k, v in table.items()}
    return lowered.get(str(code).lower())


def _missing(value) -> bool:
    """Empty cell: ``None`` or NaN (pandas fills empty cells with NaN)."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def _rows(table) -> Iterable[Mapping[str, Any]]:
    if hasattr(table, "to_dict"):           # pandas DataFrame
        return table.to_dict(orient="records")
    return table


def downtimes_from_table(table, mapping: Optional[DowntimeTableMapping] = None,
                         calendar: Optional[SimCalendar] = None) -> Dict[str, List[DowntimeInterval]]:
    """Read downtime rows (iterable of dicts or a pandas DataFrame) into
    ``{target: [DowntimeInterval, ...]}`` in table order.

    Start/end cells may be simulation times or dates (converted with ``calendar``). Rows with
    an ignored code, an unreadable start or a non-positive duration are skipped; the number
    of skipped rows is available as ``result.skipped`` (attribute of the returned dict).
    """
    m = mapping or DowntimeTableMapping()
    cal = calendar or SimCalendar.default()
    ignored = {str(c).lower() for c in m.ignored_codes}
    result: Dict[str, List[DowntimeInterval]] = _Result()
    skipped = 0

    def to_time(value) -> Optional[float]:
        if _missing(value):
            return None
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        try:
            return cal.parse_sim_time(value) if not hasattr(value, "year") else cal.to_sim_time(value)
        except ValueError:
            return None

    for row in _rows(table):
        code = row.get(m.code_column) if m.code_column else None
        code = None if _missing(code) else str(code)
        if code is not None and code.lower() in ignored:
            skipped += 1
            continue
        start = to_time(row.get(m.start_column))
        if start is None:
            skipped += 1
            continue
        duration = None
        if m.duration_column and not _missing(row.get(m.duration_column)):
            try:
                duration = float(str(row[m.duration_column]).replace(",", ".")) * m.duration_scale
            except ValueError:
                duration = None
        if duration is None and m.end_column:
            end = to_time(row.get(m.end_column))
            duration = end - start if end is not None else None
        if duration is None:
            skipped += 1
            continue
        factor = _lookup(m.factor_by_code, code)
        if factor is not None:
            duration *= float(factor)
        if not duration > 0:
            skipped += 1
            continue
        state = _lookup(m.state_by_code, code) or m.default_state
        mode = _lookup(m.mode_by_code, code) or m.default_mode
        reason = row.get(m.reason_column) if m.reason_column else None
        reason = None if _missing(reason) else reason
        target = row.get(m.target_column) if m.target_column else ""
        key = "" if _missing(target) else str(target)
        result.setdefault(key, []).append(DowntimeInterval(start, duration, state, mode, code, reason))
    result.skipped = skipped
    return result


class _Result(dict):
    skipped: int = 0


__all__ = ["DowntimeInterval", "OverlapPolicy", "DowntimeBasis", "DowntimeGenerator", "TimetableDowntime",
           "MtbfMttrDowntime", "ShiftDowntime", "DowntimeTableMapping", "downtimes_from_table"]
