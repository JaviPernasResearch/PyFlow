import math

import pytest

from PyFlow import Model


def test_simultaneous_events_fire_in_fifo_order(model):
    fired = []
    for name in "abcde":
        model.schedule(lambda n=name: fired.append(n), 5.0)
    model.schedule(lambda: fired.append("early"), 1.0)
    model.run(10)
    assert fired == ["early", "a", "b", "c", "d", "e"]


def test_events_scheduled_at_current_time_run_after_pending_ones(model):
    fired = []

    def first():
        fired.append("first")
        model.schedule(lambda: fired.append("nested"), 0.0)

    model.schedule(first, 2.0)
    model.schedule(lambda: fired.append("second"), 2.0)
    model.run(2)
    assert fired == ["first", "second", "nested"]


def test_cancelled_event_does_not_fire(model):
    fired = []
    handle = model.schedule(lambda: fired.append("x"), 3.0)
    model.schedule(lambda: fired.append("y"), 4.0)
    assert handle.pending
    assert handle.cancel() is True
    assert handle.cancel() is False
    assert model.clock.pending_events() == 1
    model.run(10)
    assert fired == ["y"]
    assert not handle.fired


def test_cancel_after_fire_returns_false(model):
    handle = model.schedule(lambda: None, 1.0)
    model.run(2)
    assert handle.fired and handle.cancel() is False


def test_advance_clock_leaves_now_exactly_at_t(model):
    model.schedule(lambda: None, 3.0)
    assert model.advance_clock(7.5) is False
    assert model.now == 7.5
    assert model.clock.last_event_time == 3.0


def test_advance_clock_returns_true_when_events_remain(model):
    model.schedule(lambda: None, 3.0)
    model.schedule(lambda: None, 30.0)
    assert model.advance_clock(10) is True
    assert model.now == 10
    assert model.clock.peek_next_time() == 30.0


def test_event_exactly_at_horizon_fires(model):
    fired = []
    model.schedule(lambda: fired.append(model.now), 10.0)
    model.run(10)
    assert fired == [10.0]


def test_advance_to_infinity_stops_at_last_event(model):
    model.schedule(lambda: None, 4.0)
    assert model.advance_clock(math.inf) is False
    assert model.now == 4.0


def test_clock_cannot_go_backwards(model):
    model.run(5)
    with pytest.raises(ValueError, match="E_CLOCK_BACKWARDS"):
        model.run(4)


def test_negative_delay_is_rejected(model):
    with pytest.raises(ValueError, match="E_NEGATIVE_DELAY"):
        model.schedule(lambda: None, -1.0)
    with pytest.raises(ValueError, match="E_NEGATIVE_DELAY"):
        model.schedule(lambda: None, float("nan"))


def test_schedule_at_absolute_time(model):
    fired = []
    model.run(2)
    model.schedule_at(lambda: fired.append(model.now), 6.0)
    with pytest.raises(ValueError, match="E_PAST_EVENT"):
        model.schedule_at(lambda: None, 1.0)
    model.run(10)
    assert fired == [6.0]


def test_event_objects_with_execute_are_supported(model):
    class Ev:
        def __init__(self):
            self.t = None

        def execute(self):
            self.t = model.now

    ev = Ev()
    model.schedule(ev, 2.5)
    model.run(3)
    assert ev.t == 2.5


def test_clock_monotonic_with_many_random_events():
    m = Model(seed=7)
    rng = m.rng("test")
    times = []
    for d in rng.uniform(0, 100, size=500):
        m.schedule(lambda: times.append(m.now), float(d))
    m.run(100)
    assert len(times) == 500
    assert times == sorted(times)


def test_reinitialize_keeps_pending_event_count(model):
    """Regression: work cancelled by initialize() after the calendar reset was counted twice,
    so advance_clock() reported an empty calendar while events were still pending."""
    from PyFlow import InfiniteSource, MultiServer, Sink
    src = InfiniteSource("Src", model)
    server = MultiServer(1, 1, "M", model)
    sink = Sink("Sink", model)
    src.connect([server])
    server.connect([sink])
    model.initialize()
    model.run(5.5)                      # server busy: its work handle is still pending
    model.initialize()
    assert model.clock.pending_events() == len([h for *_, h in model.clock._queue if h.pending])
    assert all(model.advance_clock(t) for t in (1, 2, 3))
    assert sink.get_stats_collector().get_var_input_value() == 3
