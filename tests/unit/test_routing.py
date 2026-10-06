"""Output and input strategies, links and element audit fixes (deterministic)."""
import pytest

from PyFlow import (CompositeAndInputStrategy, CompositeOrInputStrategy, DelegateOutputStrategy, InfiniteSource,
                    ItemsQueue, LabelRoutingStrategy, MaxQueueInputStrategy, MostAvailableCapacityStrategy,
                    MultiAssembler, MultiServer, OriginNameInputStrategy, OriginTypeInputStrategy,
                    ParameterizedRoutingStrategy, PriorityRoutingStrategy, RoundRobinStrategy, ScheduleSource,
                    SingleLabelStrategy, Sink)
from tests.harness import Collector, Feeder


def fan_out(model, strategy, n=3, count=6, capacity=10, **feeder_kw):
    feeder = Feeder("Feeder", model, interval=1, count=count, **feeder_kw)
    queues = [ItemsQueue(capacity, f"Q{i}", model) for i in range(n)]
    sinks = [Collector(f"S{i}", model) for i in range(n)]
    feeder.connect(queues, strategy=strategy)
    for q, s in zip(queues, sinks):
        q.connect([s])
        s.close()
    return feeder, queues, sinks


def held(queues):
    return [[i.item_number for i in q.items_q] for q in queues]


# ------------------------------------------------------------------ output strategies
def test_most_available_capacity(model):
    feeder, queues, _ = fan_out(model, MostAvailableCapacityStrategy(), n=2, count=5)
    queues[0].capacity, queues[1].capacity = 2, 3
    model.initialize()
    model.run(10)
    # free 2/3 -> Q1, 2/2 -> Q0 (tie: lowest index), 1/2 -> Q1, 1/1 -> Q0, 0/1 -> Q1
    assert held(queues) == [[2, 4], [1, 3, 5]]


def test_label_routing_with_map_and_default(model):
    feeder, queues, _ = fan_out(model, LabelRoutingStrategy("product", {"A": 2, "B": 0}, default_index=1), count=1)
    model.initialize()
    for product, expected in (("A", 2), ("B", 0), ("C", 1)):
        item = feeder._new_item(labels={"product": product})
        assert feeder.get_output().send(item)
        assert item in queues[expected].items_q


def test_label_routing_waits_instead_of_falling_back(model):
    feeder, queues, _ = fan_out(model, LabelRoutingStrategy("product", {"A": 0}), n=2, count=3,
                                capacity=1, labels={"product": "A"})
    model.initialize()
    model.run(10)
    assert held(queues) == [[1], []]
    assert len(feeder.held) == 2


def test_priority_routing(model):
    feeder, queues, _ = fan_out(model, PriorityRoutingStrategy(), n=2, count=1)
    model.initialize()
    queues[0].items_q.extend([object()] * 0)
    low = feeder._new_item()
    feeder.get_output().send(feeder._new_item())          # Q0 now holds 1
    feeder.get_output().send(low)                         # shortest queue -> Q1
    urgent = feeder._new_item()
    urgent.priority = 1
    feeder.get_output().send(urgent)                      # first available -> Q0
    assert low in queues[1].items_q and urgent in queues[0].items_q


def test_parameterized_routing_follows_model_parameters(model):
    feeder, queues, _ = fan_out(model, ParameterizedRoutingStrategy("route"), count=6)
    model.parameters["route"] = "round_robin"
    model.initialize()
    model.run(10)
    assert held(queues) == [[1, 4], [2, 5], [3, 6]]       # rotates (SimuLean never rotates here)
    model.parameters["route"] = 2
    model.initialize()
    model.run(10)
    assert held(queues) == [[], [], [1, 2, 3, 4, 5, 6]]


def test_delegate_strategy(model):
    choose_last = DelegateOutputStrategy(lambda outputs, item, source: len(outputs) - 1)
    feeder, queues, _ = fan_out(model, choose_last, count=2)
    model.initialize()
    model.run(5)
    assert held(queues) == [[], [], [1, 2]]


def test_round_robin_per_origin_when_connected_together(model):
    from PyFlow import Element
    f1 = Feeder("F1", model, interval=1, count=2)
    f2 = Feeder("F2", model, interval=1, count=2, start=0.5)
    q1, q2 = ItemsQueue(10, "Q1", model), ItemsQueue(10, "Q2", model)
    Element.connect_multiple([f1, f2], [q1, q2], strategy=RoundRobinStrategy())
    for q in (q1, q2):
        s = Collector(f"S_{q.name}", model)
        q.connect([s])
        s.close()
    model.initialize()
    model.run(5)
    assert f1.output_strategy is not f2.output_strategy
    assert sorted(i.item_number for i in q1.items_q) == [1, 2]   # each origin starts at Q1


# ------------------------------------------------------------------ input strategies
def test_output_strategy_skips_destinations_refused_by_input_strategy(model):
    """SimuLean bug: the input strategy is checked after the destination is chosen, so the
    item waits although another destination accepts it. Here Q0 refuses, Q1 takes it."""
    feeder, queues, _ = fan_out(model, None, n=2, count=2)
    queues[0].set_input_strategy(OriginNameInputStrategy("Somebody else"))
    model.initialize()
    model.run(5)
    assert held(queues) == [[], [1, 2]]


def test_origin_strategies(model):
    a = Feeder("A", model, interval=1, count=2)
    b = Feeder("B", model, interval=1, count=2)
    queue = ItemsQueue(10, "Q", model)
    queue.set_input_strategy(CompositeOrInputStrategy(OriginNameInputStrategy("A"),
                                                      OriginTypeInputStrategy("MultiServer")))
    sink = Collector("S", model)
    a.connect([queue])
    b.connect([queue])
    queue.connect([sink])
    model.initialize()
    model.run(5)
    assert sorted(i.item_number for _, i in sink.received) == [1, 3]   # only A's items
    assert len(b.held) == 2


def test_max_queue_input_strategy_is_enforced(model):
    """SimuLean never calls InputStrategy.CanAccept, so MaxQueue has no effect there."""
    feeder, queues, _ = fan_out(model, None, n=2, count=5)
    queues[0].set_input_strategy(CompositeAndInputStrategy(MaxQueueInputStrategy(2)))
    model.initialize()
    model.run(10)
    assert held(queues) == [[1, 2], [3, 4, 5]]


def test_single_label_strategy_on_any_element(model):
    feeder, queues, _ = fan_out(model, None, n=1, count=1)
    strategy = SingleLabelStrategy("lot", "L1")
    queues[0].set_input_strategy(strategy)
    model.initialize()
    ok, bad = feeder._new_item(labels={"lot": "L1"}), feeder._new_item(labels={"lot": "L2"})
    assert queues[0].can_accept(ok) and not queues[0].can_accept(bad)


# ------------------------------------------------------------------ links and audit fixes
def test_refused_receive_rolls_back_statistics(model, caplog):
    class Liar(Collector):
        def receive(self, the_item):
            return False

    feeder = Feeder("F", model, interval=1, count=1)
    liar = Liar("Liar", model)
    feeder.connect([liar])
    model.initialize()
    model.run(2)
    sc = liar.get_stats_collector()
    assert sc.get_var_input_value() == 0 and sc.get_var_content_value() == 0
    assert feeder.get_stats_collector().get_var_output_value() == 0
    assert len(feeder.held) == 1 and "E_RECEIVE_REFUSED" in caplog.text


def test_multiassembler_refuses_direct_connection(model):
    feeder = Feeder("F", model, interval=1, count=2)
    assembler = MultiAssembler(1, [1], 1, "Asm", model)
    feeder.connect([assembler])
    model.initialize()
    model.run(5)
    assert len(feeder.held) == 2       # items are not swallowed


def test_infinite_source_never_loses_items(model):
    source = InfiniteSource("Src", model)
    server = MultiServer(1, 1, "M", model)
    sink = Sink("Sink", model)
    source.connect([server])
    server.connect([sink])
    model.initialize()
    model.run(10)
    created = source.number_items
    assert created == sink.number_items + server.current_items + 1   # +1 waiting at the source
    assert source.get_queue_length() == 1


def test_sink_forgets_items_and_counts_types(model):
    feeder = Feeder("F", model, interval=1, count=3, item_type="T")
    sink = Sink("Sink", model)
    feeder.connect([sink])
    model.initialize()
    model.run(5)
    sc = sink.get_stats_collector()
    assert sc.entry_times == {} and sc.get_var_content_value() == 0
    assert sink.number_items == sc.get_var_input_value() == 3 and sink.type_counts == {"T": 3}
    assert sink.unblock() is False


def test_schedule_source_replays_on_reinitialize(model):
    source = ScheduleSource("Orders", model, file_name="Data/model_scheduleSource.csv")
    sink = Sink("Sink", model)
    source.connect([sink])
    for _ in range(2):
        model.initialize()
        model.run(10)
        assert sink.number_items == 4 and source.number_items == 4


def test_component_ports_record_consumption(model):
    from PyFlow import Combiner
    main = Feeder("Main", model, interval=10, count=2)
    comps = Feeder("Comps", model, interval=1, count=4)
    combiner = Combiner([2], 1, "C", model)
    sink = Sink("Sink", model)
    main.connect([combiner])
    comps.connect([combiner.get_component_input(0)])
    combiner.connect([sink])
    model.initialize()
    model.run(30)
    port = combiner.get_component_input(0).get_stats_collector()
    assert port.get_var_output_value() == 4 and port.get_var_content_value() == 0


@pytest.mark.parametrize("source_kind", ["interarrival", "buffering", "infinite"])
def test_source_into_combiner_port_does_not_duplicate_items(model, source_kind):
    """The port notifies upstream inside receive(); a source that had not yet removed the
    item from its pending slot used to send the same item twice."""
    from PyFlow import Combiner, InterArrivalBufferingSource, InterArrivalSource
    main = Feeder("Main", model, interval=10, count=3)
    if source_kind == "interarrival":
        comps = InterArrivalSource("Comps", model, 1)
    elif source_kind == "buffering":
        comps = InterArrivalBufferingSource("Comps", model, 1)
    else:
        comps = InfiniteSource("Comps", model)
    combiner = Combiner([2], 1, "C", model, batch_mode=True)
    sink = Sink("Sink", model, keep_items=True)
    main.connect([combiner])
    comps.connect([combiner.get_component_input(0)])
    combiner.connect([sink])
    model.initialize()
    model.run(40)
    used = [c.item_number for unit in sink.items for c in unit.get_sub_items()]
    assert len(sink.items) == 3 and len(used) == 6 and len(set(used)) == 6
