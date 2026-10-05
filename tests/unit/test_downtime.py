"""Downtime generators and tables (exact, hand-computed values)."""
from datetime import datetime

import pandas as pd
import pytest

from PyFlow import (DowntimeInterval, DowntimeTableMapping, ElementState as S, Model, MtbfMttrDowntime,
                    MultiServer, OverlapPolicy, ShiftDowntime, SimCalendar, TimetableDowntime,
                    WeeklyShiftPattern, downtimes_from_table)
from tests.harness import Collector, Feeder


def station(model, *, interval=1000, count=0, service=10):
    feeder = Feeder("Feeder", model, interval=interval, count=count)
    server = MultiServer(1, service, "M1", model)
    sink = Collector("Sink", model)
    feeder.connect([server])
    server.connect([sink])
    return server, sink


# ------------------------------------------------------------------ timetable
def test_timetable_stops(model):
    server, _ = station(model)
    gen = TimetableDowntime(server, [DowntimeInterval(10, 5), DowntimeInterval(30, 10, S.BREAKDOWN, code="X")])
    model.initialize()
    model.run(100)
    assert server.time_in_state(S.SCHEDULED_DOWN) == 5
    assert server.time_in_state(S.BREAKDOWN) == 10
    assert gen.stop_count == 2 and gen.total_downtime == 15


def test_timetable_clips_running_and_skips_past_intervals(model):
    server, _ = station(model)
    TimetableDowntime(server, [DowntimeInterval(-10, 5), DowntimeInterval(-5, 10)])
    model.initialize()
    model.run(20)
    assert server.time_in_state(S.SCHEDULED_DOWN) == 5      # [0, 5) of the second interval


def test_timetable_pauses_work(model):
    server, sink = station(model, count=1)
    TimetableDowntime(server, [DowntimeInterval(4, 6, mode="immediate")])
    model.initialize()
    model.run(30)
    assert sink.times == [16]


@pytest.mark.parametrize("policy, expected", [
    (OverlapPolicy.ALLOW, [(0, 10), (5, 10), (6, 2)]),
    (OverlapPolicy.SERIALIZE, [(0, 10), (10, 10), (20, 2)]),
    (OverlapPolicy.MERGE, [(0, 15)]),
])
def test_overlap_policies(policy, expected):
    ivs = [DowntimeInterval(5, 10), DowntimeInterval(0, 10), DowntimeInterval(6, 2)]
    got = TimetableDowntime.normalize(ivs, policy)
    assert [(iv.start, iv.duration) for iv in got] == expected


def test_overlapping_timetable_allow_stacks_stops(model):
    server, _ = station(model)
    TimetableDowntime(server, [DowntimeInterval(0, 10, "A"), DowntimeInterval(5, 10, "B")])
    model.initialize()
    model.run(30)
    assert server.time_in_state("A") == 5 and server.time_in_state("B") == 10


# ------------------------------------------------------------------ MTBF / MTTR
def test_mtbf_calendar_basis(model):
    server, _ = station(model)
    gen = MtbfMttrDowntime(server, ttf=12, ttr=3)
    model.initialize()
    model.run(50)
    # failures at 12, 27, 42 (time to failure counts from the end of each repair)
    assert [t for t, s in server.state_log if s == S.BREAKDOWN] == [12, 27, 42]
    assert gen.stop_count == 3 and gen.total_downtime == 9
    assert server.time_in_state(S.BREAKDOWN) == 9


def test_mtbf_busy_basis_counts_only_processing_time(model):
    """Jobs every 10 s, 5 s each; 12 s of processing between failures, 3 s repairs.
    Busy 0-5, 10-15, 20-22 -> fails at 22, repaired 25, job ends 28.
    Then busy 25-28, 30-35, 40-44 -> fails at 44."""
    server, sink = station(model, interval=10, count=10, service=5)
    MtbfMttrDowntime(server, ttf=12, ttr=3, basis="busy")
    model.initialize()
    model.run(60)
    assert [t for t, s in server.state_log if s == S.BREAKDOWN] == [22, 44]
    assert sink.times[:5] == [5, 15, 28, 35, 48]


def test_mtbf_is_seeded_and_reproducible():
    def run(seed):
        m = Model(seed=seed)
        server, _ = station(m)
        MtbfMttrDowntime(server, ttf="ExponentialMean~20", ttr="Uniform~1~3")
        m.initialize()
        m.run(1000)
        return server.state_log
    assert run(1) == run(1) and run(1) != run(2)


# ------------------------------------------------------------------ shifts
def shift_model(**calendar):
    return Model(seed=1, calendar=SimCalendar(datetime(2026, 1, 5), seconds_per_unit=3600))  # hours, Monday


def test_shift_downtime_hours():
    m = shift_model()
    server, _ = station(m)
    gen = ShiftDowntime(server, WeeklyShiftPattern.parse("Mon-Fri 06:00-14:00"))
    m.initialize()
    m.run(24)
    assert server.time_in_state(S.OFF_SHIFT) == pytest.approx(16)
    m.run(168)
    assert server.time_in_state(S.OFF_SHIFT) == pytest.approx(168 - 40)
    assert gen.stop_count == 6          # one per gap: Mon 0-6, 5 evenings (last one lasts the weekend)


def test_shift_finishes_current_job_and_only_works_in_shift():
    m = shift_model()
    server, sink = station(m, interval=0.25, count=400, service=0.5)
    ShiftDowntime(server, "Mon-Fri 06:00-14:00")
    m.initialize()
    m.run(100)
    hours = [t % 24 for t in sink.times]
    assert sink.times and all(6 < h <= 14.0 for h in hours)
    assert max(hours) == pytest.approx(14.0)            # job running at 14:00 is finished


# ------------------------------------------------------------------ tables
def test_downtimes_from_rows_and_dataframe():
    cal = SimCalendar("2026-01-05 00:00", seconds_per_unit=60)
    rows = [
        {"machine": "M1", "start": "2026-01-05 01:00", "end": "2026-01-05 01:30", "code": "BRK"},
        {"machine": "M1", "start": 200, "minutes": 10, "code": "set"},
        {"machine": "M2", "start": "05/01/2026 03:00", "minutes": 5, "code": "PM"},
        {"machine": "M2", "start": "never", "minutes": 5, "code": "PM"},
        {"machine": "M1", "start": 10, "minutes": 5, "code": "IGN"},
        {"machine": "M1", "start": 10, "minutes": 0, "code": "BRK"},
    ]
    mapping = DowntimeTableMapping(target_column="machine", end_column="end", duration_column="minutes",
                                   code_column="code", state_by_code={"brk": S.BREAKDOWN},
                                   mode_by_code={"SET": "after_current"}, factor_by_code={"PM": 2},
                                   ignored_codes=["ign"])
    for table in (rows, pd.DataFrame(rows)):
        result = downtimes_from_table(table, mapping, cal)
        assert result.skipped == 3
        m1, m2 = result["M1"], result["M2"]
        assert [(iv.start, iv.duration, iv.state, iv.mode) for iv in m1] == [
            (60, 30, S.BREAKDOWN, "immediate"), (200, 10, S.STOPPED, "after_current")]
        assert [(iv.start, iv.duration) for iv in m2] == [(180, 10)]


def test_table_drives_timetable(model):
    server, _ = station(model)
    table = downtimes_from_table([{"start": 5, "duration": 2}, {"start": 20, "duration": 3}])
    TimetableDowntime(server, table[""])
    model.initialize()
    model.run(40)
    assert server.time_in_state(S.STOPPED) == 5
