"""Task executers, task sequences and resource pools made of executers (exact cases)."""
import pytest

from PyFlow import Item, MtbfMttrDowntime, MultiServer, ResourcePool, Sink
from PyFlow.executers import (Callback, Load, Operator, TaskExecuter, TaskSequence, Travel, Unload, Utilize, Wait)
from PyFlow.lists import ModelList
from PyFlow.states import ElementState as S
from tests.harness import Collector, Feeder, at


def states(executer, t0=0.0):
    return [(t, s) for t, s in executer.state_log if t >= t0]


# ------------------------------------------------------------------ task sequences
def test_task_sequence_states_times_and_effects(model):
    truck = TaskExecuter("Truck", model, speed=2, location="dock", capacity=1)
    item = Item(0, item_id=7)
    delivered, called = [], []
    seq = TaskSequence([Travel("A", distance=10), Load(item, time=1), Travel("B", time=3),
                        Unload(time=1, on_done=lambda ex, task: delivered.append((model.now, task.item))),
                        Utilize(2), Wait(1), Callback(lambda ex: called.append(model.now))], name="trip")
    model.initialize()
    at(model, 1, lambda: truck.execute(seq))
    model.run(20)
    assert [s for _, s in states(truck, 1)] == [S.TRAVEL_EMPTY, S.LOADING, S.TRAVEL_LOADED, S.UNLOADING,
                                                S.WORKING, S.WAITING, S.IDLE]
    assert delivered == [(11, item)] and called == [14] and seq.finished_at == 14
    assert (truck.location, truck.distance_travelled, truck.cargo) == ("B", 10, [])
    assert (truck.sequences_completed, truck.tasks_completed) == (1, 7)
    assert truck.time_in_state(S.TRAVEL_EMPTY) == 5 and truck.time_in_state(S.TRAVEL_LOADED) == 3
    assert truck.busy.average(20) == pytest.approx(13 / 20)


def test_open_tasks_end_with_release(model):
    op = TaskExecuter("Op", model)
    model.initialize()
    op.execute(TaskSequence([Utilize(), Wait()]))
    at(model, 4, op.release)
    at(model, 6, op.release)
    model.run(10)
    assert (op.time_in_state(S.WORKING), op.time_in_state(S.WAITING), op.state) == (4, 2, S.IDLE)
    assert not op.release()                      # nothing open any more


def test_executer_errors(model):
    ex = TaskExecuter("Ex", model, capacity=1)
    model.initialize()
    ex.execute(TaskSequence([Utilize()]))
    with pytest.raises(RuntimeError, match="E_EXECUTER_BUSY"):
        ex.execute(TaskSequence([]))
    ex.release()
    ex.execute(TaskSequence([Load(Item(0)), Load(Item(0))]))
    with pytest.raises(ValueError, match="E_CARGO_FULL"):
        model.run(1)
    with pytest.raises(ValueError, match="speed"):
        TaskExecuter("Bad", model, speed=0)


def test_breakdown_pauses_the_task(model):
    ex = TaskExecuter("Ex", model)
    model.initialize()
    ex.execute(TaskSequence([Utilize(10)]))
    token = {}
    at(model, 2, lambda: token.setdefault("t", ex.stop(S.BREAKDOWN)))
    at(model, 5, lambda: ex.resume(token["t"]))
    model.run(20)
    assert ex.idle_since == 13 and ex.time_in_state(S.BREAKDOWN) == 3


def test_after_current_stop_waits_for_the_sequence(model):
    """A shift ending during a sequence: the executer finishes it, then goes off shift."""
    ex = TaskExecuter("Ex", model)
    model.initialize()
    ex.execute(TaskSequence([Utilize(5), Utilize(5)]))
    token = {}
    at(model, 3, lambda: token.setdefault("t", ex.stop(S.OFF_SHIFT, mode="after_current")))
    at(model, 15, lambda: ex.resume(token["t"]))
    model.run(20)
    assert ex.time_in_state(S.WORKING) == 10 and ex.time_in_state(S.OFF_SHIFT) == 5


# ------------------------------------------------------------------ the resource waits for work
def test_executers_serve_a_task_list(model):
    tasks = ModelList("Tasks", model)
    a, b = TaskExecuter("A", model), TaskExecuter("B", model)
    a.serve(tasks, "ORDER BY priority DESC")
    b.serve(tasks, "ORDER BY priority DESC")
    done = []

    def job(name, duration, priority):
        return TaskSequence([Utilize(duration)], name=name, priority=priority,
                            on_complete=lambda ex, seq: done.append((model.now, ex.name, seq.name)))

    model.initialize()
    assert len(tasks.backorders) == 2                     # both idle executers wait for work
    at(model, 1, lambda: tasks.push(job("j1", 4, 0)))
    at(model, 2, lambda: [tasks.push(job("j2", 4, 0)), tasks.push(job("j3", 1, 0)), tasks.push(job("urgent", 2, 9))])
    model.run(20)
    # A: j1 1-5; B takes j2 at 2 (2-6); urgent is next for whoever frees first (A at 5), then j3
    assert done == [(5, "A", "j1"), (6, "B", "j2"), (7, "A", "urgent"), (7, "B", "j3")]


def test_task_list_filters_by_executer_skills(model):
    tasks = ModelList("Tasks", model)
    welder = TaskExecuter("Welder", model, skills=["weld"])
    painter = TaskExecuter("Painter", model, skills=["paint"])
    for ex in (welder, painter):
        ex.serve(tasks, "WHERE skill in puller.skills")
    log = []
    model.initialize()
    for skill in ["paint", "weld", "paint"]:
        tasks.push(TaskSequence([Utilize(3)], labels={"skill": skill},
                                on_complete=lambda ex, seq: log.append((model.now, ex.name, seq.labels["skill"]))))
    model.run(10)
    assert log == [(3, "Painter", "paint"), (3, "Welder", "weld"), (6, "Painter", "paint")]


# ------------------------------------------------------------------ the work waits for a resource
def station(model, name, service, resources, *, start=0.0):
    feeder = Feeder(f"F_{name}", model, interval=1000, count=1, start=start)
    server = MultiServer(1, service, name, model, resources=resources)
    out = Collector(f"C_{name}", model)
    feeder.connect([server])
    server.connect([out])
    return server, out


def test_pool_units_are_operators_with_states(model):
    pool = ResourcePool("Op", model, capacity=1, kind="operator")
    unit = pool.units[0]
    assert isinstance(unit, Operator) and unit in model.elements
    _, out_a = station(model, "A", 4, [pool])
    _, out_b = station(model, "B", 4, [pool], start=1)
    model.initialize()
    assert pool.list.values == [unit]                     # idle units are published in the list
    model.run(10)
    assert out_a.times == [4] and out_b.times == [8]
    assert unit.time_in_state(S.WORKING) == 8 and unit.sequences_completed == 2
    assert pool.list.values == [unit] and pool.list.summary()["pulls"] == 0


def test_operator_breakdown_removes_it_from_the_list(model):
    pool = ResourcePool("Op", model, capacity=1)
    unit = pool.units[0]
    _, out = station(model, "A", 2, [pool], start=1)
    model.initialize()
    token = {}
    at(model, 0.5, lambda: token.setdefault("t", unit.stop(S.BREAKDOWN)))
    at(model, 3, lambda: unit.resume(token["t"]))
    model.run(10)
    assert out.times == [5]                                # served when the operator is repaired
    assert unit.time_in_state(S.BREAKDOWN) == 2.5


def test_operator_shift_from_the_spec():
    from PyFlow.spec import ModelSpec, validate_spec
    spec = ModelSpec.from_dict({
        "calendar": {"start": "2026-01-05 00:00", "seconds_per_unit": 3600},
        "resources": [{"id": "ops", "kind": "operator", "capacity": 1}],
        "elements": [{"type": "ScheduleSource", "id": "src", "jobs": [{"time": 0, "name": "J"}]},
                     {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 1, "resources": ["ops"]},
                     {"type": "Sink", "id": "snk"}],
        "connections": [{"origin": "src", "destinations": ["m"]}, {"origin": "m", "destinations": ["snk"]}],
        "downtimes": [{"type": "Shift", "targets": ["ops"], "pattern": "Mon-Fri 06:00-14:00"}]})
    assert validate_spec(spec) == []
    built = spec.build()
    results = built.run(until=10)
    # the machine waits for the operator, who starts at 06:00
    assert results["elements"]["m"]["state_ratios"]["WAITING_FOR_RESOURCE"] == pytest.approx(0.6)
    unit = results["resources"]["ops"]["units"]["ops.1"]
    assert unit["state_ratios"]["OFF_SHIFT"] == pytest.approx(0.6) and unit["sequences_completed"] == 1


def test_blocked_station_keeps_its_operator_by_default(model):
    """Default release on_exit (as SimuLean): B waits until A's item leaves at 5."""
    pool = ResourcePool("Op", model, capacity=1)
    a, out_a = station(model, "A", 2, [pool])
    _, out_b = station(model, "B", 2, [pool], start=0.5)
    out_a.close()
    model.initialize()
    at(model, 5, out_a.open)
    model.run(10)
    assert out_b.times == [7] and a.resource_release == "on_exit"


def test_waiting_request_is_granted_in_a_zero_delay_event(model):
    pool = ResourcePool("Op", model, capacity=1)
    order = []
    _, out_a = station(model, "A", 2, [pool])
    b, _ = station(model, "B", 2, [pool], start=1)
    b.on("state_changed", lambda el, old, new: order.append((model.now, new)))
    model.initialize()
    model.run(10)
    assert (2, S.PROCESSING) in order and pool.units[0].state == S.IDLE


def test_unit_in_a_pool_and_serving_a_task_list(model):
    """An operator that also takes tasks from a list when no station holds it."""
    pool = ResourcePool("Op", model, capacity=1)
    unit = pool.units[0]
    tasks = ModelList("Tasks", model)
    unit.serve(tasks)
    _, out = station(model, "A", 3, [pool])
    done = []
    model.initialize()
    at(model, 1, lambda: tasks.push(TaskSequence([Utilize(2)], on_complete=lambda ex, s: done.append(model.now))))
    model.run(10)
    assert out.times == [3] and done == [5]               # the task waits until the station frees it


def test_sink_and_executers_in_the_same_model(model):
    """Executers are elements: they appear in the model and reset with it."""
    ex = TaskExecuter("Ex", model)
    Sink("Sink", model)
    model.initialize()
    ex.execute(TaskSequence([Utilize(3)]))
    model.run(5)
    model.initialize()
    assert ex.state == S.IDLE and ex.sequences_completed == 0 and ex.current is None


def test_mtbf_on_an_operator(model):
    pool = ResourcePool("Op", model, capacity=1)
    unit = pool.units[0]
    g = MtbfMttrDowntime(unit, 100, 5, first_failure=1, busy_states=[S.WORKING], basis="calendar")
    _, out = station(model, "A", 2, [pool])
    model.initialize()
    model.run(20)
    # the operator holds the station's work 0-2 when it fails at 1: the work is not paused (it is
    # the station's), the operator is down 1-6 and back in the list afterwards
    assert out.times == [2] and g.stop_count == 1 and unit.time_in_state(S.BREAKDOWN) == 5
