"""Standard lines with constant times: results are computed by hand and must match exactly."""
import pytest

from PyFlow import QueueSizeStrategy, RoundRobinStrategy
from PyFlow.standard_lines import (Stage, assembly_line, kit_assembly, multi_product_flow_shop,
                                   order_release_line, parallel_machines, product_routing,
                                   serial_line, single_station)

# Sources emit the first item one inter-arrival time after t = 0 (items at 1, 2, 3, ...).


def test_balanced_serial_line_no_waiting():
    """All stations faster than arrivals: every item crosses in 0.5 + 0.8 + 0.6 = 1.9."""
    line = serial_line(arrival=1, stages=[Stage(0.5), Stage(0.8), Stage(0.6)], seed=1)
    r = line.run(100)
    assert r["completed"] == 98                     # arrivals k = 1..98 leave at k + 1.9 <= 100
    for i, service in enumerate((0.5, 0.8, 0.6), start=1):
        assert r["elements"][f"Q{i}"]["staytime_average"] == 0
        assert r["elements"][f"M{i}"]["staytime_average"] == pytest.approx(service)
        assert r["elements"][f"Q{i}"]["wip_average"] == 0   # items only pass through


def test_serial_line_with_bottleneck_and_finite_buffer():
    """M2 (2 s) is the bottleneck: it works non-stop from t = 2 and items leave at 5, 7, 9..."""
    line = serial_line(arrival=1, stages=[Stage(1), Stage(2, buffer=2), Stage(1)], seed=1)
    r = line.run(100)
    assert r["completed"] == 48                     # 5 + 2k <= 100
    assert r["throughput"] == pytest.approx(0.48)
    assert r["elements"]["M2"]["utilization"] == pytest.approx(0.98)
    assert r["elements"]["Q2"]["wip_max"] == 2      # finite buffer is full, M1 gets blocked ...
    assert r["elements"]["Q1"]["wip_max"] > 40      # ... and the work piles up in front of it


def test_serial_line_blocking_limits_wip():
    """Buffers of 1 before a slow station keep the WIP of the whole line bounded."""
    line = serial_line(arrival=1, stages=[Stage(1, buffer=1), Stage(3, buffer=1)], seed=1)
    r = line.run(300)
    assert r["elements"]["Q2"]["wip_max"] <= 1
    assert r["elements"]["M1"]["wip_max"] <= 1
    assert r["throughput"] == pytest.approx(1 / 3, abs=0.01)


def test_single_station_multiserver():
    """3 servers of 2.5 s with arrivals every 1 s: no queue, every stay is 2.5."""
    r = single_station(arrival=1, service=2.5, servers=3, seed=1).run(100)
    assert r["completed"] == 97                     # k + 2.5 <= 100
    assert r["elements"]["Q1"]["wip_average"] == 0
    assert r["elements"]["M1"]["staytime_average"] == pytest.approx(2.5)


def test_parallel_machines_round_robin():
    r = parallel_machines(arrival=1, services=[2.5, 2.5, 2.5], strategy=RoundRobinStrategy(), seed=1).run(100)
    assert r["completed"] == 97
    assert [r["elements"][f"M{i}"]["output"] for i in (1, 2, 3)] == [33, 32, 32]


def test_parallel_machines_first_available_prefers_first():
    r = parallel_machines(arrival=1, services=[0.5, 0.5], seed=1).run(10)
    assert r["elements"]["M1"]["output"] == 9       # M1 is free again before each arrival (10th ends at 10.5)
    assert r["elements"]["M2"]["output"] == 0


def test_parallel_machines_shortest_queue_with_different_speeds():
    """Unequal machines: the fast one takes more work, both are used."""
    r = parallel_machines(arrival=1, services=[1.5, 3.0], strategy=QueueSizeStrategy(), seed=1).run(300)
    m1, m2 = r["elements"]["M1"]["output"], r["elements"]["M2"]["output"]
    assert m1 > m2 > 0
    assert r["elements"]["Q1"]["wip_max"] <= 1     # capacity 1/1.5 + 1/3 = 1 item/s


def test_assembly_line_with_combiner():
    """Main parts every 2 s, components every 1 s, 2 components per unit, 1.5 s assembly:
    units leave at 3.5, 5.5, ... and each carries its 2 components."""
    line = assembly_line(main_arrival=2, component_arrival=1, components_per_unit=2,
                         assembly_time=1.5, seed=1)
    done = []
    line["Sink"].on("item_entered", lambda e, item: done.append(item))
    r = line.run(100)
    assert r["completed"] == 49                     # 3.5 + 2k <= 100
    assert r["elements"]["Q_comp"]["wip_max"] <= 2  # supply and demand are balanced
    assert len(done) == 49
    for item in done:
        assert len(item.get_sub_items()) == 2


def test_assembly_line_component_shortage():
    """Components every 3 s, 2 per unit: the assembly is starved (one unit every 6 s)."""
    r = assembly_line(main_arrival=2, component_arrival=3, components_per_unit=2,
                      assembly_time=1, seed=1).run(120)
    assert r["completed"] == 19                     # 2nd component at 6k -> leaves at 6k + 1
    assert r["elements"]["Q_main"]["wip_max"] > 10  # main parts pile up


def test_kit_assembly():
    r = kit_assembly(arrivals=[2, 1], requirements=[1, 2], assembly_time=1.5, seed=1).run(100)
    assert r["completed"] == 49
    # Kits are assembled 2-3.5, 4-5.5, ...: busy 1.5 of every 2 s, 49 kits done by t=100
    assert r["elements"]["Assembly"]["utilization"] * 100 == pytest.approx(49 * 1.5)
    assert r["elements"]["Assembly"]["staytime_average"] == pytest.approx(1.5)


def test_multi_product_flow_shop():
    """A, B, C arrive together every 10 s; PT1 = 2/3/4 and PT2 = 3/2/1.
    Per cycle M1 works 10-12, 12-15, 15-19 and M2 12-15, 15-17, 19-20."""
    products = {"A": {"arrival": 10, "PT1": 2, "PT2": 3},
                "B": {"arrival": 10, "PT1": 3, "PT2": 2},
                "C": {"arrival": 10, "PT1": 4, "PT2": 1}}
    line = multi_product_flow_shop(products=products, stations=2, seed=1)
    r = line.run(98)
    assert r["completed"] == 26                     # 8 full cycles + A and B of the 9th
    assert r["elements"]["M1"]["utilization"] * 98 == pytest.approx(80)
    assert r["elements"]["M2"]["utilization"] * 98 == pytest.approx(53)
    assert line["Sink"].type_counts == {"A": 9, "B": 9, "C": 8}


def test_product_routing_by_label():
    products = {"A": {"arrival": 5, "route": 0, "PT": 4},
                "B": {"arrival": 5, "route": 1, "PT": 3}}
    line = product_routing(products=products, seed=1)
    r = line.run(100)
    assert r["elements"]["M1"]["output"] == 19      # A leaves at 9, 14, ..., 99
    assert r["elements"]["M2"]["output"] == 19      # B leaves at 8, 13, ..., 98
    assert line["Sink"].type_counts == {"A": 19, "B": 19}


def test_order_release_from_table():
    """t=0: 2 x A (PT 3); t=5: 1 x B (PT 4) and 3 x C (PT 1) on one machine.
    A 0-3, 3-6; B 6-10; C 10-11, 11-12, 12-13."""
    orders = {"Time": [0, 5, 5], "Name": ["A", "B", "C"], "Q": [2, 1, 3], "PT": [3, 4, 1]}
    line = order_release_line(orders=orders, stages=[Stage("PT")], seed=1)
    r = line.run(50)
    assert r["completed"] == 6
    assert line.model.clock.last_event_time == 13
    assert r["elements"]["M1"]["utilization"] * 50 == pytest.approx(13)


def test_line_run_is_repeatable():
    line = serial_line(arrival="Exponential~1", stages=[Stage("ExponentialMean~0.8", buffer=3)], seed=5)
    assert line.run(500) == line.run(500)


def test_stage_with_breakdowns_setup_and_states():
    """Stage options create the generators; every station reports its state ratios."""
    from PyFlow import MtbfMttrDowntime
    line = serial_line(arrival=1, stages=[Stage(0.5, ttf=20, ttr=5), Stage(0.5, setup=1)], seed=1)
    r = line.run(100)
    gens = [g for g in line.model.generators if isinstance(g, MtbfMttrDowntime)]
    assert len(gens) == 1 and gens[0].target is line["M1"]
    states = r["elements"]["M1"]["states"]
    assert states["BREAKDOWN"] == pytest.approx(20 / 100)   # failures at 20, 45, 70, 95 (5 + 5 + 5 + 5)
    assert sum(states.values()) == pytest.approx(1)
    with pytest.raises(ValueError, match="E_INVALID_STAGE"):
        serial_line(arrival=1, stages=[Stage(1, ttf=5)], seed=1)
