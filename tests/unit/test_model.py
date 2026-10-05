import pytest
from scipy import stats

from PyFlow import (InterArrivalSource, Item, ItemsQueue, Model, MultiServer, SimClock, Sink)


def build_mm1(model, *, arrival="Exponential~1", service="Exponential~1.25"):
    src = InterArrivalSource("Source", model, arrival)
    queue = ItemsQueue(10_000, "Queue", model)
    server = MultiServer(1, service, "Server", model)
    sink = Sink("Sink", model)
    src.connect([queue])
    queue.connect([server])
    server.connect([sink])
    return src, queue, server, sink


def run_mm1(seed, until=500.0, **kw):
    m = Model(seed=seed)
    *_, queue, server, sink = build_mm1(m, **kw)
    m.initialize()
    m.run(until)
    return (sink.get_stats_collector().get_var_input_value(),
            queue.get_stats_collector().get_var_content_average(),
            server.get_stats_collector().get_var_staytime_average())


def test_elements_register_in_their_own_model():
    a, b = Model(seed=1), Model(seed=1)
    build_mm1(a)
    assert len(a.elements) == 4 and b.elements == []
    assert a.get_element("Queue").model is a
    with pytest.raises(KeyError, match="E_UNKNOWN_ELEMENT"):
        b.get_element("Queue")


def test_same_seed_gives_identical_results():
    assert run_mm1(42) == run_mm1(42)


def test_different_seeds_give_different_results():
    assert run_mm1(42) != run_mm1(43)


def test_scipy_distributions_are_also_seeded():
    kw = dict(arrival=stats.expon(scale=1.0), service=stats.expon(scale=0.8))
    assert run_mm1(5, **kw) == run_mm1(5, **kw)
    assert run_mm1(5, **kw) != run_mm1(6, **kw)


def test_reinitializing_a_model_reproduces_the_run():
    m = Model(seed=3)
    *_, sink = build_mm1(m)
    results = []
    for _ in range(2):
        m.initialize()
        m.run(200)
        results.append((sink.get_stats_collector().get_var_input_value(), m.items_created))
    assert results[0] == results[1]


def test_two_models_interleaved_do_not_interfere():
    reference = run_mm1(11, until=300)

    m1, m2 = Model(seed=11), Model(seed=99)
    *_, q1, s1, k1 = build_mm1(m1)
    build_mm1(m2)
    m1.initialize()
    m2.initialize()
    for t in range(10, 301, 10):  # advance both models alternately
        m1.run(t)
        m2.run(t)
    interleaved = (k1.get_stats_collector().get_var_input_value(),
                   q1.get_stats_collector().get_var_content_average(),
                   s1.get_stats_collector().get_var_staytime_average())
    assert interleaved == reference
    assert m1.now == m2.now == 300


def test_item_ids_are_per_model():
    m1, m2 = Model(seed=1), Model(seed=2)
    _, _, _, k1 = build_mm1(m1)
    _, _, _, k2 = build_mm1(m2)
    for m in (m1, m2):
        m.initialize()
        m.run(50)
    assert m1.items_created > 0 and m2.items_created > 0
    first1 = min(it.item_number for it in k1.get_stats_collector().entry_times)
    first2 = min(it.item_number for it in k2.get_stats_collector().entry_times)
    assert first1 == first2 == 1


def test_random_streams_depend_on_key_not_creation_order():
    """Adding an element must not change the random numbers of the others (CRN)."""
    m1 = Model(seed=8)
    s1 = m1.bind_sampler("Exponential~1", "Server.service")

    m2 = Model(seed=8)
    m2.bind_sampler("Exponential~1", "Extra.service")
    s2 = m2.bind_sampler("Exponential~1", "Server.service")

    assert [s1.sample() for _ in range(5)] == [s2.sample() for _ in range(5)]


def test_duplicate_keys_get_independent_streams():
    m = Model(seed=8)
    a = m.bind_sampler("Uniform~0~1", "Source.interarrival")
    b = m.bind_sampler("Uniform~0~1", "Source.interarrival")
    assert a.key == "Source.interarrival" and b.key == "Source.interarrival#2"
    assert [a.sample() for _ in range(3)] != [b.sample() for _ in range(3)]


def test_seed_is_recorded_when_not_given():
    m = Model()
    assert isinstance(m.seed, int)
    replay = Model(seed=m.seed)
    assert m.rng("k").random() == replay.rng("k").random()


def test_model_accepts_parameters():
    m = Model(seed=1, parameters={"route": 2})
    assert m.parameters["route"] == 2


def test_warmup_resets_statistics():
    m = Model(seed=4)
    *_, queue, server, sink = build_mm1(m)
    m.initialize()
    m.run(1000, warmup=200)
    assert m.stats_reset_time == 200
    sc = sink.get_stats_collector()
    # Only items that arrived after the warm-up are counted
    m2 = Model(seed=4)
    *_, sink2 = build_mm1(m2)
    m2.initialize()
    m2.run(1000)
    assert sc.get_var_input_value() < sink2.get_stats_collector().get_var_input_value()


def test_warmup_must_be_inside_horizon(model):
    model.initialize()
    with pytest.raises(ValueError, match="E_INVALID_WARMUP"):
        model.run(10, warmup=20)


# --------------------------------------------------------------------- compat
def test_legacy_clock_argument_still_works():
    m = Model(seed=1)
    q = ItemsQueue(5, "Q", m.clock)
    assert q.model is m and q.clock is m.clock


def test_legacy_get_instance_returns_default_clock():
    SimClock._instance = None
    with pytest.warns(DeprecationWarning):
        c1 = SimClock.get_instance()
    with pytest.warns(DeprecationWarning):
        assert SimClock.get_instance() is c1
    assert isinstance(c1.model, Model)
    SimClock._instance = None


def test_creating_models_does_not_touch_the_default_clock():
    SimClock._instance = None
    Model(seed=1)
    assert SimClock._instance is None


def test_bare_simclock_gets_its_own_model():
    clock = SimClock()
    q = ItemsQueue(1, "Q", clock)
    assert clock.sim_elements == [q]


def test_items_created_by_elements_do_not_touch_global_counter():
    before = Item.ITEM_NUMBER
    run_mm1(1, until=50)
    assert Item.ITEM_NUMBER == before


def test_initialize_warns_about_discarded_events(model, caplog):
    model.schedule(lambda: None, 5.0)
    with caplog.at_level("WARNING", logger="pyflow"):
        model.initialize()
    assert "discarded 1 pending event" in caplog.text
    assert model.clock.pending_events() == 0
