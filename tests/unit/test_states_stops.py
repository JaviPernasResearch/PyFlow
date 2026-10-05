"""States, pausable work, stops and element events (exact, hand-computed values)."""
import pytest

from PyFlow import ElementState as S
from PyFlow import ItemsQueue, MultiServer, StopRequest, WorkHandle
from tests.harness import Collector, Feeder, at


def line(model, *, interval=100, count=1, service=10, servers=1):
    feeder = Feeder("Feeder", model, interval=interval, count=count)
    server = MultiServer(servers, service, "Server", model)
    sink = Collector("Sink", model)
    feeder.connect([server])
    server.connect([sink])
    return feeder, server, sink


# ------------------------------------------------------------------ work handle
def test_work_handle_pause_resume_nested(model):
    done = []
    model.initialize()
    h = WorkHandle(model.clock, lambda: done.append(model.now), 10)
    at(model, 3, h.pause)
    at(model, 4, h.pause)      # nested
    at(model, 6, h.resume)     # still paused
    at(model, 8, h.resume)     # 7 left -> done at 15
    model.run(30)
    assert done == [15]
    assert h.done and not h.paused


def test_work_handle_cancel(model):
    done = []
    model.initialize()
    h = WorkHandle(model.clock, lambda: done.append(1), 5)
    assert h.cancel() and not h.cancel()
    model.run(10)
    assert done == []


# ------------------------------------------------------------------ states
def test_state_log_of_blocked_server(model):
    """Item at 0, 10 s of work, sink closed until 15: IDLE -> PROCESSING -> BLOCKED -> IDLE."""
    _, server, sink = line(model)
    sink.close()
    model.initialize()
    at(model, 15, sink.open)
    model.run(20)
    assert server.state_log == [(0, S.IDLE), (0, S.PROCESSING), (10, S.BLOCKED), (15, S.IDLE)]
    assert server.time_in_state(S.PROCESSING) == 10
    assert server.time_in_state(S.BLOCKED) == 5
    assert server.time_in_state(S.IDLE) == 5
    assert sum(server.state_breakdown().values()) == pytest.approx(20)
    assert server.state_ratio(S.PROCESSING) == pytest.approx(0.5)
    assert sink.times == [15]


def test_queue_and_source_states(model):
    feeder = Feeder("Feeder", model, interval=1, count=3)
    queue = ItemsQueue(1, "Queue", model)
    sink = Collector("Sink", model)
    feeder.connect([queue])
    queue.connect([sink])
    sink.close()
    model.initialize()
    model.run(5)
    assert queue.state == S.BLOCKED
    sink.open()
    assert queue.state == S.IDLE


def test_state_ratios_since_warmup(model):
    """Ratios use the time since the last reset, not since t = 0 (SimuLean divides by t)."""
    _, server, _ = line(model, interval=20, count=10, service=10)
    model.initialize()
    model.run(100, warmup=50)
    # after t=50 the server works 60-70, 80-90 and 50 (idle until 60): 20 of 50
    assert server.time_in_state(S.PROCESSING) == pytest.approx(20)
    assert server.state_ratio(S.PROCESSING) == pytest.approx(20 / 50)
    assert sum(server.state_ratios().values()) == pytest.approx(1)


def test_state_changed_and_item_events(model):
    _, server, _ = line(model, interval=20, count=2, service=5)
    changes, entered, exited = [], [], []
    server.on("state_changed", lambda e, old, new: changes.append((model.now, old, new)))
    server.on("item_entered", lambda e, item: entered.append(item.item_number))
    unsubscribe = server.on("item_exited", lambda e, item: exited.append(item.item_number))
    model.initialize()
    model.run(50)
    assert changes == [(0, S.IDLE, S.PROCESSING), (5, S.PROCESSING, S.IDLE),
                       (20, S.IDLE, S.PROCESSING), (25, S.PROCESSING, S.IDLE)]
    assert entered == exited == [1, 2]
    unsubscribe()
    with pytest.raises(ValueError, match="E_UNKNOWN_EVENT"):
        server.on("nope", print)


# ------------------------------------------------------------------ stops
def test_immediate_stop_pauses_work(model):
    """SimuLean TestStop: 10 s of work, breakdown 5-10 -> leaves at 15, 5 s in BREAKDOWN."""
    _, server, sink = line(model)
    model.initialize()
    token = {}
    at(model, 5, lambda: token.setdefault("t", server.stop(S.BREAKDOWN)))
    at(model, 10, lambda: server.resume(token["t"]))
    model.run(14.9)
    assert sink.times == []
    model.run(20)
    assert sink.times == [15]
    assert server.time_in_state(S.BREAKDOWN) == pytest.approx(5)
    assert server.time_in_state(S.PROCESSING) == pytest.approx(10)
    assert token["t"].duration == 5 and not token["t"].active
    assert server.last_pause_duration == 5


def test_after_current_stop_finishes_job_and_blocks_input(model):
    """Jobs every 2 s (10 s each). Stop after_current at 5: job 1 ends at 10, then the
    machine shows OFF_SHIFT and takes nothing until the resume at 20."""
    feeder, server, sink = line(model, interval=2, count=3)
    model.initialize()
    token = {}
    at(model, 5, lambda: token.setdefault("t", server.stop(S.OFF_SHIFT, "after_current")))
    at(model, 20, lambda: server.resume(token["t"]))
    model.run(60)
    assert sink.times == [10, 30, 40]
    assert server.time_in_state(S.OFF_SHIFT) == pytest.approx(10)
    assert (5, S.OFF_SHIFT) not in server.state_log       # still working at 5


def test_after_current_without_work_shows_at_once(model):
    _, server, _ = line(model, count=0)
    model.initialize()
    at(model, 3, lambda: server.stop(S.OFF_SHIFT, "after_current"))
    model.run(5)
    assert server.state == S.OFF_SHIFT


def test_overlapping_stops(model):
    """Breakdown 5-15 and a stop 8-12 on a 10 s job started at 0: work resumes at 15 and
    ends at 20. The most recent stop is the one shown."""
    _, server, sink = line(model)
    model.initialize()
    tokens = {}
    at(model, 5, lambda: tokens.setdefault("a", server.stop(S.BREAKDOWN)))
    at(model, 8, lambda: tokens.setdefault("b", server.stop(S.STOPPED)))
    at(model, 12, lambda: server.resume(tokens["b"]))
    at(model, 15, lambda: server.resume(tokens["a"]))
    model.run(30)
    assert sink.times == [20]
    assert server.time_in_state(S.BREAKDOWN) == pytest.approx(3 + 3)
    assert server.time_in_state(S.STOPPED) == pytest.approx(4)
    assert server.resume(tokens["a"]) is False                # already resumed


def test_stopped_element_blocks_input_and_output(model):
    feeder = Feeder("Feeder", model, interval=1, count=5)
    queue = ItemsQueue(10, "Queue", model)
    sink = Collector("Sink", model)
    feeder.connect([queue])
    queue.connect([sink])
    model.initialize()
    token = {}
    at(model, 0.5, lambda: token.setdefault("t", queue.stop(S.STOPPED)))
    at(model, 10, lambda: queue.resume(token["t"]))
    model.run(20)
    assert sink.times == [0, 10, 10, 10, 10]                  # held by the feeder until 10
    assert len(feeder.sent) == 5


def test_output_only_stop_lets_items_in(model):
    feeder = Feeder("Feeder", model, interval=1, count=3)
    queue = ItemsQueue(10, "Queue", model)
    sink = Collector("Sink", model)
    feeder.connect([queue])
    queue.connect([sink])
    model.initialize()
    token = queue.stop(S.STOPPED, block_input=False, block_output=True)
    at(model, 5, lambda: queue.resume(token))
    model.run(10)
    assert queue.get_stats_collector().get_var_input_value() == 3
    assert sink.times == [5, 5, 5]


def test_stop_request_is_reusable_and_immutable(model):
    _, server, _ = line(model, count=0)
    model.initialize()
    request = StopRequest(S.BREAKDOWN, "immediate", code="E1")
    t1 = server.stop(request=request)
    t2 = server.stop(request=request)
    assert server.is_input_blocked and server.is_output_blocked and server.is_work_paused
    server.resume(t1)
    assert server.is_down
    server.resume(t2)
    assert not (server.is_down or server.is_input_blocked or server.is_output_blocked)
    with pytest.raises(Exception):
        request.mode = "after_current"
    with pytest.raises(ValueError, match="E_INVALID_STOP_MODE"):
        StopRequest(mode="later")


def test_initialize_clears_stops(model):
    _, server, _ = line(model, count=0)
    model.initialize()
    server.stop(S.BREAKDOWN)
    model.initialize()
    assert not server.is_down and server.state == S.IDLE and server.stop_count == 0


# ------------------------------------------------------------------ setup
def test_setup_time_on_type_change(model):
    """A, A, B, A arrive at 0 (queue); service 1, setup 2 when the type changes:
    A 0-1, A 1-2, setup 2-4, B 4-5, setup 5-7, A 7-8."""
    from PyFlow import Item, ScheduleSource, Sink
    orders = {"Time": [0, 0, 0], "Name": ["A", "B", "A"], "Q": [2, 1, 1]}
    source = ScheduleSource("Orders", model, data_dict=orders)
    queue = ItemsQueue(10, "Queue", model)
    server = MultiServer(1, 1, "Server", model, setup_time=2)
    sink = Collector("Sink", model)
    source.connect([queue])
    queue.connect([server])
    server.connect([sink])
    model.initialize()
    model.run(20)
    assert sink.times == [1, 2, 5, 8]
    assert server.time_in_state(S.SETUP) == pytest.approx(4)
    assert server.time_in_state(S.PROCESSING) == pytest.approx(4)


def test_setup_matrix_and_breakdown_pauses_setup(model):
    orders = {"Time": [0, 0], "Name": ["A", "B"], "Q": [1, 1]}
    from PyFlow import ScheduleSource
    source = ScheduleSource("Orders", model, data_dict=orders)
    queue = ItemsQueue(10, "Queue", model)
    server = MultiServer(1, 1, "Server", model, setup_time={("A", "B"): 3, "A": 7})
    sink = Collector("Sink", model)
    source.connect([queue])
    queue.connect([server])
    server.connect([sink])
    model.initialize()
    token = {}
    at(model, 2, lambda: token.setdefault("t", server.stop(S.BREAKDOWN)))   # during setup 1-4
    at(model, 6, lambda: server.resume(token["t"]))
    model.run(20)
    assert sink.times == [1, 9]          # setup 1-2 + 6-8, B 8-9
    assert server.time_in_state(S.SETUP) == pytest.approx(3)
