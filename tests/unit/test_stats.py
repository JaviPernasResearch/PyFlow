import pytest

from PyFlow import ItemsQueue, Model, MultiServer
from PyFlow.Statistics import StatTimeWeightedVariable
from tests.harness import Collector, Feeder, at


def test_time_weighted_variable_known_pattern():
    v = StatTimeWeightedVariable(0.0)
    v.update(+1, 0.0)
    v.update(-1, 5.0)
    assert v.average(10.0) == pytest.approx(0.5)
    assert v.max_value == 1 and v.min_value == 0


def test_time_weighted_variable_reset_keeps_level():
    v = StatTimeWeightedVariable(0.0)
    v.update(+2, 0.0)
    v.reset(4.0)
    assert v.value == 2 and v.max_value == 2
    v.update(-2, 6.0)
    assert v.average(8.0) == pytest.approx((2 * 2 + 0 * 2) / 4)


def test_time_weighted_average_with_no_elapsed_time_is_current_level():
    v = StatTimeWeightedVariable(3.0)
    v.update(+1, 3.0)
    assert v.average(3.0) == 1


def test_server_wip_one_item_for_5s_then_idle_for_5s(model):
    feeder = Feeder("Feeder", model, interval=100, count=1)
    server = MultiServer(1, 5, "Server", model)
    sink = Collector("Sink", model)
    feeder.connect([server])
    server.connect([sink])
    model.initialize()
    model.run(10)
    sc = server.get_stats_collector()
    assert sink.times == [5.0]
    assert sc.get_var_content_average() == pytest.approx(0.5)
    assert sc.get_var_staytime_average() == 5.0


def test_queue_wip_with_forced_blocking(model):
    feeder = Feeder("Feeder", model, interval=1, count=4)
    queue = ItemsQueue(10, "Queue", model)
    sink = Collector("Sink", model)
    feeder.connect([queue])
    queue.connect([sink])
    sink.close()
    model.initialize()
    at(model, 10, sink.open)
    model.run(20)
    # items wait from t=0,1,2,3 until t=10: area = 10+9+8+7 = 34 over 20
    assert queue.get_stats_collector().get_var_content_average() == pytest.approx(34 / 20)
    assert queue.get_stats_collector().get_var_content_max() == 4
    assert sink.times == [10, 10, 10, 10]
    assert sink.ids == [1, 2, 3, 4]


def test_reset_at_warmup_discards_earlier_history(model):
    feeder = Feeder("Feeder", model, interval=1, count=4)
    queue = ItemsQueue(10, "Queue", model)
    sink = Collector("Sink", model)
    feeder.connect([queue])
    queue.connect([sink])
    sink.close()
    model.initialize()
    at(model, 10, sink.open)
    model.run(20, warmup=5)
    sc = queue.get_stats_collector()
    # After t=5: 4 items until t=10, then 0 until 20 -> 20 / 15
    assert sc.get_var_content_average() == pytest.approx(20 / 15)
    assert sc.get_var_input_value() == 0          # all entries happened before the warm-up
    assert sc.get_var_output_value() == 4
    assert sc.get_var_staytime_average() == pytest.approx((10 + 9 + 8 + 7) / 4)


def test_sources_do_not_report_negative_content(model):
    feeder = Feeder("Feeder", model, interval=1, count=5)
    sink = Collector("Sink", model)
    feeder.connect([sink])
    model.initialize()
    model.run(10)
    sc = feeder.get_stats_collector()
    assert sc.get_var_output_value() == 5
    assert sc.get_var_content_value() == 0
    assert sc.get_var_content_average() == 0


def test_initialize_resets_statistics(model):
    feeder = Feeder("Feeder", model, interval=1, count=3)
    sink = Collector("Sink", model)
    feeder.connect([sink])
    for _ in range(2):
        model.initialize()
        model.run(10)
        assert sink.get_stats_collector().get_var_input_value() == 3
