"""``Model``: the simulation context (equivalent to SimuLean's ``SimContext``).

A model owns its clock, its element registry, its item counter, its random streams
and its parameters. Nothing is shared between models, so several of them can run in
the same process (MCP sessions, replications in parallel).

    model = Model(seed=42)
    src  = InterArrivalSource("Source", model, "Exponential~0.5")
    ...
    model.initialize()
    model.run(until=10_000, warmup=1_000)
"""
from __future__ import annotations

import logging
import zlib
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

import numpy as np

from .sampling import Sampler, as_sampler
from .simcalendar import SimCalendar
from .SimClock.simClock import EventHandle, SimClock

if TYPE_CHECKING:
    from .Elements.element import Element

logger = logging.getLogger("pyflow")


class Model:
    def __init__(self, seed: Optional[int] = None, *, name: str = "Model",
                 parameters: Optional[Dict[str, Any]] = None, calendar: Optional["SimCalendar"] = None,
                 _clock: Optional[SimClock] = None):
        self.name = name
        seed_seq = np.random.SeedSequence(seed)
        self.seed: int = seed_seq.entropy  # the actual seed, also when none was given
        self.parameters: Dict[str, Any] = dict(parameters or {})
        self.elements: List["Element"] = []
        self.pending_requests: Deque["Element"] = deque()  # origins waiting for space (GeneralLink)
        self._item_counter = 0
        self._samplers: List[Sampler] = []
        self._stream_keys: Dict[str, int] = {}
        self.stats_reset_time: float = 0.0
        self.generators: List[Any] = []  # downtime generators, started after the elements
        from .resources import ResourceManager
        self.resources = ResourceManager(self)  # shared resource pools (operators, robots...)
        self.lists: Dict[str, Any] = {}          # model lists (PyFlow.lists.ModelList) by name
        self.list_links: List[Any] = []          # elements pulling from lists (started last)
        self.calendar = calendar if calendar is not None else SimCalendar.default()
        self.clock: SimClock = _clock if _clock is not None else SimClock(model=self)

    def __repr__(self) -> str:
        return f"Model(name={self.name!r}, seed={self.seed}, elements={len(self.elements)}, now={self.now})"

    # ------------------------------------------------------------------ registry
    def add_element(self, element: "Element") -> None:
        from .Elements.element import Element
        if not isinstance(element, Element):
            raise TypeError("The element must be an instance of Element")
        if any(e.name == element.name for e in self.elements):
            logger.warning("Model %r: duplicate element name %r", self.name, element.name)
        self.elements.append(element)

    def get_element(self, name: str) -> "Element":
        for element in self.elements:
            if element.name == name:
                return element
        raise KeyError(f"E_UNKNOWN_ELEMENT: no element named {name!r} in model {self.name!r}")

    def add_list(self, model_list: Any) -> None:
        if model_list.name in self.lists:
            raise ValueError(f"E_DUPLICATE_LIST: a list named {model_list.name!r} already exists")
        self.lists[model_list.name] = model_list

    def add_list_link(self, link: Any) -> None:
        self.list_links.append(link)

    def add_generator(self, generator: Any) -> None:
        self.generators.append(generator)

    # ------------------------------------------------------------------ dates
    def to_datetime(self, t: Optional[float] = None):
        """Calendar date of simulation time ``t`` (default: now)."""
        return self.calendar.to_datetime(self.now if t is None else t)

    def to_sim_time(self, date) -> float:
        return self.calendar.to_sim_time(date)

    # ------------------------------------------------------------------ items
    def next_item_id(self) -> int:
        self._item_counter += 1
        return self._item_counter

    @property
    def items_created(self) -> int:
        return self._item_counter

    # ------------------------------------------------------------------ randomness
    def rng(self, key: str) -> np.random.Generator:
        """Independent random stream derived from the model seed and a stable ``key``.

        The stream depends only on ``(seed, key)``, not on creation order. A key used
        twice gets a suffix (``key#2``) so the two streams stay independent.
        """
        return np.random.Generator(np.random.PCG64(self._seed_sequence(key)))

    def _seed_sequence(self, key: str) -> np.random.SeedSequence:
        return np.random.SeedSequence(self.seed, spawn_key=(zlib.crc32(key.encode("utf-8")),))

    def _unique_key(self, key: str) -> str:
        n = self._stream_keys.get(key, 0) + 1
        self._stream_keys[key] = n
        return key if n == 1 else f"{key}#{n}"

    def bind_sampler(self, spec: Any, key: str, *, negative: Optional[str] = None) -> Sampler:
        """Turn ``spec`` into a :class:`Sampler` with its own stream from this model."""
        sampler = as_sampler(spec, negative=negative)
        if sampler.key is not None and sampler in self._samplers:
            return sampler  # the same sampler object shared by several elements keeps one stream
        key = self._unique_key(key)
        sampler.bind(self.rng(key), key)
        self._samplers.append(sampler)
        return sampler

    def _reseed_samplers(self) -> None:
        for sampler in self._samplers:
            sampler.bind(self.rng(sampler.key), sampler.key)

    # ------------------------------------------------------------------ time
    @property
    def now(self) -> float:
        return self.clock.sim_time

    def schedule(self, target: Any, delay: float) -> EventHandle:
        return self.clock.schedule_event(target, delay)

    def schedule_at(self, target: Any, time: float) -> EventHandle:
        return self.clock.schedule_at(target, time)

    def initialize(self) -> None:
        """Start a run: t = 0, empty calendar, fresh random streams and item ids,
        statistics reset, then ``start()`` every element in creation order.
        Events scheduled before this call are discarded: schedule interventions after it."""
        if self.clock.pending_events():
            logger.warning("Model %r: initialize() discarded %d pending event(s)",
                           self.name, self.clock.pending_events())
        self.clock.reset()
        self._item_counter = 0
        self.pending_requests.clear()
        self._reseed_samplers()
        self.stats_reset_time = 0.0
        self.resources.clear(0.0)
        for model_list in self.lists.values():
            model_list.clear(0.0)
        for element in self.elements:
            element.get_stats_collector().clear(0.0)
            element._reset_runtime()
        for element in self.elements:
            element.start()
        for generator in self.generators:  # after the elements: element start clears stops
            generator.start()
        for link in self.list_links:      # pullers ask for items once everything is ready
            link.start()

    def advance_clock(self, time: float) -> bool:
        return self.clock.advance_clock(time)

    def run(self, until: float, *, warmup: Optional[float] = None) -> bool:
        """Advance to ``until``. With ``warmup``, statistics are reset at that time.
        Returns ``True`` if events remain in the calendar."""
        if warmup is not None:
            if not 0 <= warmup <= until:
                raise ValueError(f"E_INVALID_WARMUP: warmup={warmup} must be within [0, until={until}]")
            if warmup < self.now:
                raise ValueError(f"E_INVALID_WARMUP: warmup={warmup} is already in the past (now={self.now})")
            self.clock.advance_clock(warmup)
            self.reset_stats()
        return self.clock.advance_clock(until)

    def reset_stats(self) -> None:
        """Discard the statistics collected so far (end of the warm-up period)."""
        for element in self.elements:
            element.get_stats_collector().reset(self.now)
            element._tracker.reset(self.now)
            element._on_stats_reset(self.now)
        for generator in self.generators:
            generator.reset_stats()
        self.resources.reset_stats(self.now)
        for model_list in self.lists.values():
            model_list.reset_stats(self.now)
        self.stats_reset_time = self.now



__all__ = ["Model"]
