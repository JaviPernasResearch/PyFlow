"""Many-to-one, one-to-many and many-to-many connections (deterministic)."""
from PyFlow import Element, InfiniteSource, InterArrivalSource, ItemsQueue, MultiServer, Sink


def count(element):
    return element.get_stats_collector().get_var_output_value()


def received(sink):
    return sink.get_stats_collector().get_var_input_value()


def test_two_sources_into_one_queue(model):
    s1 = InterArrivalSource("S1", model, 2)
    s2 = InterArrivalSource("S2", model, 2)
    queue = ItemsQueue(100_000, "Q", model)
    server = MultiServer(1, 2, "M", model)
    sink = Sink("Sink", model)
    Element.connect_multiple([s1, s2], [queue])
    queue.connect([server])
    server.connect([sink])
    model.initialize()
    model.run(100)
    # 2 items every 2 s but the server only does 1 per 2 s: leaves at 4, 6, ..., 100
    assert received(sink) == 49
    assert count(s1) == count(s2) == 50


def test_one_source_into_two_queues_first_available(model):
    source = InterArrivalSource("S", model, 2)
    q1 = ItemsQueue(3, "Q1", model)
    q2 = ItemsQueue(3, "Q2", model)
    server = MultiServer(1, 2, "M", model)
    sink = Sink("Sink", model)
    source.connect([q1, q2])
    q1.connect([server])
    q2.connect([server])
    server.connect([sink])
    model.initialize()
    model.run(100)
    assert (count(q1), count(q2), received(sink)) == (50, 0, 49)


def test_two_infinite_sources_into_two_queues(model):
    s1 = InfiniteSource("S1", model)
    s2 = InfiniteSource("S2", model)
    q1 = ItemsQueue(3, "Q1", model)
    q2 = ItemsQueue(3, "Q2", model)
    m1 = MultiServer(1, 20, "M1", model)
    m2 = MultiServer(1, 10, "M2", model)
    sink = Sink("Sink", model)
    Element.connect_multiple([s1, s2], [q1, q2])
    q1.connect([m1])
    q2.connect([m2])
    m1.connect([sink])
    m2.connect([sink])
    model.initialize()
    model.run(100)
    # Machine bound: M1 starts at 0, 20, ..., 100 and M2 at 0, 10, ..., 100
    assert (count(q1), count(q2), received(sink)) == (6, 11, 15)
