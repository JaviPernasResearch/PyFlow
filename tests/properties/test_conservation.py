"""Invariants on random serial lines: source -> (queue -> server) x k -> sink.

Topologies and parameters are drawn from a seeded generator, so the cases are random
but reproducible (no external property-testing library)."""
import numpy as np
import pytest

from PyFlow import InterArrivalSource, ItemsQueue, Model, MultiServer, Sink

CASES = 40


def random_line(case: int):
    rng = np.random.default_rng(case)
    stages = [(int(rng.integers(1, 6)), int(rng.integers(1, 4)), float(rng.uniform(0.2, 3.0)))
              for _ in range(int(rng.integers(1, 5)))]
    return int(rng.integers(0, 2**32)), stages, float(rng.uniform(0.2, 3.0)), float(rng.uniform(10, 200))


@pytest.mark.parametrize("case", range(CASES))
def test_items_are_conserved_and_bounded(case):
    seed, stages, rate, horizon = random_line(case)
    m = Model(seed=seed)
    source = InterArrivalSource("Source", m, f"Exponential~{rate}")
    prev, buffers = source, []
    for i, (cap, servers, mean) in enumerate(stages):
        q = ItemsQueue(cap, f"Q{i}", m)
        s = MultiServer(servers, f"ExponentialMean~{mean}", f"S{i}", m)
        prev.connect([q])
        q.connect([s])
        prev = s
        buffers += [(q, cap), (s, servers)]
    sink = Sink("Sink", m)
    prev.connect([sink])

    m.initialize()
    times = []
    for t in (horizon / 3, 2 * horizon / 3, horizon):
        m.run(t)
        times.append(m.now)
        wip = 0
        for element, capacity in buffers:
            content = element.get_stats_collector().get_var_content_value()
            assert 0 <= content <= capacity
            wip += content
        held = 1 if source.last_item is not None else 0
        done = sink.get_stats_collector().get_var_input_value()
        assert m.items_created == done + wip + held
    assert times == sorted(times)
