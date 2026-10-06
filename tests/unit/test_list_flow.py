"""Flow through lists (push to list / pull from list): reference models with exact values."""
import pytest

from PyFlow import (InfiniteSource, InterArrivalSource, ItemsQueue, MaxQueueInputStrategy, Model, MultiServer,
                    ResourcePool, ScheduleSource, Sink)
from PyFlow.lists import ModelList
from PyFlow.states import ElementState
from tests.harness import Collector, at


def jobs(*rows):
    """ScheduleSource data: (time, name/type, qty, labels)."""
    data = {"Time": [], "Name": [], "Q": []}
    keys = sorted({k for *_, labels in rows for k in labels})
    for k in keys:
        data[k] = []
    for t, name, q, labels in rows:
        data["Time"].append(t)
        data["Name"].append(name)
        data["Q"].append(q)
        for k in keys:
            data[k].append(labels.get(k))
    return data


def labels_of(collector, label):
    return [item.get_label_value(label) for _, item in collector.received]


# ------------------------------------------------------------------ global priority queue
def test_global_priority_queue_over_several_queues(model):
    """Two queues announce their items; one machine takes the highest 'prio' of both."""
    jobs_list = ModelList("Jobs", model)
    s1 = ScheduleSource("S1", model, data_dict=jobs((0, "J", 1, {"prio": 1}), (0, "J", 1, {"prio": 5})))
    s2 = ScheduleSource("S2", model, data_dict=jobs((0, "J", 1, {"prio": 3}), (0, "J", 1, {"prio": 9})))
    q1, q2 = ItemsQueue(10, "Q1", model), ItemsQueue(10, "Q2", model)
    m = MultiServer(1, 2, "M", model)
    out = Collector("Out", model)
    s1.connect([q1])
    s2.connect([q2])
    q1.connect([jobs_list])
    q2.connect_to_list(jobs_list)
    m.pull_from_list(jobs_list, "ORDER BY prio DESC")
    m.connect([out])
    model.initialize()
    model.run(20)
    # t=0: the first announced item (prio 1) is taken at once by the idle machine; then by priority
    assert labels_of(out, "prio") == [1, 9, 5, 3]
    assert out.times == [2, 4, 6, 8]
    assert (len(q1.items_q), len(q2.items_q), len(jobs_list)) == (0, 0, 0)
    assert q2.get_stats_collector().get_var_output_value() == 2      # statistics from the list link


def test_items_wait_in_their_queue_not_in_the_list(model):
    jobs_list = ModelList("Jobs", model)
    src = ScheduleSource("S", model, data_dict=jobs((0, "J", 3, {})))
    q = ItemsQueue(10, "Q", model)
    m = MultiServer(1, 5, "M", model)
    src.connect([q])
    q.connect([jobs_list])
    m.pull_from_list(jobs_list)
    m.connect([Sink("Sink", model)])
    model.initialize()
    model.run(3)
    assert len(q.items_q) == 2 and q.state == ElementState.BLOCKED      # held, announced
    assert [e.origin for e in jobs_list.entries] == [q, q]
    assert q.get_stats_collector().get_var_content_value() == 2


# ------------------------------------------------------------------ filters and back-orders
def test_consumers_filter_by_label_without_head_of_line_blocking(model):
    lst = ModelList("L", model)
    src = ScheduleSource("S", model, data_dict=jobs((0, "A", 2, {}), (0, "B", 1, {}), (0, "A", 1, {})))
    q = ItemsQueue(10, "Q", model)
    ma, mb = MultiServer(1, 1, "MA", model), MultiServer(1, 1, "MB", model)
    out_a, out_b = Collector("OutA", model), Collector("OutB", model)
    src.connect([q])
    q.connect([lst])
    ma.pull_from_list(lst, "WHERE type == 'A'")
    mb.pull_from_list(lst, "WHERE type == 'B'")
    ma.connect([out_a])
    mb.connect([out_b])
    model.initialize()
    model.run(10)
    assert [i.type for _, i in out_a.received] == ["A", "A", "A"] and out_a.times == [1, 2, 3]
    assert [i.type for _, i in out_b.received] == ["B"] and out_b.times == [1]   # not behind the A's


def test_pending_pulls_are_served_when_items_arrive(model):
    """Idle machines wait as back-orders; items arrive at 3 and 4 (dt = 0 delivery)."""
    lst = ModelList("L", model)
    src = ScheduleSource("S", model, data_dict=jobs((3, "J", 1, {}), (4, "J", 1, {})))
    q = ItemsQueue(10, "Q", model)
    m1, m2 = MultiServer(1, 10, "M1", model), MultiServer(1, 10, "M2", model)
    out = Collector("Out", model)
    src.connect([q])
    q.connect([lst])
    m1.pull_from_list(lst)
    m2.pull_from_list(lst)
    m1.connect([out])
    m2.connect([out])
    model.initialize()
    assert len(lst.backorders) == 2
    model.run(20)
    assert out.times == [13, 14] and [i.item_number for _, i in out.received] == [1, 2]
    assert lst.summary()["backorder_wait_average"] == pytest.approx(3.5)


def test_puller_input_strategy_and_capacity(model):
    """The puller's own input strategy is part of its pull: MaxQueue(1) on a 3-slot server."""
    lst = ModelList("L", model)
    src = ScheduleSource("S", model, data_dict=jobs((0, "J", 3, {})))
    q = ItemsQueue(10, "Q", model)
    m = MultiServer(3, 2, "M", model)
    m.set_input_strategy(MaxQueueInputStrategy(1))
    out = Collector("Out", model)
    src.connect([q])
    q.connect([lst])
    m.pull_from_list(lst)
    m.connect([out])
    model.initialize()
    model.run(10)
    assert out.times == [2, 4, 6]


# ------------------------------------------------------------------ origins: servers, sources, stops
def test_finished_items_of_a_server_are_offered(model):
    """M1 (1 s) sends to a list; M2 (3 s) pulls: M1 stays blocked until M2 takes its item."""
    lst = ModelList("L", model)
    src = InfiniteSource("Src", model)
    m1, m2 = MultiServer(1, 1, "M1", model), MultiServer(1, 3, "M2", model)
    out = Collector("Out", model)
    src.connect([m1])
    m1.connect([lst])
    m2.pull_from_list(lst)
    m2.connect([out])
    model.initialize()
    model.run(10)
    assert out.times == [4, 7, 10]
    assert m1.state_ratio(ElementState.BLOCKED) == pytest.approx(0.6)     # blocked 2-4, 5-7, 8-10


def test_source_sends_to_list_and_waits(model):
    lst = ModelList("L", model)
    src = InterArrivalSource("Src", model, 1)
    m = MultiServer(1, 4, "M", model)
    out = Collector("Out", model)
    src.connect([lst])
    m.pull_from_list(lst)
    m.connect([out])
    model.initialize()
    model.run(13)
    # arrivals only after the previous item was taken: 1, (taken 1) 2, (taken 5) 6, (taken 9) 10
    assert out.times == [5, 9, 13] and src.number_items == 4


def test_items_of_a_stopped_origin_are_not_taken(model):
    lst = ModelList("L", model)
    src = ScheduleSource("S", model, data_dict=jobs((0, "J", 2, {})))
    q = ItemsQueue(10, "Q", model)
    m = MultiServer(1, 1, "M", model)
    out = Collector("Out", model)
    src.connect([q])
    q.connect([lst])
    m.pull_from_list(lst)
    m.connect([out])
    model.initialize()
    token = {}
    at(model, 0.5, lambda: token.setdefault("t", q.stop(ElementState.BREAKDOWN, block_input=False)))
    at(model, 5, lambda: q.resume(token["t"]))
    model.run(10)
    assert out.times == [1, 6]


def test_puller_resources_and_release(model):
    """A puller that needs an operator: the pull only takes the item; the operator is waited
    for inside the machine as usual."""
    op = ResourcePool("Op", model, capacity=1)
    lst = ModelList("L", model)
    src = ScheduleSource("S", model, data_dict=jobs((0, "J", 2, {})))
    q = ItemsQueue(10, "Q", model)
    m1, m2 = MultiServer(1, 2, "M1", model, resources=[op]), MultiServer(1, 2, "M2", model, resources=[op])
    out = Collector("Out", model)
    src.connect([q])
    q.connect([lst])
    m1.pull_from_list(lst)
    m2.pull_from_list(lst)
    m1.connect([out])
    m2.connect([out])
    model.initialize()
    model.run(10)
    assert out.times == [2, 4] and m2.time_in_state(ElementState.WAITING_FOR_RESOURCE) == 2


# ------------------------------------------------------------------ values that are not items
def test_value_list_for_orders(model):
    """A list of plain values (orders) moves information: a pull with a callback."""
    orders = ModelList("Orders", model, fields={"big": "value['qty'] > 5"})
    served = []
    model.initialize()
    orders.pull("WHERE big", on_fulfilled=lambda values: served.append((model.now, values[0]["id"])))
    at(model, 2, lambda: orders.push({"id": "O1", "qty": 3}))
    at(model, 4, lambda: orders.push({"id": "O2", "qty": 8}))
    model.run(10)
    assert served == [(4, "O2")] and [v["id"] for v in orders.values] == ["O1"]


# ------------------------------------------------------------------ runs and errors
def test_reinitialize_and_determinism():
    def run():
        model = Model(seed=4)
        lst = ModelList("L", model)
        src = InterArrivalSource("Src", model, "ExponentialMean~1", )
        q = ItemsQueue(100, "Q", model)
        servers = [MultiServer(1, "ExponentialMean~1.8", f"M{i}", model) for i in range(2)]
        sink = Sink("Sink", model)
        src.connect([q])
        q.connect([lst])
        for i, s in enumerate(servers):
            s.pull_from_list(lst, "ORDER BY age DESC", priority=i)
            s.connect([sink])
        model.initialize()
        model.run(500)
        first = sink.get_stats_collector().get_var_input_value()
        model.initialize()
        model.run(500)
        return first, sink.get_stats_collector().get_var_input_value()

    a, b = run()
    assert a == b > 200
    assert run() == (a, b)


def test_list_connection_errors(model):
    lst = ModelList("L", model)
    q = ItemsQueue(5, "Q", model)
    with pytest.raises(ValueError, match="E_MIXED_LIST_DESTINATION"):
        q.connect([lst, Sink("S", model)])
    with pytest.raises(TypeError, match="E_LIST_NOT_SUPPORTED"):
        Collector("C", model).connect_to_list(lst)


# ------------------------------------------------------------------ specification
def global_queue_spec(**extra):
    data = {
        "seed": 1,
        "lists": [{"id": "jobs", "fields": {"rank": "prio * 10"}}],
        "elements": [
            {"type": "ScheduleSource", "id": "s1", "jobs": [{"time": 0, "name": "J", "labels": {"prio": 1}},
                                                            {"time": 0, "name": "J", "labels": {"prio": 5}}]},
            {"type": "ScheduleSource", "id": "s2", "jobs": [{"time": 0, "name": "J", "labels": {"prio": 3}},
                                                            {"time": 0, "name": "J", "labels": {"prio": 9}}]},
            {"type": "ItemsQueue", "id": "q1", "capacity": 10},
            {"type": "ItemsQueue", "id": "q2", "capacity": 10},
            {"type": "MultiServer", "id": "m", "num_servers": 1, "service_time": 2},
            {"type": "Sink", "id": "snk", "keep_items": True}],
        "connections": [
            {"origin": "s1", "destinations": ["q1"]}, {"origin": "s2", "destinations": ["q2"]},
            {"origin": "q1", "destinations": ["jobs"]}, {"origin": "q2", "destinations": ["jobs"]},
            {"origin": "jobs", "destinations": ["m"], "query": "ORDER BY rank DESC"},
            {"origin": "m", "destinations": ["snk"]}],
    }
    data.update(extra)
    return data


def test_lists_through_the_spec():
    from PyFlow.spec import ModelSpec, validate_spec
    spec = ModelSpec.from_dict(global_queue_spec())
    assert validate_spec(spec) == []
    built = spec.build()
    results = built.run(until=20)
    assert [i.get_label_value("prio") for i in built["snk"].items] == [1, 9, 5, 3]
    assert results["lists"]["jobs"]["pulls"] == 4 and results["lists"]["jobs"]["content_current"] == 0
    assert ModelSpec.from_json(spec.to_json()) == spec
    assert built.builder.to_spec() == spec


def test_list_validation():
    from PyFlow.spec import ModelSpec, validate_spec
    data = global_queue_spec()
    data["lists"] += [{"id": "orphan"}, {"id": "nobody_pulls"}, {"id": "q1"}]
    data["connections"] += [
        {"origin": "s1", "destinations": ["nobody_pulls", "q1"]},                       # mixed destination
        {"origin": "snk", "destinations": ["nobody_pulls"]},                             # sink cannot push
        {"origin": "s2", "destinations": ["m"], "query": "ORDER BY age"},               # query without list
        {"origin": "jobs", "destinations": ["s2", "jobs"], "strategy": "RoundRobin"},   # source, list, strategy
        {"origin": "nobody_pulls", "destinations": ["snk"]},                             # snk has another input
    ]
    issues = [(i.code, i.path) for i in validate_spec(ModelSpec.from_dict(data))]
    assert ("E_DUPLICATE_ID", "elements[2].id") in issues
    for code in ["E_MIXED_LIST_DESTINATION", "E_LIST_NOT_SUPPORTED", "E_QUERY_NOT_ALLOWED",
                 "E_STRATEGY_NOT_ALLOWED", "E_SOURCE_AS_DESTINATION", "E_LIST_TO_LIST", "E_MIXED_INPUT",
                 "W_UNUSED_LIST"]:
        assert code in {c for c, _ in issues}, code


def test_list_mcp_tools():
    pytest.importorskip("mcp")
    from tests.test_mcp_tools import run_session
    data = global_queue_spec()

    async def script(call):
        created = await call("create_lists_batch", {"lists": data["lists"]})
        await call("create_elements_batch", {"elements": data["elements"]})
        await call("connect_batch", {"connections": data["connections"]})
        await call("initialize_model")
        run = await call("run_experiment", {"stop_time": 20})
        exported = await call("export_model_spec")
        return created, run, exported["spec"]

    created, run, exported = run_session(script)
    assert created == {"status": "success", "created_ids": ["jobs"], "failed_at": None}
    assert run["lists"][0]["id"] == "jobs" and run["lists"][0]["pulls"] == 4
    assert exported["lists"] == [{"id": "jobs", "name": "jobs", "fields": {"rank": "prio * 10"}, "unique": True,
                                  "deliver": "event"}]
