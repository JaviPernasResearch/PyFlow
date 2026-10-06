"""Model lists (FlexSim lists, SimuLean ``ModelList``): a rendezvous between producers that
*push* values and consumers that *pull* them with a query.

    orders = ModelList("Orders", model, fields={"due": "value.due_date", "late": "now > value.due_date"})
    orders.push(item)                                   # a value enters the list
    orders.pull("WHERE type == puller.type ORDER BY due ASC", puller=machine,
                on_fulfilled=lambda values: ...)        # now, or as soon as a push matches

* **Back-orders.** A pull that cannot be served (no match, or fewer than ``quantity``)
  becomes a back-order when it gives a callback; every push re-evaluates the back-orders in
  ``backorder_order`` (default: oldest first) and serves each one that can be fully served
  (first-fit). The callback runs inside the event of the push (as in SimuLean).
* **Fields.** In ``WHERE`` / ``ORDER BY`` a name is looked up as: a field defined on the list
  (expression or ``fn(entry, puller)``), then ``value``, ``puller``, ``age`` (time in the list),
  ``push_time``, ``now``, then the data given to ``push(value, **data)``, then the value's
  own fields (for items: ``type``, ``name``, ``priority``... and any label).
* **Order.** Without ``ORDER BY`` values are pulled first-in first-out; ties keep insertion
  order. Back-order queries see the same names plus ``priority`` and ``age`` of the pull.
* **Unique values.** By default a value already in the list is not added twice.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from .query import Query, QueryError
from .Statistics.statTimeWeightedVariable import StatTimeWeightedVariable

FieldDef = Union[str, Callable[["ListEntry", Any], Any]]


class ListEntry:
    """A value in a list, with its push time and the data given to ``push``."""

    __slots__ = ("value", "push_time", "seq", "data")

    def __init__(self, value: Any, push_time: float, seq: int, data: Dict[str, Any]):
        self.value = value
        self.push_time = push_time
        self.seq = seq
        self.data = data

    def __repr__(self) -> str:
        return f"ListEntry({self.value!r}, pushed={self.push_time:g})"


class _EntryScope(Mapping):
    """Lazy name resolution for one (entry, puller) pair."""

    __slots__ = ("lst", "entry", "puller", "_cache")

    def __init__(self, lst: "ModelList", entry: ListEntry, puller: Any):
        self.lst, self.entry, self.puller, self._cache = lst, entry, puller, {}

    def __getitem__(self, name: str) -> Any:
        if name in self._cache:
            return self._cache[name]
        value = self._resolve(name)
        self._cache[name] = value
        return value

    def _resolve(self, name: str) -> Any:
        lst, entry = self.lst, self.entry
        if name in lst.fields:
            return lst._field(name, entry, self.puller)
        if name == "value":
            return entry.value
        if name == "puller":
            if self.puller is None:
                raise KeyError(name)
            return self.puller
        if name == "age":
            return lst.model.now - entry.push_time
        if name == "push_time":
            return entry.push_time
        if name == "now":
            return lst.model.now
        if name in entry.data:
            return entry.data[name]
        getter = getattr(type(entry.value), "expression_field", None)
        if getter is not None:
            return getter(entry.value, name)
        raise KeyError(name)

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


class BackOrder:
    """A pull waiting for values. ``cancel()`` withdraws it."""

    __slots__ = ("lst", "query", "puller", "quantity", "on_fulfilled", "priority", "seq", "time",
                 "fulfilled", "cancelled", "values")

    def __init__(self, lst, query, puller, quantity, on_fulfilled, priority, seq, time):
        self.lst, self.query, self.puller, self.quantity = lst, query, puller, quantity
        self.on_fulfilled, self.priority, self.seq, self.time = on_fulfilled, priority, seq, time
        self.fulfilled = False
        self.cancelled = False
        self.values: List[Any] = []

    @property
    def pending(self) -> bool:
        return not (self.fulfilled or self.cancelled)

    def cancel(self) -> bool:
        return self.lst.cancel(self)

    def expression_field(self, name: str) -> Any:
        if name == "puller":
            return self.puller
        if name == "age":
            return self.lst.model.now - self.time
        if name in ("priority", "quantity", "time", "seq"):
            return getattr(self, name)
        getter = getattr(type(self.puller), "expression_field", None)
        if getter is not None:            # puller fields directly: ORDER BY due_date
            return getter(self.puller, name)
        raise KeyError(name)

    def __repr__(self) -> str:
        state = "fulfilled" if self.fulfilled else "cancelled" if self.cancelled else "waiting"
        return f"BackOrder({self.lst.name}, q={self.quantity}, {state})"


class _BackOrderScope(Mapping):
    __slots__ = ("bo",)

    def __init__(self, bo: BackOrder):
        self.bo = bo

    def __getitem__(self, name: str) -> Any:
        try:
            return self.bo.expression_field(name)
        except KeyError:
            raise KeyError(name) from None

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


class ModelList:
    """A list of values with queries and back-orders. ``fields``: calculated fields by name
    (expressions over the entry's names, or ``fn(entry, puller)``). ``backorder_order``:
    ``ORDER BY`` clause for waiting pulls (default oldest first)."""

    def __init__(self, name: str, model: Any, *, fields: Optional[Mapping[str, FieldDef]] = None,
                 backorder_order: Optional[str] = None, unique: bool = True):
        from .model import resolve_model
        self.name = name
        self.model = resolve_model(model)
        self.fields: Dict[str, Callable[[ListEntry, Any], Any]] = {}
        self.field_specs: Dict[str, FieldDef] = dict(fields or {})
        for field_name, definition in self.field_specs.items():
            if field_name in ("value", "puller", "age", "push_time", "now"):
                raise ValueError(f"E_INVALID_LIST: field name {field_name!r} is reserved")
            if isinstance(definition, str):
                compiled = Query(where=None, order_by=definition, text=definition)._order[0][0]
                self.fields[field_name] = (lambda entry, puller, fn=compiled, lst=self:
                                           fn(_EntryScope(lst, entry, puller)))
            elif callable(definition):
                self.fields[field_name] = definition
            else:
                raise TypeError(f"E_INVALID_LIST: field {field_name!r} must be an expression or a function")
        self.backorder_order = Query.of(backorder_order) if backorder_order else None
        self.unique = unique
        self.entries: List[ListEntry] = []
        self.backorders: List[BackOrder] = []
        self._seq = 0
        self.content = StatTimeWeightedVariable()
        self.waiting = StatTimeWeightedVariable()
        self._reset_counters()
        self.model.add_list(self)

    def __repr__(self) -> str:
        return f"ModelList({self.name!r}, values={len(self.entries)}, backorders={len(self.backorders)})"

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def values(self) -> List[Any]:
        return [e.value for e in self.entries]

    def _field(self, name: str, entry: ListEntry, puller: Any) -> Any:
        return self.fields[name](entry, puller)

    # ------------------------------------------------------------------ lifecycle
    def _reset_counters(self) -> None:
        self.pushes = 0
        self.pulls = 0                 # pulls served (immediately or as back-orders)
        self.stay_count = 0
        self.stay_total = 0.0
        self.stay_max = 0.0
        self.wait_count = 0            # back-orders served
        self.wait_total = 0.0
        self.wait_max = 0.0

    def clear(self, t: float = 0.0) -> None:
        self.entries.clear()
        self.backorders.clear()
        self._seq = 0
        self.content.reset(t, 0.0)
        self.waiting.reset(t, 0.0)
        self._reset_counters()

    def reset_stats(self, t: float) -> None:
        self.content.reset(t)
        self.waiting.reset(t)
        self._reset_counters()

    # ------------------------------------------------------------------ queries
    def _scope(self, entry: ListEntry, puller: Any) -> Mapping:
        return _EntryScope(self, entry, puller)

    def _select(self, query: Query, puller: Any, quantity: Optional[int]) -> List[ListEntry]:
        try:
            return query.select(self.entries, lambda e: self._scope(e, puller), quantity)
        except KeyError as exc:
            raise QueryError(f"E_QUERY_FAILED: list {self.name!r}: unknown name {exc.args[0]!r} in {query}") from None

    def peek(self, query: Union[None, str, Query] = None, *, puller: Any = None, quantity: Optional[int] = 1) -> List[Any]:
        """Values that a pull would take now (``quantity=None``: every match), without removing them."""
        return [e.value for e in self._select(Query.of(query), puller, quantity)]

    # ------------------------------------------------------------------ push / pull
    def push(self, value: Any, **data: Any) -> bool:
        """Add ``value``. Returns ``True`` if it was taken at once by a waiting pull."""
        if self.unique and any(e.value is value for e in self.entries):
            return False
        now = self.model.now
        entry = ListEntry(value, now, self._seq, data)
        self._seq += 1
        self.entries.append(entry)
        self.pushes += 1
        self.content.update(1, now)
        self._serve_backorders()
        return entry not in self.entries

    def pull(self, query: Union[None, str, Query] = None, *, puller: Any = None, quantity: int = 1,
             on_fulfilled: Optional[Callable[[List[Any]], Any]] = None, priority: float = 0) -> Union[List[Any], BackOrder]:
        """Take ``quantity`` matching values. Without ``on_fulfilled``: returns them now, or
        ``[]`` if there are not enough (nothing is taken). With ``on_fulfilled(values)``: it is
        called now if possible, otherwise a :class:`BackOrder` is registered and returned."""
        if quantity < 1:
            raise ValueError("E_INVALID_PULL: quantity must be >= 1")
        query = Query.of(query)
        chosen = self._select(query, puller, quantity)
        if len(chosen) >= quantity:
            values = self._take(chosen)
            self.pulls += 1
            if on_fulfilled is None:
                return values
            bo = BackOrder(self, query, puller, quantity, on_fulfilled, priority, self._seq, self.model.now)
            self._seq += 1
            bo.fulfilled, bo.values = True, values
            on_fulfilled(values)
            return bo
        if on_fulfilled is None:
            return []
        bo = BackOrder(self, query, puller, quantity, on_fulfilled, priority, self._seq, self.model.now)
        self._seq += 1
        self.backorders.append(bo)
        self.waiting.update(1, self.model.now)
        return bo

    def remove(self, value: Any) -> bool:
        """Take a specific value out of the list (it is no longer available)."""
        for entry in self.entries:
            if entry.value is value:
                self._take([entry])
                return True
        return False

    def cancel(self, backorder: BackOrder) -> bool:
        if not backorder.pending or backorder not in self.backorders:
            return False
        backorder.cancelled = True
        self.backorders.remove(backorder)
        self.waiting.update(-1, self.model.now)
        return True

    # ------------------------------------------------------------------ internals
    def _take(self, chosen: List[ListEntry]) -> List[Any]:
        now = self.model.now
        for entry in chosen:
            self.entries.remove(entry)
            stay = now - entry.push_time
            self.stay_count += 1
            self.stay_total += stay
            self.stay_max = max(self.stay_max, stay)
        self.content.update(-len(chosen), now)
        return [e.value for e in chosen]

    def _ordered_backorders(self) -> List[BackOrder]:
        if self.backorder_order is None:
            return list(self.backorders)
        try:
            return sorted(self.backorders, key=lambda bo: self.backorder_order.sort_key(_BackOrderScope(bo)))
        except KeyError as exc:
            raise QueryError(f"E_QUERY_FAILED: list {self.name!r}: unknown name {exc.args[0]!r} in "
                             f"backorder_order {self.backorder_order}") from None

    def _serve_backorders(self) -> None:
        served = True
        while served and self.backorders and self.entries:
            served = False
            for bo in self._ordered_backorders():
                if not bo.pending:
                    continue
                chosen = self._select(bo.query, bo.puller, bo.quantity)
                if len(chosen) < bo.quantity:
                    continue
                self.backorders.remove(bo)
                now = self.model.now
                self.waiting.update(-1, now)
                wait = now - bo.time
                self.wait_count += 1
                self.wait_total += wait
                self.wait_max = max(self.wait_max, wait)
                bo.fulfilled, bo.values = True, self._take(chosen)
                self.pulls += 1
                bo.on_fulfilled(bo.values)
                served = True          # the callback may push or pull: re-evaluate from the start
                break

    # ------------------------------------------------------------------ statistics
    def summary(self) -> Dict[str, Any]:
        now = self.model.now
        return {
            "name": self.name,
            "content_current": len(self.entries),
            "content_average": self.content.average(now),
            "content_max": self.content.max_value,
            "backorders_current": len(self.backorders),
            "backorders_average": self.waiting.average(now),
            "backorders_max": self.waiting.max_value,
            "pushes": self.pushes,
            "pulls": self.pulls,
            "staytime_average": self.stay_total / self.stay_count if self.stay_count else None,
            "staytime_max": self.stay_max if self.stay_count else None,
            "backorder_wait_average": self.wait_total / self.wait_count if self.wait_count else None,
            "backorder_wait_max": self.wait_max if self.wait_count else None,
        }


__all__ = ["ModelList", "ListEntry", "BackOrder"]
