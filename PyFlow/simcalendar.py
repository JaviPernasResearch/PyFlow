"""Simulation calendar (time <-> date) and weekly shift patterns (SimuLean parity).

    cal = SimCalendar(datetime(2026, 1, 5, 6, 0), seconds_per_unit=60)   # 1 unit = 1 minute
    cal.to_datetime(90)            # 2026-01-05 07:30
    shifts = WeeklyShiftPattern.parse("Mon-Fri 06:00-14:00,14:00-22:00; Sat 06:00-14:00",
                                      holidays=["2026-01-06"])
    shifts.is_working(datetime(2026, 1, 5, 23, 0))   # False
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple, Union

DateLike = Union[str, date, datetime]

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
)


def parse_date(value: DateLike) -> datetime:
    """Parse ``yyyy-MM-dd[ HH:mm[:ss]]``, ISO ``T`` variants or day-first ``dd/MM/yyyy``."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        raise ValueError(f"E_INVALID_DATE: cannot parse {value!r}") from None


class SimCalendar:
    """Maps simulation time to dates: ``date = start + t * seconds_per_unit``."""

    DEFAULT_START = datetime(2000, 1, 1)

    def __init__(self, start: DateLike = DEFAULT_START, seconds_per_unit: float = 1.0):
        if not seconds_per_unit > 0:
            raise ValueError("E_INVALID_CALENDAR: seconds_per_unit must be > 0")
        self.start = parse_date(start)
        self.seconds_per_unit = float(seconds_per_unit)

    @classmethod
    def default(cls) -> "SimCalendar":
        return cls()

    @property
    def is_default(self) -> bool:
        return self.start == self.DEFAULT_START and self.seconds_per_unit == 1.0

    def to_datetime(self, t: float) -> datetime:
        return self.start + timedelta(seconds=t * self.seconds_per_unit)

    def to_sim_time(self, value: DateLike) -> float:
        return (parse_date(value) - self.start).total_seconds() / self.seconds_per_unit

    def from_seconds(self, seconds: float) -> float:
        return seconds / self.seconds_per_unit

    def to_seconds(self, t: float) -> float:
        return t * self.seconds_per_unit

    def from_timedelta(self, delta: timedelta) -> float:
        return delta.total_seconds() / self.seconds_per_unit

    def parse_sim_time(self, value) -> float:
        """A number is already simulation time; anything else is parsed as a date."""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        text = str(value).strip()
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return self.to_sim_time(text)

    def format(self, t: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        return self.to_datetime(t).strftime(fmt)

    def __repr__(self) -> str:
        return f"SimCalendar(start={self.start:%Y-%m-%d %H:%M:%S}, seconds_per_unit={self.seconds_per_unit:g})"


# ---------------------------------------------------------------------------
# Weekly shift pattern
# ---------------------------------------------------------------------------

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")   # datetime.weekday() order


@dataclass(frozen=True)
class ShiftWindow:
    day: int            # 0 = Monday ... 6 = Sunday
    start: timedelta    # from 00:00 of ``day``
    end: timedelta      # if end <= start the window ends the next day

    @property
    def length(self) -> timedelta:
        return self.end - self.start if self.end > self.start else self.end + timedelta(days=1) - self.start


def _parse_day(token: str) -> int:
    key = token.strip().lower()[:3]
    if key not in _DAYS:
        raise ValueError(f"E_INVALID_SHIFT: unknown day {token!r}")
    return _DAYS.index(key)


def _parse_days(spec: str) -> List[int]:
    days: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (_parse_day(x) for x in part.split("-", 1))
            d = a
            while True:                      # ranges wrap: Fri-Mon = Fri, Sat, Sun, Mon
                days.append(d)
                if d == b:
                    break
                d = (d + 1) % 7
        else:
            days.append(_parse_day(part))
    if not days:
        raise ValueError(f"E_INVALID_SHIFT: no days in {spec!r}")
    return days


_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _parse_time(text: str) -> timedelta:
    m = _TIME_RE.match(text.strip())
    if not m:
        raise ValueError(f"E_INVALID_SHIFT: bad time {text!r} (use HH:mm)")
    h, mnt, sec = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if (h, mnt, sec) != (24, 0, 0) and (h > 23 or mnt > 59 or sec > 59):
        raise ValueError(f"E_INVALID_SHIFT: bad time {text!r}")
    return timedelta(hours=h, minutes=mnt, seconds=sec)


class WeeklyShiftPattern:
    """Working windows per weekday plus holidays.

    Grammar (SimuLean): groups separated by ``;``, each ``<days> <ranges>``:
    days are names (first 3 letters) or wrapping ranges (``Mon-Fri``, ``Fri-Mon``) separated
    by commas; ranges are ``HH:mm-HH:mm`` separated by commas. ``22:00-06:00`` crosses
    midnight, ``00:00-24:00`` is a whole day. Windows that *start* on a holiday are skipped.
    Intervals are half-open ``[start, end)``; touching windows merge.
    """

    def __init__(self, windows: Iterable[ShiftWindow] = (), holidays: Iterable[DateLike] = ()):
        self.windows: List[ShiftWindow] = list(windows)
        self.holidays = {parse_date(h).date() for h in holidays}

    @classmethod
    def parse(cls, text: str, holidays: Iterable[DateLike] = ()) -> "WeeklyShiftPattern":
        pattern = cls(holidays=holidays)
        for group in (text or "").split(";"):
            group = group.strip()
            if not group:
                continue
            m = re.match(r"^([A-Za-z,\-\s]+?)\s+(\d.*)$", group)   # days may contain ", "
            if not m:
                raise ValueError(f"E_INVALID_SHIFT: expected '<days> <HH:mm-HH:mm>' in {group!r}")
            days = _parse_days(m.group(1))
            for rng in m.group(2).split(","):
                if "-" not in rng:
                    raise ValueError(f"E_INVALID_SHIFT: bad range {rng!r}")
                a, b = rng.split("-", 1)
                start, end = _parse_time(a), _parse_time(b)
                for d in days:
                    pattern.add(d, start, end)
        return pattern

    def add(self, day: Union[int, str], start: Union[str, timedelta], end: Union[str, timedelta]) -> None:
        day = _parse_day(day) if isinstance(day, str) else int(day)
        start = _parse_time(start) if isinstance(start, str) else start
        end = _parse_time(end) if isinstance(end, str) else end
        self.windows.append(ShiftWindow(day, start, end))

    def add_holiday(self, value: DateLike) -> None:
        self.holidays.add(parse_date(value).date())

    def merged_windows(self, start: datetime, end: datetime) -> List[Tuple[datetime, datetime]]:
        """Working intervals overlapping ``[start, end)``, merged and sorted."""
        raw = []
        day = datetime.combine(start.date() - timedelta(days=1), time())
        last = datetime.combine(end.date(), time())
        while day <= last:
            if day.date() not in self.holidays:
                for w in self.windows:
                    if w.day == day.weekday():
                        s = day + w.start
                        e = s + w.length
                        if e > start and s < end:
                            raw.append((s, e))
            day += timedelta(days=1)
        raw.sort()
        merged: List[Tuple[datetime, datetime]] = []
        for s, e in raw:
            if merged and s <= merged[-1][1]:
                if e > merged[-1][1]:
                    merged[-1] = (merged[-1][0], e)
            else:
                merged.append((s, e))
        return merged

    def is_working(self, when: datetime) -> bool:
        return any(s <= when < e for s, e in self.merged_windows(when - timedelta(days=1), when + timedelta(days=1)))

    def next_change(self, when: datetime) -> Optional[datetime]:
        """End of the current working window, or start of the next one (``None`` if none
        within the next 15 days)."""
        for s, e in self.merged_windows(when - timedelta(days=1), when + timedelta(days=15)):
            if s <= when < e:
                return e
            if s > when:
                return s
        return None

    def working_time(self, start: datetime, end: datetime) -> timedelta:
        """Total working time inside ``[start, end)``."""
        total = timedelta()
        for s, e in self.merged_windows(start, end):
            total += min(e, end) - max(s, start)
        return total


__all__ = ["SimCalendar", "WeeklyShiftPattern", "ShiftWindow", "parse_date"]
