from collections import deque
from typing import Any, List, Optional, Sequence, Union
from scipy import stats

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .multiServer import MultiServer
from .serverProcess import ServerProcess
from .constrainedInput import ConstrainedInput
from .arrivalListener import ArrivalListener



class MultiAssembler(MultiServer, ArrivalListener):
    def __init__(self, num_servers: int, requirements: List[int], delay_strategy:Union[stats.rv_continuous, stats.rv_discrete, str],
                  name: str, sim_clock: SimClock, batch_mode: bool = False, *,
                  resources: Optional[Sequence[Any]] = None, resource_release: str = "on_finish"):
        """
        Args:
            num_servers (int): The number of servers (capacity of the workstation).
            requirements (List[int]): A list of requirements for each constrained input.
            delay_strategy (Union[stats.rv_continuous, stats.rv_discrete, str]): The strategy for determining the delay. 
                This can be an instance of a Scipy distribution class or a string specifying the item label name to read the delay from.
            name (str): The name of the multi-assembler.
            sim_clock (SimClock): The simulation clock.
            batch_mode (bool): Optional. Whether batch mode is enabled. Default is False.
            resources / resource_release: shared resources needed while assembling (see
                :class:`MultiServer`).
        """
        super().__init__(num_servers, delay_strategy, name=name, clock=sim_clock, resources=resources,
                         resource_release=resource_release)

        self.requirements = requirements
        self.batch_mode = batch_mode
        self.delay_strategy= delay_strategy 
        self.inputs = [ConstrainedInput(requirements[i], self, i, f"{name}.Input{i}", self.clock) for i in range(len(requirements))]
        
        self.completed_items = 0
        self.receiving_items = False

    def start(self):
        self.idle_processes.clear()
        self.work_in_progress.clear()
        self.completed.clear()
        
        for _ in range(self.num_servers):
            the_process = ServerProcess(self, self.service_sampler)
            self.idle_processes.append(the_process)
        
        for input_port in self.inputs:
            input_port.start()
        
        self.completed_items = 0
        self._refresh_state()

    def is_main_receiving(self) -> bool:
        return True

    def get_component_input(self, i: int) -> ConstrainedInput:
        return self.inputs[i]

    def get_inputs_count(self) -> int:
        return len(self.inputs)

    def unblock(self) -> bool:
        if self.completed:
            the_process = self.completed.popleft()
            the_item = the_process.get_item()

            if self.get_output().send(the_item):
                self._release_all(the_process)
                self.idle_processes.append(the_process)
                self._refresh_state()
                self.check_requirements()
                return True
            else:
                self.completed.appendleft(the_process)
                return False
        return False

    def receive(self, the_item: Item) -> bool:
        # Components enter through get_component_input(i); the assembler itself has no input
        return False

    def component_received(self, the_item: Item, source: int):
        if not self.receiving_items:
            self.check_requirements()

    def check_requirements(self):
        if not self.idle_processes:
            return
        
        ready = all(input_port.get_queue_length() >= req for input_port, req in zip(self.inputs, self.requirements))
        
        if ready:
            self.completed_items += 1
            self.receiving_items = True
            new_item = self.create_new_item()
            the_process = self.idle_processes.popleft()

            for i, (input_port, req) in enumerate(zip(self.inputs, self.requirements)):
                items = input_port.release(req)
                for item in items:
                    if self.batch_mode:
                        new_item.add_item(item)
            
            self.receiving_items = False
            # The new item is inside the assembler from now on (content, stay time)
            self.get_stats_collector().on_entry(new_item)
            the_process.set_item(new_item)
            self.work_in_progress.append(the_process)

            self._acquire(the_process, "processing", lambda p=the_process: self._start_service(p))
            self._refresh_state()
            self.check_requirements()

    def create_new_item(self) -> Item:
        return self._new_item()

    def complete_server_process(self, the_process: ServerProcess):
        the_item = the_process.get_item()
        self.work_in_progress.remove(the_process)
        the_process.phase = None
        the_process.work = None
        self._end_phase(the_process, "processing")

        if self.get_output().send(the_item):
            self._release_all(the_process)
            self.idle_processes.append(the_process)
            self._refresh_state()
            self.check_requirements()

        else:
            self.blockage_count += 1
            self.completed.append(the_process)
            self._refresh_state()


    def check_availability(self, the_item: Item) -> bool:
        return False  # connect component flows to get_component_input(i)

    def get_queue_length(self) -> int:
        return len(self.work_in_progress) + len(self.completed)

    def get_free_capacity(self) -> float:
        return self.num_servers - self.get_queue_length()

    def get_items(self) -> deque:
        items = deque()
        for the_process in self.work_in_progress:
            items.append(the_process.get_item())
        for the_process in self.completed:
            items.append(the_process.get_item())
        return items
