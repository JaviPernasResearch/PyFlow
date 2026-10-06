"""Shared resources: operators, robots, tools, fixtures... anything an element needs while it works.

A :class:`ResourcePool` holds interchangeable *units*, optionally with skills. Elements with
active service time (``MultiServer``, ``Combiner``, ``MultiAssembler`` and any element using
:class:`ResourceUser`) declare what they need with :class:`ResourceRequirement`:

    welders = ResourcePool("Welders", model, capacity=2, kind="operator")
    robots  = ResourcePool("Robots", model, units=[{"name": "R1", "skills": ["weld", "paint"]},
                                                   {"name": "R2", "skills": ["paint"]}], kind="robot")
    weld = MultiServer(2, 5, "Weld", model,
                       resources=[welders, ResourceRequirement(robots, skill="weld", during="processing")])

Rules:

* A phase (``setup`` or ``processing``) starts only when *all* the requirements it needs are
  granted at once (no partial holding, so two elements cannot deadlock each other).
* Waiting requests are served by item priority (higher first), then in request order. On
  every release the queue is scanned in that order and every request that can be fully
  served is granted (a big request does not block smaller ones behind it).
* ``during="both"`` (default) holds the units from the start of the setup to the end of
  the processing; ``"setup"`` / ``"processing"`` only during that phase.
* ``release="on_finish"`` (default) frees the units when the processing ends, even if the
  item cannot leave; ``"on_exit"`` keeps them until the item has left the element.
* Among the idle units with the skill, the one with the fewest skills is chosen (ties: in
  declaration order), so versatile units stay available for the tasks only they can do.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Union

from .Statistics.statTimeWeightedVariable import StatTimeWeightedVariable

DURING = ("setup", "processing", "both")
RELEASE = ("on_finish", "on_exit")


class ResourceUnit:
    """One unit of a pool (an operator, a robot...)."""

    __slots__ = ("name", "skills", "holder", "busy")

    def __init__(self, name: str, skills: Iterable[str] = ()):
        self.name = name
        self.skills = frozenset(skills)
        self.holder: Any = None
        self.busy = StatTimeWeightedVariable()

    def __repr__(self) -> str:
        return f"ResourceUnit({self.name!r}, skills={sorted(self.skills)}, busy={self.holder is not None})"

    @property
    def is_free(self) -> bool:
        return self.holder is None


def _make_units(name: str, capacity: Optional[int], units: Optional[Sequence[Any]]) -> List[ResourceUnit]:
    if (capacity is None) == (units is None):
        raise ValueError(f"E_INVALID_RESOURCE: pool {name!r} needs exactly one of 'capacity' or 'units'")
    if units is None:
        if capacity < 1:
            raise ValueError(f"E_INVALID_RESOURCE: pool {name!r} capacity must be >= 1")
        return [ResourceUnit(f"{name}.{i + 1}") for i in range(capacity)]
    made: List[ResourceUnit] = []
    for i, unit in enumerate(units):
        if isinstance(unit, ResourceUnit):
            made.append(ResourceUnit(unit.name, unit.skills))
        elif isinstance(unit, str):
            made.append(ResourceUnit(unit))
        elif isinstance(unit, dict):
            made.append(ResourceUnit(unit.get("name") or f"{name}.{i + 1}", unit.get("skills", ())))
        else:
            raise TypeError(f"E_INVALID_RESOURCE: unit {unit!r} of pool {name!r}")
    if not made:
        raise ValueError(f"E_INVALID_RESOURCE: pool {name!r} has no units")
    if len({u.name for u in made}) != len(made):
        raise ValueError(f"E_INVALID_RESOURCE: duplicate unit names in pool {name!r}")
    return made


class ResourcePool:
    """A set of units shared by several elements. ``capacity`` creates anonymous units;
    ``units`` gives them names and skills (``"R1"`` or ``{"name": "R1", "skills": ["weld"]}``).
    ``kind`` is a free label for reports ("operator", "robot", "tool"...)."""

    def __init__(self, name: str, model: Any, capacity: Optional[int] = None, *,
                 units: Optional[Sequence[Any]] = None, kind: str = "resource"):
        from .model import resolve_model
        self.name = name
        self.kind = kind
        self.model = resolve_model(model)
        self.units: List[ResourceUnit] = _make_units(name, capacity, units)
        self.busy = StatTimeWeightedVariable()      # units in use
        self.queue = StatTimeWeightedVariable()     # requests waiting for this pool
        self._reset_counters()
        self.model.resources.add_pool(self)

    def __repr__(self) -> str:
        return f"ResourcePool({self.name!r}, kind={self.kind!r}, units={len(self.units)}, free={self.free_count()})"

    @property
    def capacity(self) -> int:
        return len(self.units)

    def units_with(self, skill: Optional[str]) -> List[ResourceUnit]:
        return [u for u in self.units if skill is None or skill in u.skills]

    def pick(self, quantity: int, skill: Optional[str], exclude=()) -> List[ResourceUnit]:
        """Idle units for a request: fewest skills first, then declaration order."""
        free = [u for u in self.units_with(skill) if u.is_free and u not in exclude]
        free.sort(key=lambda u: len(u.skills))     # stable: keeps declaration order on ties
        return free[:quantity]

    def free_count(self, skill: Optional[str] = None) -> int:
        return sum(1 for u in self.units_with(skill) if u.is_free)

    # ------------------------------------------------------------------ statistics
    def _reset_counters(self) -> None:
        self.requests = 0
        self.grants = 0
        self.wait_count = 0
        self.wait_total = 0.0
        self.wait_max = 0.0

    def _clear(self, t: float) -> None:
        """New run: every unit free, no statistics."""
        for unit in self.units:
            unit.holder = None
            unit.busy.reset(t, 0.0)
        self.busy.reset(t, 0.0)
        self.queue.reset(t, 0.0)
        self._reset_counters()

    def _reset_stats(self, t: float) -> None:
        """End of the warm-up: keep the current levels, drop what was collected."""
        for unit in self.units:
            unit.busy.reset(t)
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
    """``quantity`` units of ``pool`` (with ``skill`` if given) during a phase."""

    __slots__ = ("pool", "quantity", "during", "skill")

    def __init__(self, pool: ResourcePool, quantity: int = 1, *, during: str = "both", skill: Optional[str] = None):
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

    def units(self) -> List[ResourceUnit]:
        return [u for _, units in self.parts for u in units]


class ResourceRequest:
    """A pending request (see :meth:`ResourceManager.request`)."""

    __slots__ = ("requirements", "holder", "priority", "on_granted", "seq", "time", "granted", "cancelled")

    def __init__(self, requirements, holder, priority, on_granted, seq, time):
        self.requirements = requirements
        self.holder = holder
        self.priority = priority
        self.on_granted = on_granted
        self.seq = seq
        self.time = time
        self.granted = False
        self.cancelled = False


class ResourceManager:
    """Pools of one model and the queue of waiting requests (``model.resources``)."""

    def __init__(self, model: Any):
        self.model = model
        self.pools: Dict[str, ResourcePool] = {}
        self.pending: List[ResourceRequest] = []
        self._seq = 0

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
        for pool in self.pools.values():
            pool._clear(t)

    def reset_stats(self, t: float) -> None:
        for pool in self.pools.values():
            pool._reset_stats(t)

    # ------------------------------------------------------------------ requests
    def request(self, requirements: Sequence[ResourceRequirement], holder: Any,
                on_granted: Callable[[Allocation], Any], *, priority: float = 0) -> ResourceRequest:
        """Ask for every requirement at once. ``on_granted(allocation)`` is called as soon
        as they can all be served (immediately if possible)."""
        now = self.model.now
        req = ResourceRequest(list(requirements), holder, priority, on_granted, self._seq, now)
        self._seq += 1
        for pool in {r.pool for r in req.requirements}:
            pool.requests += 1
        # Waiting requests could not be served at their last chance, so a new request that
        # fits now does not overtake anyone who could have used these units.
        if self._can_serve(req):
            self._grant(req)
        else:
            self.pending.append(req)
            self.pending.sort(key=lambda r: (-r.priority, r.seq))
            for pool in {r.pool for r in req.requirements}:
                pool.queue.update(1, now)
        return req

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
        for requirement, units in allocation.parts:
            for unit in units:
                unit.holder = None
                unit.busy.set(0.0, now)
            requirement.pool.busy.update(-len(units), now)
        allocation.parts.clear()
        self._serve_pending()

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
        for r in req.requirements:
            used = taken.setdefault(r.pool, [])
            units = r.pool.pick(r.quantity, r.skill, used)
            if len(units) < r.quantity:
                return False
            used.extend(units)
        return True

    def _grant(self, req: ResourceRequest) -> None:
        now = self.model.now
        allocation = Allocation(req.holder)
        for r in req.requirements:
            units = r.pool.pick(r.quantity, r.skill)
            for unit in units:
                unit.holder = req.holder
                unit.busy.set(1.0, now)
            r.pool.busy.update(len(units), now)
            allocation.parts.append((r, units))
        req.granted = True
        wait = now - req.time
        for pool in {r.pool for r in req.requirements}:
            pool.grants += 1
            pool.wait_count += 1
            pool.wait_total += wait
            pool.wait_max = max(pool.wait_max, wait)
        req.on_granted(allocation)

    def _serve_pending(self) -> None:
        i = 0
        while i < len(self.pending):
            req = self.pending[i]
            if self._can_serve(req):
                self.pending.pop(i)
                for pool in {r.pool for r in req.requirements}:
                    pool.queue.update(-1, self.model.now)
                self._grant(req)       # may release or request again: rescan from the start
                i = 0
            else:
                i += 1


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
                                                       priority=getattr(item, "priority", 0) or 0)

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


__all__ = ["ResourcePool", "ResourceUnit", "ResourceRequirement", "ResourceManager", "Allocation",
           "ResourceRequest", "ResourceUser", "as_requirements", "DURING", "RELEASE"]
