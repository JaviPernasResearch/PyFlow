"""Queries and model lists (FlexSim lists / SimuLean ModelList): exact cases."""
import pytest

from PyFlow import Item, MultiServer
from PyFlow.lists import ModelList
from PyFlow.query import Query, QueryError
from tests.harness import at


def item(model, item_type="A", priority=0, **labels):
    return Item(model.now, item_type=item_type, labels=labels, item_id=model.next_item_id(), priority=priority)


def ids(values):
    return [v.item_number for v in values]


@pytest.fixture
def ready(model):
    model.initialize()
    return model


# ------------------------------------------------------------------ query language
ROWS = [dict(type="A", age=3, priority=1), dict(type="A", age=5, priority=1), dict(type="B", age=9, priority=9),
        dict(type="A", age=4, priority=2), dict(type="A", age=1, priority=5)]


@pytest.mark.parametrize("text, expected", [
    ("WHERE type = 'A' AND age > 2 ORDER BY priority DESC, age", [3, 0, 1]),
    ("WHERE type == 'A' and not age > 3", [0, 4]),
    ("WHERE type <> 'A'", [2]),
    ("ORDER BY age DESC", [2, 1, 3, 0, 4]),
    ("age DESC", [2, 1, 3, 0, 4]),                         # a bare clause is an ORDER BY
    ("ORDER BY type DESC, priority", [2, 0, 1, 3, 4]),     # ties keep the original order
    ("", [0, 1, 2, 3, 4]),
    ("WHERE type = 'OR'", []),                             # SQL words inside strings are kept
])
def test_query_language(text, expected):
    assert [ROWS.index(r) for r in Query.parse(text).select(ROWS, lambda r: r)] == expected


def test_query_callables_and_errors():
    q = Query(where=lambda s: s["age"] > 3, order_by=lambda s: -s["age"])
    assert [r["age"] for r in q.select(ROWS, lambda r: r)] == [9, 5, 4]
    for bad in ["WHERE age >", "ORDER BY", "WHERE __import__('os')", "WHERE x.__class__"]:
        with pytest.raises(QueryError, match="E_INVALID_QUERY"):
            Query.parse(bad)
    with pytest.raises(QueryError, match="E_QUERY_FAILED"):
        Query.parse("WHERE nope > 1").select(ROWS, lambda r: r)


def test_none_sorts_last_ascending():
    rows = [dict(d=None), dict(d=2), dict(d=1)]
    assert [r["d"] for r in Query.parse("d ASC").select(rows, lambda r: r)] == [1, 2, None]
    assert [r["d"] for r in Query.parse("d DESC").select(rows, lambda r: r)] == [None, 2, 1]


# ------------------------------------------------------------------ push / pull / back-orders
def test_pull_now_is_fifo_without_order(ready):
    lst = ModelList("L", ready)
    a, b, c = (item(ready) for _ in range(3))
    for v in (a, b, c):
        lst.push(v)
    assert lst.pull(quantity=2) == [a, b] and lst.values == [c]
    assert lst.pull("WHERE type == 'Z'") == [] and lst.values == [c]   # nothing taken when unmet


def test_item_fields_labels_and_calculated_fields(ready):
    lst = ModelList("Orders", ready, fields={"slack": "due - now", "big": lambda entry, puller: entry.value.labels["qty"] > 5})
    orders = [item(ready, "A", due=30, qty=2), item(ready, "B", due=10, qty=9), item(ready, "A", due=20, qty=7)]
    for o in orders:
        lst.push(o)
    assert ids(lst.peek("WHERE type == 'A' ORDER BY slack", quantity=None)) == [3, 1]
    assert ids(lst.peek("WHERE big ORDER BY value.due DESC", quantity=None)) == [3, 2]
    with pytest.raises(ValueError, match="reserved"):
        ModelList("Bad", ready, fields={"age": "1"})


def test_puller_fields(ready):
    machine = MultiServer(1, 1, "M", ready)
    lst = ModelList("L", ready)
    lst.push(item(ready, "M"))
    lst.push(item(ready, "Other"))
    assert ids(lst.peek("WHERE type == puller.name", puller=machine)) == [1]
    with pytest.raises(QueryError, match="unknown name 'puller'"):
        lst.peek("WHERE type == puller.name")


def test_backorder_is_served_by_the_matching_push(model):
    lst = ModelList("L", model)
    got = []
    model.initialize()
    bo = lst.pull("WHERE type == 'B'", on_fulfilled=lambda values: got.append((model.now, ids(values))))
    at(model, 2, lambda: lst.push(item(model, "A")))
    at(model, 5, lambda: lst.push(item(model, "B")))
    model.run(10)
    assert got == [(5, [2])] and bo.fulfilled and lst.values[0].type == "A"
    s = lst.summary()
    assert (s["pushes"], s["pulls"], s["backorder_wait_average"], s["content_current"]) == (2, 1, 5, 1)
    assert s["backorders_average"] == pytest.approx(0.5)          # one back-order during 5 of 10


def test_backorder_quantity_waits_for_enough_values(ready):
    lst = ModelList("L", ready)
    got = []
    lst.pull(quantity=3, on_fulfilled=lambda v: got.append(ids(v)))
    lst.push(item(ready))
    lst.push(item(ready))
    assert got == [] and len(lst) == 2
    lst.push(item(ready))
    assert got == [[1, 2, 3]] and len(lst) == 0


def test_backorder_order_and_first_fit(ready):
    lst = ModelList("L", ready, backorder_order="priority DESC")
    got = []
    lst.pull(on_fulfilled=lambda v: got.append("low"))
    lst.pull(on_fulfilled=lambda v: got.append("high"), priority=5)
    lst.pull("WHERE type == 'B'", on_fulfilled=lambda v: got.append("B only"), priority=9)
    lst.push(item(ready, "A"))           # B-only cannot use it: the high-priority pull takes it
    lst.push(item(ready, "A"))
    assert got == ["high", "low"]
    lst.push(item(ready, "B"))
    assert got == ["high", "low", "B only"]


def test_backorder_order_by_puller_fields(ready):
    lst = ModelList("L", ready, backorder_order="due ASC")
    got = []
    for name, due in [("late", 50), ("early", 10)]:
        lst.pull(puller=item(ready, name, due=due), on_fulfilled=lambda v, n=name: got.append(n))
    lst.push(item(ready))
    assert got == ["early"]


def test_cancel_unique_remove_and_reinitialize(model):
    lst = ModelList("L", model)
    model.initialize()
    v = item(model)
    assert lst.push(v) is False and lst.push(v) is False and len(lst) == 1      # unique by default
    assert lst.remove(v) and not lst.remove(v)
    bo = lst.pull(on_fulfilled=lambda values: pytest.fail("cancelled"))
    assert bo.cancel() and not bo.cancel()
    lst.push(item(model))
    assert len(lst) == 1
    dup = ModelList("Dup", model, unique=False)
    dup.push(v)
    dup.push(v)
    assert len(dup) == 2
    model.initialize()
    assert len(lst) == 0 and lst.summary()["pushes"] == 0
    with pytest.raises(ValueError, match="E_DUPLICATE_LIST"):
        ModelList("L", model)


def test_callback_can_push_again(ready):
    """A fulfilled pull that pushes to the same list re-triggers the back-orders."""
    lst = ModelList("L", ready)
    got = []
    lst.pull("WHERE type == 'B'", on_fulfilled=lambda v: got.append("B"))
    lst.pull("WHERE type == 'A'", on_fulfilled=lambda v: (got.append("A"), lst.push(item(ready, "B"))))
    lst.push(item(ready, "A"))
    assert got == ["A", "B"] and len(lst) == 0


def test_stay_time_and_warmup(model):
    lst = ModelList("L", model)
    model.initialize()
    at(model, 1, lambda: lst.push(item(model)))
    at(model, 4, lambda: lst.pull())
    at(model, 6, lambda: lst.push(item(model)))
    model.run(10, warmup=5)
    s = lst.summary()
    assert (s["pushes"], s["pulls"], s["staytime_average"], s["content_current"]) == (1, 0, None, 1)
    assert s["content_average"] == pytest.approx(4 / 5)
