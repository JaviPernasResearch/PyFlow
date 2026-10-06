"""Task executers: resources with identity that carry out task sequences (FlexSim / SimuLean).

A :class:`TaskExecuter` is an element of the engine (states, statistics, stops and shifts like
any element) that executes :class:`TaskSequence` objects, one task after another:

    seq = TaskSequence([Travel(distance=20), Load(item, time=1), Travel(distance=35),
                        Unload(time=1, on_done=deliver), Callback(log)], priority=2)
    forklift.execute(seq)

Tasks: :class:`Travel` (time, or distance / speed), :class:`Load` / :class:`Unload` (cargo),
:class:`Utilize` (work for a time, or until :meth:`TaskExecuter.release`), :class:`Wait` (same,
shown as WAITING) and :class:`Callback` (instant). Timed tasks are pausable work: a breakdown or
a shift of the executer pauses them.

Work reaches executers in two directions, both through lists:

* **the work waits for a resource**: a :class:`~PyFlow.resources.ResourcePool` publishes its
  idle executers in a list and stations take them with a query (see :mod:`PyFlow.resources`);
* **the resource waits for work**: ``executer.serve(task_list, query)`` makes an idle executer
  pull task sequences pushed to a :class:`~PyFlow.lists.ModelList`.

:class:`Operator` is the executer used by resource pools: it *works at the station* (an open
``Utilize``) while a station holds it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Sequence, Union

from .Elements.element import Element
from .states import ElementState
from .Statistics.statTimeWeightedVariable import StatTimeWeightedVariable

if TYPE_CHECKING:
    from .model import Model

Duration = Union[None, float, Callable[["TaskExecuter"], float]]


def _duration(value: Duration, executer: "TaskExecuter") -> Optional[float]:
    if value is None:
        return None
    d = value(executer) if callable(value) else float(value)
    if not d >= 0:
        raise ValueError(f"E_NEGATIVE_DELAY: task duration {d!r}")
    return d


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class Task:
    """Base task. ``begin(executer)`` returns the duration (``None``: until released) and the
    state shown meanwhile; ``finish(executer)`` applies the effect."""
    state = ElementState.WORKING

    def __init__(self, *, on_done: Optional[Callable[["TaskExecuter", "Task"], Any]] = None):
        self.on_done = on_done

    def begin(self, executer: "TaskExecuter"):
        return 0.0, self.state

    def finish(self, executer: "TaskExecuter") -> None:
        pass

    def __repr__(self) -> str:
        return type(self).__name__


class Travel(Task):
    """Move (to ``to``, a location label or network node). Duration: ``time``, or ``distance``
    / executer speed (0 if neither). Shown as TRAVEL_LOADED with cargo, TRAVEL_EMPTY otherwise."""

    def __init__(self, to: Any = None, *, time: Duration = None, distance: Optional[float] = None, **kw):
        super().__init__(**kw)
        self.to, self.time, self.distance = to, time, distance

    def begin(self, executer):
        if self.time is not None:
            d = _duration(self.time, executer)
        elif self.distance is not None:
            d = self.distance / executer.speed
        else:
            d = 0.0
        state = ElementState.TRAVEL_LOADED if executer.cargo else ElementState.TRAVEL_EMPTY
        return d, state

    def finish(self, executer):
        if self.distance is not None:
            executer.distance_travelled += self.distance
        if self.to is not None:
            executer.location = self.to


class Load(Task):
    """Take ``item`` into the executer's cargo after ``time`` (LOADING)."""
    state = ElementState.LOADING

    def __init__(self, item: Any, *, time: Duration = 0.0, **kw):
        super().__init__(**kw)
        self.item, self.time = item, time

    def begin(self, executer):
        if len(executer.cargo) >= executer.capacity:
            raise ValueError(f"E_CARGO_FULL: {executer.name} carries {len(executer.cargo)} of {executer.capacity}")
        return _duration(self.time, executer), self.state

    def finish(self, executer):
        executer.cargo.append(self.item)


class Unload(Task):
    """Take ``item`` (default: the first carried) out of the cargo after ``time`` (UNLOADING).
    ``on_done(executer, task)`` can hand ``task.item`` to an element."""
    state = ElementState.UNLOADING

    def __init__(self, item: Any = None, *, time: Duration = 0.0, **kw):
        super().__init__(**kw)
        self.item, self.time = item, time

    def begin(self, executer):
        return _duration(self.time, executer), self.state

    def finish(self, executer):
        if self.item is None:
            if not executer.cargo:
                raise ValueError(f"E_CARGO_EMPTY: {executer.name} has nothing to unload")
            self.item = executer.cargo[0]
        executer.cargo.remove(self.item)


class Utilize(Task):
    """Work for ``time``, or until :meth:`TaskExecuter.release` if ``time`` is ``None``."""

    def __init__(self, time: Duration = None, *, state: str = ElementState.WORKING, **kw):
        super().__init__(**kw)
        self.time, self.state = time, state

    def begin(self, executer):
        return _duration(self.time, executer), self.state


class Wait(Utilize):
    """Wait for ``time``, or until :meth:`TaskExecuter.release` (WAITING)."""

    def __init__(self, time: Duration = None, **kw):
        super().__init__(time, state=ElementState.WAITING, **kw)


class Callback(Task):
    """Call ``fn(executer)`` and go on at once."""

    def __init__(self, fn: Callable[["TaskExecuter"], Any], **kw):
        super().__init__(**kw)
        self.fn = fn

    def finish(self, executer):
        self.fn(executer)


class TaskSequence:
    """Tasks executed in order by one executer. ``priority`` and ``labels`` can be used in list
    queries; ``on_complete(executer, sequence)`` runs after the last task."""

    def __init__(self, tasks: Sequence[Task], *, priority: float = 0, name: Optional[str] = None,
                 labels: Optional[Dict[str, Any]] = None,
                 on_complete: Optional[Callable[["TaskExecuter", "TaskSequence"], Any]] = None):
        self.tasks: List[Task] = list(tasks)
        self.priority = priority
        self.name = name
        self.labels = dict(labels or {})
        self.on_complete = on_complete
        self.executer: Optional[TaskExecuter] = None
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

    def expression_field(self, name: str) -> Any:
        if name in ("priority", "name", "started_at", "finished_at"):
            return getattr(self, name)
        if name == "tasks":
            return len(self.tasks)
        return self.labels.get(name)

    def __repr__(self) -> str:
        return f"TaskSequence({self.name or ''}{self.tasks})"


# ---------------------------------------------------------------------------
# Executers
# ---------------------------------------------------------------------------

class TaskExecuter(Element):
    """A resource with identity: ``skills`` and ``attributes`` (for queries), ``speed`` (distance
    per time unit), ``location`` and cargo ``capacity``. Busy while it executes a sequence."""

    def __init__(self, name: str, model: "Model", *, skills: Iterable[str] = (),
                 attributes: Optional[Dict[str, Any]] = None, speed: float = 1.0, location: Any = None,
                 capacity: int = 1):
        super().__init__(name, model)
        if not speed > 0:
            raise ValueError(f"E_INVALID_RESOURCE: speed of {name!r} must be > 0")
        self.skills = frozenset(skills)
        self.attributes = dict(attributes or {})
        self.speed = speed
        self.home = location
        self.capacity = capacity
        self.pool = None              # set by a ResourcePool
        self.index = 0                # position in its pool
        self.busy = StatTimeWeightedVariable()
        self._served_lists: List[Any] = []
        self.on("stopped", lambda *_: self._on_stopped())
        self.on("resumed", lambda *_: self._on_resumed())
        self._reset_run()

    def _reset_run(self) -> None:
        self.location = self.home
        self.cargo: List[Any] = []
        self.current: Optional[TaskSequence] = None
        self.holder: Any = None       # who holds it (resource allocations)
        self.idle_since = 0.0
        self.sequences_completed = 0
        self.tasks_completed = 0
        self.distance_travelled = 0.0
        self._task_index = 0
        self._open_task: Optional[Task] = None
        self._backorders: Dict[Any, Any] = {}

    # ------------------------------------------------------------------ element protocol
    def start(self) -> None:
        self._reset_run()
        self.busy.reset(self.clock.now, 0.0)
        self.idle_since = self.clock.now
        self._set_state(ElementState.IDLE)
        self._became_available()

    def receive(self, the_item) -> bool:
        return False

    def unblock(self) -> bool:
        return False

    def check_availability(self, the_item) -> bool:
        return False

    def get_queue_length(self) -> int:
        return len(self.cargo)

    def get_free_capacity(self) -> float:
        return 0

    def _has_pending_work(self) -> bool:
        # an executer is "working" (for after_current stops) while it executes a sequence
        return self.current is not None or bool(self._work)

    # ------------------------------------------------------------------ availability
    @property
    def is_available(self) -> bool:
        return self.current is None and self.holder is None and not self._input_blocks

    def _became_available(self) -> None:
        if not self.is_available:
            return
        if self.pool is not None:
            self.pool._unit_available(self)
        for model_list, query in self._served_lists:
            self._pull_tasks(model_list, query)

    def _on_stopped(self) -> None:
        if self.pool is not None and self._input_blocks:
            self.pool._unit_unavailable(self)
        if self._input_blocks:
            for bo in list(self._backorders.values()):
                bo.cancel()
            self._backorders.clear()

    def _on_resumed(self) -> None:
        self._became_available()

    # ------------------------------------------------------------------ task lists
    def serve(self, task_list, query=None) -> None:
        """Pull task sequences from ``task_list`` whenever this executer is available."""
        self._served_lists.append((task_list, query))

    def _pull_tasks(self, task_list, query) -> None:
        bo = self._backorders.get(id(task_list))
        if bo is not None and bo.pending:
            return
        result = task_list.pull(query, puller=self, entries=True,
                                on_fulfilled=lambda entries, lst=task_list: self._got_tasks(lst, entries))
        if result.pending:
            self._backorders[id(task_list)] = result

    def _got_tasks(self, task_list, entries) -> None:
        self._backorders.pop(id(task_list), None)
        entry = entries[0]
        if not self.is_available:            # taken by something else meanwhile: give it back
            task_list.restore(entry)
            return
        self.execute(entry.value)

    # ------------------------------------------------------------------ execution
    def execute(self, sequence: TaskSequence) -> None:
        """Start ``sequence`` now (the executer must not be executing another one)."""
        if self.current is not None:
            raise RuntimeError(f"E_EXECUTER_BUSY: {self.name} is executing {self.current}")
        for bo in list(self._backorders.values()):
            bo.cancel()
        self._backorders.clear()
        now = self.clock.now
        self.current = sequence
        sequence.executer, sequence.started_at = self, now
        self._task_index = 0
        self.busy.set(1.0, now)
        self._next_task()

    def release(self) -> bool:
        """End the current open task (``Utilize`` / ``Wait`` without time)."""
        task = self._open_task
        if task is None:
            return False
        self._open_task = None
        self._end_task(task)
        return True

    def _next_task(self) -> None:
        sequence = self.current
        if sequence is None:
            return
        if self._task_index >= len(sequence.tasks):
            self._finish_sequence()
            return
        task = sequence.tasks[self._task_index]
        duration, state = task.begin(self)
        if not isinstance(task, Callback):
            self._set_state(state)
        if duration is None:
            self._open_task = task
        elif duration == 0 and isinstance(task, Callback):
            self._end_task(task)
        else:
            self.schedule_work(lambda task=task: self._end_task(task), duration)

    def _end_task(self, task: Task) -> None:
        task.finish(self)
        self.tasks_completed += 1
        if task.on_done is not None:
            task.on_done(self, task)
        self._task_index += 1
        self._next_task()

    def _finish_sequence(self) -> None:
        sequence, self.current = self.current, None
        now = self.clock.now
        sequence.finished_at = now
        self.sequences_completed += 1
        self.busy.set(0.0, now)
        self.idle_since = now
        self._set_state(ElementState.IDLE)
        if self._stops and self._shown_stop is None:
            self._refresh_down_state()       # an after_current stop now shows
        if sequence.on_complete is not None:
            sequence.on_complete(self, sequence)
        self._became_available()

    # ------------------------------------------------------------------ holding (resource pools)
    def hold(self, holder: Any, *, state: str = ElementState.WORKING) -> None:
        """Work for ``holder`` (e.g. at a station) until :meth:`free`: an open ``Utilize``."""
        self.holder = holder
        self.execute(TaskSequence([Utilize(state=state)], name=f"held by {getattr(holder, 'name', holder)}"))

    def free(self) -> None:
        self.holder = None
        self.release()

    def _on_stats_reset(self, t: float) -> None:
        self.busy.reset(t)
        self.sequences_completed = self.tasks_completed = 0
        self.distance_travelled = 0.0

    # ------------------------------------------------------------------ queries and reports
    def expression_field(self, name: str) -> Any:
        now = self.clock.now
        if name == "skills_count":
            return len(self.skills)
        if name == "busy_time":
            return self.busy.average(now) * (now - self.busy.t0)
        if name == "utilization":
            return self.busy.average(now)
        if name == "idle_time":
            return now - self.idle_since if self.current is None else 0.0
        if name == "kind":
            return self.pool.kind if self.pool is not None else type(self).__name__
        if name in ("index", "skills", "idle_since", "location", "speed", "capacity", "holder",
                    "sequences_completed", "tasks_completed", "distance_travelled"):
            return getattr(self, name)
        if name == "cargo":
            return len(self.cargo)
        if name in self.attributes:
            return self.attributes[name]
        return super().expression_field(name)

    def summary(self) -> Dict[str, Any]:
        now = self.clock.now
        return {"name": self.name, "state": self.state, "utilization": self.busy.average(now),
                "state_ratios": {s: round(r, 12) for s, r in self.state_ratios().items()},
                "sequences_completed": self.sequences_completed, "tasks_completed": self.tasks_completed,
                "distance_travelled": self.distance_travelled}

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r}, state={self.state}, busy={self.current is not None})"


class Operator(TaskExecuter):
    """Executer that works at the station that holds it: the default unit of a
    :class:`~PyFlow.resources.ResourcePool` (operators, robots, tools...)."""


__all__ = ["TaskExecuter", "Operator", "TaskSequence", "Task", "Travel", "Load", "Unload", "Utilize", "Wait",
           "Callback"]
