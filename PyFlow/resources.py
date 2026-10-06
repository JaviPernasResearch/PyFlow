"""Shared resources: operators, robots, tools, fixtures... anything an element needs while it works.

A :class:`ResourcePool` holds interchangeable *units*, optionally with skills. Elements with
active service time (``MultiServer``, ``Combiner``, ``MultiAssembler`` and any element using
:class:`ResourceUser`) declare what they need with :class:`ResourceRequirement`:

    welders = ResourcePool("Welders", model, capacity=2, kind="operator")
    robots  = ResourcePool("Robots", model, units=[{"name": "R1", "skills": ["weld", "paint"]},
                                                   {"name": "R2", "skills": ["paint"]}], kind="robot")
    weld = MultiServer(2, 5, "Weld", model,
                       resources=[welders, ResourceRequirement(robots, skill="weld", during="processing")])

Rules (the defaults; all of them can be changed with queries, see :mod:`PyFlow.query`):

* A phase (``setup`` or ``processing``) starts only when *all* the requirements it needs are
  granted at once (no partial holding, so two elements cannot deadlock each other).
* **Request order** (``model.resources.configure(request_order=...)``, default
  ``"priority DESC"``): waiting requests are ranked with this ``ORDER BY`` over the request
  fields ``priority`` (item priority, or the repair priority), ``time``, ``age``, ``seq``,
  ``quantity``, ``kind`` (``"work"`` | ``"repair"``), ``element`` (name) and ``item``
  (``item.due_date``...); ties keep the request order.
* **Discipline** (``configure(discipline=...)``): ``"first_fit"`` (default) grants, in that
  order, every request that can be fully served (a big request does not block smaller ones
  behind it); ``"strict"`` stops at the first one that cannot be served (nobody overtakes).
* **Unit choice** (``ResourcePool(unit_order=...)``, default ``"skills_count ASC"``): ``ORDER
  BY`` over the unit fields ``name``, ``index``, ``skills``, ``skills_count``, ``busy_time``,
  ``utilization``, ``idle_since``, ``idle_time``, ``kind`` and the unit ``attributes``.
* **Unit filter** (``ResourceRequirement(where=...)``): an expression over the same unit
  fields plus ``item`` and ``element`` of the request (``"level >= item.complexity"``).
* ``during="both"`` (default) holds the units from the start of the setup to the end of
  the processing; ``"setup"`` / ``"processing"`` only during that phase.
* ``release="on_exit"`` (default, as SimuLean) keeps the units until the item has left the
  element (also while it is blocked); ``"on_finish"`` frees them when the processing ends.
* Units are task executers (:class:`~PyFlow.executers.Operator` by default) with their own
  states and statistics; idle units are published in ``pool.list``. A grant reserves the units
  at once; a request that had to wait is told in a dt = 0 event (like list back-orders).
* With the default unit order, among the idle units with the skill the one with the fewest
  skills is chosen (ties: declaration order), so versatile units stay available for the tasks
  only they can do.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from .query import Query, QueryError
from .Statistics.statTimeWeightedVariable import StatTimeWeightedVariable

DURING = ("setup", "processing", "both")
RELEASE = ("on_exit", "on_finish")
DISCIPLINES = ("first_fit", "strict")
DEFAULT_REQUEST_ORDER = "priority DESC"
DEFAULT_UNIT_ORDER = "skills_count ASC, index ASC"


def _make_units(pool: "ResourcePool", capacity: Optional[int], units: Optional[Sequence[Any]]) -> List[Any]:
    from .executers import Operator, TaskExecuter
    name, model = pool.name, pool.model
    if (capacity is None) == (units is None):
        raise ValueError(f"E_INVALID_RESOURCE: pool {name!r} needs exactly one of 'capacity' or 'units'")
    if units is None:
        if capacity < 1:
            raise ValueError(f"E_INVALID_RESOURCE: pool {name!r} capacity must be >= 1")
        units = [f"{name}.{i + 1}" for i in range(capacity)]
    if not units:
        raise ValueError(f"E_INVALID_RESOURCE: pool {name!r} has no units")
    names = [u.name if isinstance(u, TaskExecuter) else (u if isinstance(u, str) else u.get("name"))
             for u in units]
    if len({n for n in names if n}) != len([n for n in names if n]):
        raise ValueError(f"E_INVALID_RESOURCE: duplicate unit names in pool {name!r}")
    made: List[Any] = []
    for i, unit in enumerate(units):
        if isinstance(unit, TaskExecuter):
            if unit.model is not model or unit.pool is not None:
                raise ValueError(f"E_INVALID_RESOURCE: {unit.name!r} belongs to another model or pool")
            made.append(unit)
        elif isinstance(unit, str):
            made.append(Operator(unit, model))
        elif isinstance(unit, dict):
            made.append(Operator(unit.get("name") or f"{name}.{i + 1}", model, skills=unit.get("skills", ()),
                                 attributes=unit.get("attributes"), speed=unit.get("speed", 1.0),
                                 location=unit.get("location")))
        else:
            raise TypeError(f"E_INVALID_RESOURCE: unit {unit!r} of pool {name!r}")
    return made


class ResourcePool:
    """A team of task executers (operators, robots, tools...) shared by several elements, plus
    the list where its idle units are published (``pool.list``, named ``"<name>.available"``).

    ``capacity`` creates identical :class:`~PyFlow.executers.Operator` units; ``units`` gives
    them names, skills and attributes (``"R1"`` or ``{"name": "R1", "skills": ["weld"],
    "attributes": {"level": 2}}``) or passes executers built by the user. ``kind`` is a free
    label for reports. ``unit_order``: ``ORDER BY`` used to choose among the idle units (default
    ``"skills_count ASC, index ASC"``; e.g. ``"utilization ASC"`` to balance the work,
    ``"idle_time DESC"`` for the longest idle)."""

    def __init__(self, name: str, model: Any, capacity: Optional[int] = None, *,
                 units: Optional[Sequence[Any]] = None, kind: str = "resource",
                 unit_order: Optional[str] = DEFAULT_UNIT_ORDER):
        from .lists import ModelList
        from .model import Model
        self.name = name
        self.kind = kind
        if not isinstance(model, Model):
            raise TypeError(f"E_INVALID_MODEL: {name!r} needs a Model, got {type(model).__name__}")
        self.model = model
        if name in model.resources.pools:
            raise ValueError(f"E_DUPLICATE_RESOURCE: a pool named {name!r} already exists")
        self.unit_order = unit_order
        self._unit_query = Query.of(unit_order)
        self.list = ModelList(f"{name}.available", model)
        self.units: List[Any] = _make_units(self, capacity, units)
        for i, unit in enumerate(self.units):
            unit.index, unit.pool = i, self
        self.busy = StatTimeWeightedVariable()      # units held by requests
        self.queue = StatTimeWeightedVariable()     # requests waiting for this pool
        self._reset_counters()
        self.model.resources.add_pool(self)

    def __repr__(self) -> str:
        return f"ResourcePool({self.name!r}, kind={self.kind!r}, units={len(self.units)}, free={self.free_count()})"

    @property
    def capacity(self) -> int:
        return len(self.units)

    def units_with(self, skill: Optional[str]) -> List[Any]:
        return [u for u in self.units if skill is None or skill in u.skills]

    # ------------------------------------------------------------------ the list of idle units
    def _unit_available(self, unit: Any) -> None:
        if not self.list.contains(unit):
            self.list.push(unit, origin=unit)
        self.model.resources._schedule_serve()

    def _unit_unavailable(self, unit: Any) -> None:
        self.list.remove(unit)

    def pick(self, quantity: int, skill: Optional[str], exclude=(), where: Optional[Query] = None,
             context: Optional[Dict[str, Any]] = None) -> List[Any]:
        """Idle units for a request, taken from the list: filtered by skill and ``where``, ranked
        by ``unit_order`` (ties: their order in the list)."""
        free = [u for u in self.list.values
                if (skill is None or skill in u.skills) and u.is_available and u not in exclude]
        if where is not None:
            free = [u for u in free if where.matches(_UnitScope(u, context))]
        if self._unit_query.has_order:
            free.sort(key=lambda u: self._unit_query.sort_key(_UnitScope(u, context)))
        return free[:quantity]

    def free_count(self, skill: Optional[str] = None) -> int:
        return sum(1 for u in self.list.values if (skill is None or skill in u.skills) and u.is_available)

    # ------------------------------------------------------------------ statistics
    def _reset_counters(self) -> None:
        self.requests = 0
        self.grants = 0
        self.wait_count = 0
        self.wait_total = 0.0
        self.wait_max = 0.0

    def _clear(self, t: float) -> None:
        """New run (the units reset themselves when the model starts them)."""
        self.busy.reset(t, 0.0)
        self.queue.reset(t, 0.0)
        self._reset_counters()

    def _reset_stats(self, t: float) -> None:
        """End of the warm-up: keep the current levels, drop what was collected."""
        self.busy.reset(t)
        self.queue.reset(t)
        self._reset_counters()

    def utilization(self, t: Optional[float] = None) -> float:
        t = self.model.now if t is None else t
        return self.busy.average(t) / self.capacity

    def unit_utilization(self, t: Optional[float] = None) -> Dict[str, float]:
        t = self.model.now if t is None else t
        return {u.name: u.busy.average(t) for u in self.units}


class ResourceRequirement:
    """``quantity`` units of ``pool`` (with ``skill`` if given, and matching ``where``) during a
    phase. ``where`` is an expression over the unit fields plus ``item`` and ``element``."""

    __slots__ = ("pool", "quantity", "during", "skill", "where", "_where")

    def __init__(self, pool: ResourcePool, quantity: int = 1, *, during: str = "both", skill: Optional[str] = None,
                 where: Optional[str] = None):
        if not isinstance(pool, ResourcePool):
            raise TypeError(f"E_INVALID_RESOURCE: expected a ResourcePool, got {type(pool).__name__}")
        if during not in DURING:
            raise ValueError(f"E_INVALID_RESOURCE: during={during!r}; use one of {DURING}")
        if quantity < 1:
            raise ValueError("E_INVALID_RESOURCE: quantity must be >= 1")
        available = len(pool.units_with(skill))
        if quantity > available:
            what = f"units with skill {skill!r}" if skill else "units"
            raise ValueError(f"E_RESOURCE_INSUFFICIENT: {quantity} unit(s) of {pool.name!r} requested but the "
                             f"pool has {available} {what}: the request could never be served")
        self.pool = pool
        self.quantity = quantity
        self.during = during
        self.skill = skill
        self.where = where
        self._where = Query(where=where, text=where) if where else None

    def needed_in(self, phase: str) -> bool:
        return self.during == "both" or self.during == phase

    def __repr__(self) -> str:
        skill = f", skill={self.skill!r}" if self.skill else ""
        return f"ResourceRequirement({self.pool.name!r}, {self.quantity}, during={self.during!r}{skill})"


def as_requirements(resources: Optional[Sequence[Union[ResourcePool, ResourceRequirement]]]) -> List[ResourceRequirement]:
    """A pool alone means one unit of it during the whole service."""
    result = []
    for r in resources or ():
        result.append(r if isinstance(r, ResourceRequirement) else ResourceRequirement(r))
    return result


class Allocation:
    """Units granted to one holder for a set of requirements."""

    __slots__ = ("holder", "parts")

    def __init__(self, holder: Any):
        self.holder = holder
        self.parts: List[tuple] = []     # (requirement, [units])

    @property
    def requirements(self) -> List[ResourceRequirement]:
        return [req for req, _ in self.parts]

    def holds(self, requirement: ResourceRequirement) -> bool:
        return any(req is requirement for req, _ in self.parts)

    def units(self) -> List[Any]:
        return [u for _, units in self.parts for u in units]


class ResourceRequest:
    """A pending request (see :meth:`ResourceManager.request`)."""

    __slots__ = ("manager", "requirements", "holder", "priority", "on_granted", "seq", "time", "granted",
                 "cancelled", "item", "kind")

    def __init__(self, manager, requirements, holder, priority, on_granted, seq, time, item=None, kind="work"):
        self.manager = manager
        self.requirements = requirements
        self.holder = holder
        self.priority = priority
        self.on_granted = on_granted
        self.seq = seq
        self.time = time
        self.granted = False
        self.cancelled = False
        self.item = item
        self.kind = kind

    @property
    def element_name(self) -> Optional[str]:
        target = getattr(self.holder, "target", self.holder)     # downtime generators repair their target
        return getattr(target, "name", None)

    def context(self) -> Dict[str, Any]:
        return {"item": self.item, "element": self.element_name}

    def expression_field(self, name: str) -> Any:
        if name == "age":
            return self.manager.model.now - self.time
        if name == "element":
            return self.element_name
        if name == "quantity":
            return sum(r.quantity for r in self.requirements)
        if name in ("priority", "time", "seq", "kind", "item"):
            return getattr(self, name)
        raise KeyError(name)


class _FieldScope(Mapping):
    """Names = the fields of one object (``expression_field``) plus extra context names."""

    __slots__ = ("obj", "extra")

    def __init__(self, obj: Any, extra: Optional[Dict[str, Any]] = None):
        self.obj, self.extra = obj, extra or {}

    def __getitem__(self, name: str) -> Any:
        if name in self.extra:
            return self.extra[name]
        return self.obj.expression_field(name)

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0


def _UnitScope(unit: Any, context: Optional[Dict[str, Any]]) -> _FieldScope:
    return _FieldScope(unit, context)


class ResourceManager:
    """Pools of one model and the queue of waiting requests (``model.resources``)."""

    def __init__(self, model: Any):
        self.model = model
        self.pools: Dict[str, ResourcePool] = {}
        self.pending: List[ResourceRequest] = []
        self._seq = 0
        self._serve_scheduled = False
        self._releasing = False
        self.configure(request_order=DEFAULT_REQUEST_ORDER, discipline="first_fit")

    def configure(self, *, request_order: Optional[str] = None, discipline: Optional[str] = None) -> None:
        """Change the rules: ``request_order`` (``ORDER BY`` over request fields) and
        ``discipline`` (``"first_fit"`` | ``"strict"``). Takes effect at the next grant."""
        if request_order is not None:
            self._request_query = Query.of(request_order)
            self.request_order = request_order
        if discipline is not None:
            if discipline not in DISCIPLINES:
                raise ValueError(f"E_INVALID_RESOURCE: discipline={discipline!r}; use one of {DISCIPLINES}")
            self.discipline = discipline

    def _rank(self, req: ResourceRequest):
        try:
            return self._request_query.sort_key(_FieldScope(req))
        except KeyError as exc:
            raise QueryError(f"E_QUERY_FAILED: request_order {self.request_order!r}: unknown name "
                             f"{exc.args[0]!r}") from None

    def _ordered_pending(self) -> List[ResourceRequest]:
        if not self._request_query.has_order:
            return list(self.pending)
        return sorted(self.pending, key=self._rank)        # stable: ties keep request order

    def add_pool(self, pool: ResourcePool) -> None:
        if pool.name in self.pools:
            raise ValueError(f"E_DUPLICATE_RESOURCE: a pool named {pool.name!r} already exists")
        self.pools[pool.name] = pool

    def __getitem__(self, name: str) -> ResourcePool:
        return self.pools[name]

    def __iter__(self):
        return iter(self.pools.values())

    def __len__(self) -> int:
        return len(self.pools)

    # ------------------------------------------------------------------ lifecycle
    def clear(self, t: float) -> None:
        self.pending.clear()
        self._seq = 0
        self._serve_scheduled = False
        for pool in self.pools.values():
            pool._clear(t)

    def reset_stats(self, t: float) -> None:
        for pool in self.pools.values():
            pool._reset_stats(t)

    # ------------------------------------------------------------------ requests
    def request(self, requirements: Sequence[ResourceRequirement], holder: Any,
                on_granted: Callable[[Allocation], Any], *, priority: float = 0, item: Any = None,
                kind: str = "work") -> ResourceRequest:
        """Ask for every requirement at once. ``on_granted(allocation)`` is called as soon
        as they can all be served (immediately if the rules allow it)."""
        now = self.model.now
        req = ResourceRequest(self, list(requirements), holder, priority, on_granted, self._seq, now, item, kind)
        self._seq += 1
        for pool in {r.pool for r in req.requirements}:
            pool.requests += 1
        # Waiting requests could not be served at their last chance, so with first_fit a new
        # request that fits now takes no units anyone else could use. With strict it must
        # also rank before every waiting request.
        if self._can_serve(req) and (self.discipline == "first_fit" or not self._ranked_behind(req)):
            self._grant(req, deferred=False)
        else:
            self.pending.append(req)
            for pool in {r.pool for r in req.requirements}:
                pool.queue.update(1, now)
        return req

    def _ranked_behind(self, req: ResourceRequest) -> bool:
        if not self.pending:
            return False
        if not self._request_query.has_order:
            return True                      # FIFO: everyone waiting arrived earlier
        key = self._rank(req)
        return any(not (key < self._rank(other)) for other in self.pending)

    def cancel(self, req: ResourceRequest) -> bool:
        if req.granted or req.cancelled:
            return False
        req.cancelled = True
        if req in self.pending:
            self.pending.remove(req)
            for pool in {r.pool for r in req.requirements}:
                pool.queue.update(-1, self.model.now)
        return True

    def release(self, allocation: Allocation) -> None:
        if not allocation.parts:
            return
        now = self.model.now
        parts, allocation.parts = allocation.parts, []
        for requirement, units in parts:
            requirement.pool.busy.update(-len(units), now)
        self._releasing = True
        try:
            for _, units in parts:
                for unit in units:
                    unit.free()            # back to the pool's list (if not stopped)
        finally:
            self._releasing = False
        self._serve_pending()

    def _schedule_serve(self) -> None:
        """A unit became available outside a release (start, resume, end of a task sequence):
        serve the waiting requests in a dt = 0 event."""
        if self._releasing or self._serve_scheduled or not self.pending:
            return
        self._serve_scheduled = True

        def serve():
            self._serve_scheduled = False
            self._serve_pending()
        self.model.schedule(serve, 0.0)

    def release_part(self, allocation: Allocation, requirements: Iterable[ResourceRequirement]) -> None:
        """Release only the units held for ``requirements`` (end of a phase)."""
        targets = list(requirements)
        part = Allocation(allocation.holder)
        part.parts = [(req, units) for req, units in allocation.parts if any(req is t for t in targets)]
        allocation.parts = [(req, units) for req, units in allocation.parts if not any(req is t for t in targets)]
        self.release(part)

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _can_serve(req: ResourceRequest) -> bool:
        # Two requirements on the same pool must be served by different units
        taken: Dict[ResourcePool, list] = {}
        context = req.context()
        for r in req.requirements:
            used = taken.setdefault(r.pool, [])
            units = r.pool.pick(r.quantity, r.skill, used, r._where, context)
            if len(units) < r.quantity:
                return False
            used.extend(units)
        return True

    def _grant(self, req: ResourceRequest, deferred: bool = True) -> None:
        """Reserve the units now; a waiting request is told in a dt = 0 event (``deferred``),
        like the back-orders of lists."""
        now = self.model.now
        allocation = Allocation(req.holder)
        context = req.context()
        for r in req.requirements:
            units = r.pool.pick(r.quantity, r.skill, (), r._where, context)
            for unit in units:
                r.pool.list.remove(unit)
                unit.hold(req.holder)
            r.pool.busy.update(len(units), now)
            allocation.parts.append((r, units))
        req.granted = True
        wait = now - req.time
        for pool in {r.pool for r in req.requirements}:
            pool.grants += 1
            pool.wait_count += 1
            pool.wait_total += wait
            pool.wait_max = max(pool.wait_max, wait)
        if deferred:
            self.model.schedule(lambda: req.on_granted(allocation), 0.0)
        else:
            req.on_granted(allocation)

    def _serve_pending(self) -> None:
        granted = True
        while granted and self.pending:
            granted = False
            for req in self._ordered_pending():
                if self._can_serve(req):
                    self.pending.remove(req)
                    for pool in {r.pool for r in req.requirements}:
                        pool.queue.update(-1, self.model.now)
                    self._grant(req)       # may release or request again: rescan from the start
                    granted = True
                    break
                if self.discipline == "strict":
                    return


class ResourceUser:
    """Mixin for elements with active service time. The element keeps one :class:`Allocation`
    per service slot (``process.allocation``) and calls:

    * ``_acquire(process, phase, then)`` before starting ``phase`` ("setup" / "processing");
    * ``_end_phase(process, phase)`` when the phase ends (frees phase-only units, and with
      ``release="on_finish"`` everything at the end of the processing);
    * ``_release_all(process)`` when the item has left (``release="on_exit"``).
    """

    def _init_resources(self, resources, release: str) -> None:
        if release not in RELEASE:
            raise ValueError(f"E_INVALID_RESOURCE: resource_release={release!r}; use one of {RELEASE}")
        self.resource_requirements: List[ResourceRequirement] = as_requirements(resources)
        self.resource_release = release
        for req in self.resource_requirements:
            if req.pool.model is not self.model:
                raise ValueError(f"E_INVALID_RESOURCE: pool {req.pool.name!r} belongs to another model")
        for phase in ("setup", "processing"):
            needed: Dict[ResourcePool, int] = {}
            for req in self.resource_requirements:
                if req.needed_in(phase):
                    needed[req.pool] = needed.get(req.pool, 0) + req.quantity
            for pool, quantity in needed.items():
                if quantity > pool.capacity:
                    raise ValueError(f"E_RESOURCE_INSUFFICIENT: {self.name!r} needs {quantity} unit(s) of "
                                     f"{pool.name!r} at once ({phase}) but the pool has {pool.capacity}")

    def _acquire(self, process: Any, phase: str, then: Callable[[], Any]) -> None:
        allocation = getattr(process, "allocation", None)
        if allocation is None:
            allocation = process.allocation = Allocation(self)
        missing = [r for r in self.resource_requirements if r.needed_in(phase) and not allocation.holds(r)]
        if not missing:
            then()
            return
        process.phase = "waiting"

        def granted(new: Allocation, process=process, then=then) -> None:
            process.request = None
            process.allocation.parts.extend(new.parts)
            then()
            self._refresh_state()

        item = process.get_item()
        process.request = self.model.resources.request(missing, self, granted,
                                                       priority=getattr(item, "priority", 0) or 0, item=item)

    def _end_phase(self, process: Any, phase: str) -> None:
        allocation = getattr(process, "allocation", None)
        if allocation is None or not allocation.parts:
            return
        if phase == "processing" and self.resource_release == "on_finish":
            self.model.resources.release(allocation)
        elif phase == "setup":
            self.model.resources.release_part(allocation, [r for r in allocation.requirements if r.during == "setup"])

    def _release_all(self, process: Any) -> None:
        allocation = getattr(process, "allocation", None)
        if allocation is not None and allocation.parts:
            self.model.resources.release(allocation)


__all__ = ["ResourcePool", "ResourceRequirement", "ResourceManager", "Allocation",
           "ResourceRequest", "ResourceUser", "as_requirements", "DURING", "RELEASE", "DISCIPLINES",
           "DEFAULT_REQUEST_ORDER", "DEFAULT_UNIT_ORDER"]
