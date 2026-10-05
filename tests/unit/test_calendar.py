from datetime import datetime, timedelta

import pytest

from PyFlow import SimCalendar, WeeklyShiftPattern

MON = datetime(2026, 1, 5)   # a Monday


def d(day_offset, hh, mm=0):
    return MON + timedelta(days=day_offset, hours=hh, minutes=mm)


def test_calendar_conversions():
    cal = SimCalendar("2026-01-05 06:00", seconds_per_unit=60)
    assert cal.to_datetime(90) == datetime(2026, 1, 5, 7, 30)
    assert cal.to_sim_time(datetime(2026, 1, 5, 7, 30)) == 90
    assert cal.to_sim_time("05/01/2026 08:00") == 120          # day-first
    assert cal.parse_sim_time("12,5") == 12.5
    assert cal.parse_sim_time(3) == 3
    assert cal.format(90, "%H:%M") == "07:30"
    assert SimCalendar().is_default
    with pytest.raises(ValueError, match="E_INVALID_CALENDAR"):
        SimCalendar(seconds_per_unit=0)
    with pytest.raises(ValueError, match="E_INVALID_DATE"):
        cal.to_sim_time("yesterday")


def test_two_shifts_and_saturday():
    p = WeeklyShiftPattern.parse("Mon-Fri 06:00-14:00,14:00-22:00; Sat 06:00-14:00")
    assert not p.is_working(d(0, 5, 59))
    assert p.is_working(d(0, 6))
    assert p.is_working(d(0, 21, 59))
    assert not p.is_working(d(0, 22))                          # half-open
    assert p.next_change(d(0, 10)) == d(0, 22)                 # 14:00 shifts merge
    assert p.is_working(d(5, 13)) and not p.is_working(d(6, 10))
    assert p.next_change(d(5, 15)) == d(7, 6)                  # Saturday afternoon -> Monday
    assert p.working_time(MON, MON + timedelta(days=7)) == timedelta(hours=5 * 16 + 8)


def test_overnight_wrapping_days_and_whole_day():
    night = WeeklyShiftPattern.parse("Mon-Fri 22:00-06:00")
    assert night.is_working(d(1, 3))        # Tuesday early hours: Monday's shift
    assert night.is_working(d(5, 3))        # Saturday early hours: Friday's shift
    assert not night.is_working(d(0, 3))    # Monday early hours: no Sunday shift
    wrap = WeeklyShiftPattern.parse("Fri-Mon 08:00-09:00")
    assert [wrap.is_working(d(k, 8, 30)) for k in range(7)] == [True, False, False, False, True, True, True]
    whole = WeeklyShiftPattern.parse("Mon 00:00-24:00")
    assert whole.is_working(d(0, 23, 59)) and not whole.is_working(d(1, 0))


def test_holidays_skip_windows_that_start_on_them():
    p = WeeklyShiftPattern.parse("Mon-Fri 22:00-06:00", holidays=["2026-01-06"])
    assert p.is_working(d(1, 3))            # started on Monday
    assert not p.is_working(d(1, 23))       # Tuesday's own shift is a holiday


def test_lenient_day_lists_and_errors():
    p = WeeklyShiftPattern.parse("Mon, Wed 06:00-07:00")
    assert p.is_working(d(2, 6, 30)) and not p.is_working(d(1, 6, 30))
    for bad in ["Xyz 06:00-07:00", "Mon 6-7", "Mon 25:00-26:00", "Mon"]:
        with pytest.raises(ValueError, match="E_INVALID_SHIFT"):
            WeeklyShiftPattern.parse(bad)


def test_empty_pattern_never_works():
    p = WeeklyShiftPattern.parse("")
    assert not p.is_working(MON) and p.next_change(MON) is None
