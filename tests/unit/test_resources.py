"""Shared resources (operators, robots, tools...): deterministic cases computed by hand."""
import pytest

from PyFlow import (Combiner, InfiniteSource, ItemsQueue, Model, MultiAssembler, MultiServer, ResourcePool,
                    ResourceRequirement, Sink)
from PyFlow.states import ElementState
from tests.harness import Collector, Feeder, at

WAIT = ElementState.WAITING_FOR_RESOURCE


def station(model, name, service, resources, *, feed=1, start=0.0, priority=0, release="on_finish", **kw):
    """Feeder(feed items) -> MultiServer -> Collector."""
    feeder = Feeder(f"F_{name}", model, interval=1000, count=feed, start=start, priority=priority, **kw)
    server = MultiServer(1, service, name, model, resources=resources, resource_release=release)
    out = Collector(f"C_{name}", model)
    feeder.connect([server])
    server.connect([out])
    return server, out


def run(model, until):
    model.initialize()
    model.run(until)


# ------------------------------------------------------------------ basic sharing
def test_one_operator_serializes_two_machines(model):
    op = ResourcePool("Op", model, capacity=1, kind="operator")
    a, out_a = station(model, "A", 4, [op])
    b, out_b = station(model, "B", 4, [op])
    run(model, 10)
    assert out_a.times == [4] and out_b.times == [8]
    assert b.time_in_state(WAIT) == 4 and a.time_in_state(WAIT) == 0
    assert op.utilization() == pytest.approx(0.8)
    assert (op.requests, op.grants, op.wait_total, op.wait_max) == (2, 2, 4, 4)


def test_two_units_serve_in_parallel(model):
    op = ResourcePool("Op", model, capacity=2)
    _, out_a = station(model, "A", 4, [op])
    _, out_b = station(model, "B", 4, [op])
    run(model, 10)
    assert out_a.times == [4] and out_b.times == [4]
    assert op.unit_utilization() == {"Op.1": pytest.approx(0.4), "Op.2": pytest.approx(0.4)}


def test_pool_alone_means_one_unit_for_the_whole_service(model):
    op = ResourcePool("Op", model, capacity=1)
    server, _ = station(model, "A", 2, [op])
    assert [(r.pool, r.quantity, r.during, r.skill) for r in server.resource_requirements] == [(op, 1, "both", None)]


# ------------------------------------------------------------------ release policy
@pytest.mark.parametrize("release, b_done, a_op_busy", [("on_finish", 4, 2), ("on_exit", 7, 5)])
def test_release_on_finish_or_on_exit_when_blocked(model, release, b_done, a_op_busy):
    """A (2 s) finishes at 2 but its output is closed until t=5; B (2 s) waits for the operator."""
    op = ResourcePool("Op", model, capacity=1)
    a, out_a = station(model, "A", 2, [op], release=release)
    _, out_b = station(model, "B", 2, [op], start=0.5)
    out_a.close()
    model.initialize()
    at(model, 5, out_a.open)
    model.run(10)
    assert out_a.times == [5]
    assert out_b.times == [b_done]
    assert op.units[0].busy.average(10) * 10 == pytest.approx(a_op_busy + 2)


# ------------------------------------------------------------------ phases
def test_setup_and_processing_resources(model):
    """Types A then B: no setup for A, 3 s setup for B (technician), 1 s processing (robot)."""
    tech = ResourcePool("Tech", model, capacity=1)
    robot = ResourcePool("Robot", model, capacity=1)
    feeder = Feeder("F", model, interval=0, count=1, item_type="A")
    feeder_b = Feeder("FB", model, interval=0, count=1, item_type="B", start=0.5)
    queue = ItemsQueue(5, "Q", model)
    server = MultiServer(1, 1, "M", model, setup_time={"B": 3},
                         resources=[ResourceRequirement(tech, during="setup"),
                                    ResourceRequirement(robot, during="processing")])
    out = Collector("Out", model)
    feeder.connect([queue])
    feeder_b.connect([queue])
    queue.connect([server])
    server.connect([out])
    run(model, 10)
    # A: 0-1 processing; B: setup 1-4 (tech), processing 4-5 (robot)
    assert out.times == [1, 5]
    assert tech.busy.average(10) * 10 == pytest.approx(3)
    assert robot.busy.average(10) * 10 == pytest.approx(2)
    assert server.time_in_state(ElementState.SETUP) == 3


def test_both_phases_hold_the_unit_from_setup_to_end(model):
    """M: A 0-1, then B with setup 1-3 and processing 3-4, holding the operator throughout.
    C asks for the operator at t=3 (end of B's setup) and must wait until 4."""
    op = ResourcePool("Op", model, capacity=1)
    fa = Feeder("FA", model, interval=0, count=1, item_type="A")
    fb = Feeder("FB", model, interval=0, count=1, item_type="B", start=0.5)
    q = ItemsQueue(5, "Q", model)
    m = MultiServer(1, 1, "M", model, setup_time=2, resources=[op])
    out = Collector("Out", model)
    fa.connect([q])
    fb.connect([q])
    q.connect([m])
    m.connect([out])
    _, out_c = station(model, "C", 2, [op], start=3)
    run(model, 10)
    assert out.times == [1, 4]
    assert out_c.times == [6]
    assert op.busy.average(10) * 10 == pytest.approx(6)


# ------------------------------------------------------------------ allocation rules
def test_all_or_nothing_across_pools(model):
    """B needs operator AND robot. While the operator is busy, B holds nothing, so C can use the robot."""
    op = ResourcePool("Op", model, capacity=1)
    robot = ResourcePool("Robot", model, capacity=1, kind="robot")
    _, out_a = station(model, "A", 5, [op])
    _, out_b = station(model, "B", 1, [op, robot], start=0.1)
    _, out_c = station(model, "C", 2, [robot], start=1)
    run(model, 10)
    assert out_a.times == [5]
    assert out_c.times == [3]          # robot free at t=1: B did not keep it while waiting
    assert out_b.times == [6]          # operator free at 5, robot free since 3


def test_priority_then_request_order(model):
    op = ResourcePool("Op", model, capacity=1)
    _, out0 = station(model, "M0", 2, [op])
    _, out1 = station(model, "M1", 2, [op], start=0.1)
    _, out2 = station(model, "M2", 2, [op], start=0.2, priority=5)
    run(model, 10)
    assert (out0.times, out2.times, out1.times) == ([2], [4], [6])


def test_small_request_is_not_blocked_by_a_big_one(model):
    op = ResourcePool("Op", model, capacity=2)
    _, out_a = station(model, "A", 4, [op])
    _, out_big = station(model, "Big", 1, [ResourceRequirement(op, 2)], start=0.1)
    _, out_small = station(model, "Small", 1, [op], start=0.2)
    run(model, 10)
    assert out_small.times == [1.2]     # one unit was free: served although Big waits
    assert out_big.times == [5]


def test_skills_and_least_versatile_unit_first(model):
    robots = ResourcePool("Robots", model, units=[{"name": "R1", "skills": ["weld", "paint"]},
                                                  {"name": "R2", "skills": ["paint"]}])
    _, out_p = station(model, "Paint", 3, [ResourceRequirement(robots, skill="paint")])
    _, out_w = station(model, "Weld", 3, [ResourceRequirement(robots, skill="weld")], start=0.1)
    run(model, 10)
    # Paint takes R2 (fewer skills), so the welder R1 is free for Weld
    assert out_p.times == [3] and out_w.times == [3.1]
    assert robots.unit_utilization(10) == {"R1": pytest.approx(0.3), "R2": pytest.approx(0.3)}


def test_impossible_requests_are_rejected(model):
    robots = ResourcePool("Robots", model, units=[{"name": "R1", "skills": ["paint"]}])
    with pytest.raises(ValueError, match="E_RESOURCE_INSUFFICIENT"):
        ResourceRequirement(robots, 2)
    with pytest.raises(ValueError, match="skill 'weld'"):
        ResourceRequirement(robots, skill="weld")
    with pytest.raises(ValueError, match="during"):
        ResourceRequirement(robots, during="always")
    with pytest.raises(ValueError, match="exactly one of 'capacity' or 'units'"):
        ResourcePool("X", model)
    with pytest.raises(ValueError, match="E_DUPLICATE_RESOURCE"):
        ResourcePool("Robots", model, capacity=1)
    with pytest.raises(ValueError, match="another model"):
        MultiServer(1, 1, "M", Model(seed=2), resources=[robots])
    with pytest.raises(ValueError, match="needs 2 unit"):
        MultiServer(1, 1, "M3", model, resources=[robots, ResourceRequirement(robots, during="processing")])
    with pytest.raises(ValueError, match="resource_release"):
        MultiServer(1, 1, "M2", model, resources=[robots], resource_release="never")


# ------------------------------------------------------------------ other elements
def test_combiner_waits_for_the_operator(model):
    op = ResourcePool("Op", model, capacity=1)
    _, out_m = station(model, "M", 3, [op])
    main = Feeder("Main", model, interval=1000, count=1)
    parts = Feeder("Parts", model, interval=0, count=2)
    comb = Combiner([2], 2, "Comb", model, resources=[op])
    out_c = Collector("C_Comb", model)
    main.connect([comb])
    parts.connect([comb.get_component_input(0)])
    comb.connect([out_c])
    run(model, 10)
    assert out_m.times == [3]
    assert out_c.times == [5]                   # components ready at 0, operator free at 3
    assert comb.time_in_state(WAIT) == 3


def test_multiassembler_servers_share_one_operator(model):
    op = ResourcePool("Op", model, capacity=1)
    a = Feeder("A", model, interval=0, count=2)
    b = Feeder("B", model, interval=0, count=2)
    asm = MultiAssembler(2, [1, 1], 4, "Asm", model, resources=[op])
    out = Collector("Out", model)
    a.connect([asm.get_component_input(0)])
    b.connect([asm.get_component_input(1)])
    asm.connect([out])
    run(model, 20)
    assert out.times == [4, 8]                  # two servers, but one operator


# ------------------------------------------------------------------ interaction with stops and runs
def test_units_granted_while_stopped_wait_for_the_resume(model):
    op = ResourcePool("Op", model, capacity=1)
    _, out_a = station(model, "A", 3, [op])
    b, out_b = station(model, "B", 2, [op], start=0.5)
    model.initialize()
    token = {}
    at(model, 1, lambda: token.setdefault("t", b.stop(ElementState.BREAKDOWN)))
    at(model, 6, lambda: b.resume(token["t"]))
    model.run(10)
    # granted at 3 (A done), but B is down until 6: works 6-8, holding the operator 3-8
    assert out_a.times == [3] and out_b.times == [8]
    assert op.busy.average(10) * 10 == pytest.approx(8)


def test_warmup_resets_pool_statistics_and_reinitialize_starts_over(model):
    op = ResourcePool("Op", model, capacity=1)
    station(model, "A", 4, [op])
    station(model, "B", 4, [op])
    model.initialize()
    model.run(10, warmup=6)                      # op busy 0-8: 2 of the last 4 units of time
    assert op.utilization() == pytest.approx(0.5)
    assert op.requests == 0 and op.wait_count == 0
    model.initialize()
    model.run(10)
    assert op.utilization() == pytest.approx(0.8) and op.requests == 2


# ------------------------------------------------------------------ stochastic equivalence
def test_shared_pool_is_equivalent_to_fewer_servers():
    """queue -> MultiServer(5 slots) needing 1 of 2 units == queue -> MultiServer(2): same departures."""
    def line(slots, pool_units):
        model = Model(seed=9)
        src = Feeder("Src", model, interval=0.45, count=400)
        q = ItemsQueue(10_000, "Q", model)
        resources = [ResourcePool("Op", model, capacity=pool_units)] if pool_units else None
        server = MultiServer(slots, "ExponentialMean~0.8", "Server", model, resources=resources)
        out = Collector("Out", model)
        src.connect([q])
        q.connect([server])
        server.connect([out])
        model.initialize()
        model.run(1000)
        return out.times

    plain = line(2, None)
    pooled = line(5, 2)
    assert len(plain) == 400 and pooled == pytest.approx(plain, abs=1e-9)


def test_infinite_source_and_sink_with_pool(model):
    """Saturated 3-slot machine with one operator: throughput = 1 / service. The other slots
    hold items waiting for the operator, but the visible state is PROCESSING (it has priority)."""
    op = ResourcePool("Op", model, capacity=1)
    src = InfiniteSource("Src", model)
    m = MultiServer(3, 2, "M", model, resources=[op])
    sink = Sink("Sink", model)
    src.connect([m])
    m.connect([sink])
    run(model, 100)
    assert sink.get_stats_collector().get_var_input_value() == 50
    assert m.state_ratio(ElementState.PROCESSING) == 1.0
    assert m.get_queue_length() == 3 and op.queue.value == 2
