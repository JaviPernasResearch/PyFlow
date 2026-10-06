from collections import deque
from typing import Any, Deque, Dict, Optional, Sequence, Union

from ..Items.item import Item
from ..resources import ResourceUser
from ..SimClock.simClock import SimClock
from ..states import ElementState
from .element import Element
from .serverProcess import ServerProcess
from .workStation import WorkStation


class MultiServer(Element, WorkStation, ResourceUser):
    def __init__(self, num_servers: int, delay_strategy: Any, name: str, clock: SimClock, *,
                 setup_time: Union[None, Any, Dict[Any, Any]] = None,
                 resources: Optional[Sequence[Any]] = None, resource_release: str = "on_finish"):
        """
        Args:
            num_servers: number of parallel servers (capacity).
            delay_strategy: service time, any sampler specification (number, scipy.stats
                distribution, ``"Exponential~0.5"``, label expression, ``Sampler``).
            name: element name.
            clock: the ``Model`` (or its ``SimClock``).
            setup_time: changeover time applied when a server starts an item whose
                ``type`` differs from the previous item it processed (no setup for the first
                item). Either one sampler specification for every change, or a dict keyed by
                ``(from_type, to_type)`` and/or ``to_type`` (missing combinations: no setup).
            resources: what each server needs while it works: ``ResourcePool`` objects (one
                unit for the whole service) or ``ResourceRequirement`` (quantity, phase,
                skill). See :mod:`PyFlow.resources`.
            resource_release: ``"on_finish"`` frees the units when the processing ends;
                ``"on_exit"`` keeps them until the item has left (also while blocked).
        """
        super().__init__(name, clock)
        self.num_servers = num_servers
        self.delay_strategy = delay_strategy
        self.service_sampler = self._bind_sampler(delay_strategy, "service")
        self.setup_time = setup_time
        if setup_time is None:
            self._setup = None
        elif isinstance(setup_time, dict):
            self._setup = {key: self._bind_sampler(spec, f"setup.{key}") for key, spec in setup_time.items()}
        else:
            self._setup = self._bind_sampler(setup_time, "setup")

        self.idle_processes: Deque[ServerProcess] = deque()
        self.work_in_progress: Deque[ServerProcess] = deque()
        self.completed: Deque[ServerProcess] = deque()

        self.current_items = 0
        self.pending_requests = 0
        self.blockage_count = 0
        self._init_resources(resources, resource_release)

    def start(self) -> None:
        self.idle_processes.clear()
        self.work_in_progress.clear()
        self.completed.clear()

        for i in range(self.num_servers):
            the_process = ServerProcess(self, self.service_sampler)
            self.idle_processes.append(the_process)

        self.current_items = 0
        self.blockage_count = 0
        self._refresh_state()

    # ------------------------------------------------------------------ state
    def _refresh_state(self) -> None:
        """PROCESSING if any server works, else SETUP, else WAITING_FOR_RESOURCE, else BLOCKED
        (finished items waiting), else IDLE."""
        phases = {p.phase for p in self.work_in_progress}
        if "processing" in phases:
            state = ElementState.PROCESSING
        elif "setup" in phases:
            state = ElementState.SETUP
        elif "waiting" in phases:
            state = ElementState.WAITING_FOR_RESOURCE
        elif self.completed:
            state = ElementState.BLOCKED
        else:
            state = ElementState.IDLE
        self._set_state(state)

    def _setup_delay(self, previous_type, item: Item) -> float:
        if self._setup is None or previous_type is None or previous_type == item.type:
            return 0.0
        if isinstance(self._setup, dict):
            sampler = self._setup.get((previous_type, item.type), self._setup.get(item.type))
            return sampler.sample(item) if sampler is not None else 0.0
        return self._setup.sample(item)

    # ------------------------------------------------------------------ flow
    def unblock(self) -> bool:
        if self.completed:
            the_process = self.completed.popleft()
            the_item = the_process.get_item()

            if self.get_output().send(the_item):
                self._release_all(the_process)
                self.idle_processes.append(the_process)
                self.current_items -= 1
                self._refresh_state()
                self.get_input().notify_available()
                return True
            else:
                # Still blocked: keep the finished process (and its item) at the head
                self.completed.appendleft(the_process)
                return False
        else:
            return False

    def receive(self, the_item: Item) -> bool:
        if self.current_items >= self.num_servers:
            return False

        if not self.idle_processes:
            return False

        the_process = self.idle_processes.popleft()
        the_process.set_item(the_item)
        self.work_in_progress.append(the_process)

        self.current_items += 1

        setup = self._setup_delay(the_process.last_type, the_item)
        if setup > 0:
            self._acquire(the_process, "setup", lambda p=the_process: self._start_setup(p, setup))
        else:
            self._acquire(the_process, "processing", lambda p=the_process: self._start_service(p))
        self._refresh_state()
        return True

    def _start_setup(self, the_process: ServerProcess, setup: float) -> None:
        the_process.phase = "setup"
        the_process.work = self.schedule_work(lambda p=the_process: self._end_setup(p), setup)

    def _end_setup(self, the_process: ServerProcess) -> None:
        self._end_phase(the_process, "setup")
        self._acquire(the_process, "processing", lambda p=the_process: self._start_service(p))
        self._refresh_state()

    def _start_service(self, the_process: ServerProcess) -> None:
        the_process.phase = "processing"
        the_process.last_type = the_process.get_item().type
        delay = the_process.get_delay()
        the_process.work = self.schedule_work(the_process.execute, delay)

    def complete_server_process(self, the_process: ServerProcess) -> None:
        the_item = the_process.get_item()
        self.work_in_progress.remove(the_process)
        the_process.phase = None
        the_process.work = None
        self._end_phase(the_process, "processing")

        if self.get_output().send(the_item):
            self._release_all(the_process)
            self.idle_processes.append(the_process)
            self.current_items -= 1
            self._refresh_state()
            self.get_input().notify_available()
        else:
            self.blockage_count += 1
            self.completed.append(the_process)
            self._refresh_state()

    def check_availability(self, the_item: Item) -> bool:
        return not (self.current_items >= self.num_servers)

    def get_queue_length(self) -> int:
        return self.current_items

    def get_free_capacity(self) -> float:
        return self.num_servers - self.current_items
