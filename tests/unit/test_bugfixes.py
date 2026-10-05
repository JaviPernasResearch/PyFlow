"""Regression tests for the Phase 0.4 bugs."""
import pytest

from PyFlow import (Combiner, InterArrivalBufferingSource, Item, ItemsQueue, MultiAssembler,
                    MultiServer, QueueSizeStrategy)
from tests.harness import Collector, Feeder, at


def test_multiserver_unblock_keeps_process_when_still_blocked(model):
    feeder = Feeder("Feeder", model, interval=100, count=2)
    server = MultiServer(1, 1, "Server", model)
    sink = Collector("Sink", model)
    feeder.connect([server])
    server.connect([sink])
    sink.close()
    model.initialize()
    model.run(5)
    assert len(server.completed) == 1
    # A spurious unblock while the sink is still closed must not lose the process
    assert server.unblock() is False
    assert len(server.completed) == 1
    sink.open()
    model.run(200)
    assert sink.times == [5.0, 101.0]
    assert len(server.idle_processes) == 1


def test_buffering_source_keeps_generating_and_sends_fifo(model):
    source = InterArrivalBufferingSource("Source", model, 1.0)
    sink = Collector("Sink", model)
    source.connect([sink])
    sink.close()
    model.initialize()
    at(model, 5.5, sink.open)
    model.run(8)
    # Arrivals at t=1..5 are buffered, released at 5.5 in arrival order; 6,7,8 go straight
    assert sink.ids == [1, 2, 3, 4, 5, 6, 7, 8]
    assert sink.times == [5.5] * 5 + [6.0, 7.0, 8.0]
    assert source.get_buffer_length() == 0


def test_items_queue_never_drops_items_and_unblock_returns_bool(model):
    feeder = Feeder("Feeder", model, interval=1, count=6)
    queue = ItemsQueue(3, "Queue", model)
    sink = Collector("Sink", model)
    feeder.connect([queue])
    queue.connect([sink])
    sink.close()
    model.initialize()
    model.run(10)
    assert queue.current_items == len(queue.items_q) == 3
    assert queue.unblock() is False                 # destination still closed
    assert [i.item_number for i in queue.items_q] == [1, 2, 3]  # order preserved
    assert queue.unblock() is False
    sink.open()
    model.run(20)
    assert sink.ids == [1, 2, 3, 4, 5, 6]
    assert queue.unblock() is False                 # empty


def test_items_queue_accepts_infinite_capacity(model):
    queue = ItemsQueue(float("inf"), "Queue", model)
    feeder = Feeder("Feeder", model, interval=1, count=3)
    sink = Collector("Sink", model)
    feeder.connect([queue])
    queue.connect([sink])
    sink.close()
    model.initialize()
    model.run(5)
    assert queue.current_items == 3


def test_queue_size_strategy_tries_other_destinations(model):
    feeder = Feeder("Feeder", model, interval=1, count=3)
    empty_but_closed = Collector("Closed", model)
    busy = ItemsQueue(10, "Busy", model)
    feeder.connect([empty_but_closed, busy], strategy=QueueSizeStrategy())
    sink = Collector("Sink", model)
    busy.connect([sink])
    empty_but_closed.close()
    model.initialize()
    model.run(5)
    assert sink.ids == [1, 2, 3]


def test_queue_size_strategy_picks_shortest(model):
    feeder = Feeder("Feeder", model, interval=1, count=4)
    q1 = ItemsQueue(10, "Q1", model)
    q2 = ItemsQueue(10, "Q2", model)
    s1 = Collector("S1", model)
    s2 = Collector("S2", model)
    feeder.connect([q1, q2], strategy=QueueSizeStrategy())
    q1.connect([s1])
    q2.connect([s2])
    s1.close()
    s2.close()
    model.initialize()
    model.run(5)
    assert [i.item_number for i in q1.items_q] == [1, 3]
    assert [i.item_number for i in q2.items_q] == [2, 4]


def test_combiner_batch_mode_attaches_components(model):
    main = Feeder("Main", model, interval=10, count=2)
    comps = Feeder("Comps", model, interval=1, count=6, item_type="Comp")
    combiner = Combiner([3], 2, "Combiner", model, batch_mode=True)
    sink = Collector("Sink", model)
    main.connect([combiner])
    comps.connect([combiner.get_component_input(0)])
    combiner.connect([sink])
    model.initialize()
    model.run(50)
    assert len(sink.received) == 2
    for _, item in sink.received:
        assert [c.type for c in item.get_sub_items()] == ["Comp"] * 3


def test_multiassembler_batch_mode_attaches_components(model):
    a = Feeder("A", model, interval=1, count=2, item_type="A")
    b = Feeder("B", model, interval=1, count=4, item_type="B")
    assembler = MultiAssembler(1, [1, 2], 1, "Assembler", model, batch_mode=True)
    sink = Collector("Sink", model)
    a.connect([assembler.get_component_input(0)])
    b.connect([assembler.get_component_input(1)])
    assembler.connect([sink])
    model.initialize()
    model.run(20)
    assert len(sink.received) == 2
    for _, item in sink.received:
        assert sorted(c.type for c in item.get_sub_items()) == ["A", "B", "B"]


def test_item_add_item():
    parent = Item(0, item_id=1)
    child = Item(0, item_id=2)
    parent.add_item(child)
    assert parent.get_sub_items() == [child]
