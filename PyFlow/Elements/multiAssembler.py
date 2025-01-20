from collections import deque
from typing import List, Union
from scipy import stats

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .multiServer import MultiServer
from .serverProcess import ServerProcess
from .constrainedInput import ConstrainedInput
from .arrivalListener import ArrivalListener



class MultiAssembler(MultiServer, ArrivalListener):
    def __init__(self, num_servers: int, requirements: List[int], delay_strategy:Union[stats.rv_continuous, stats.rv_discrete, str],
                  name: str, sim_clock: SimClock, batch_mode: bool = False):
        """
        Args:
            num_servers (int): The number of servers (capacity of the workstation).
            requirements (List[int]): A list of requirements for each constrained input.
            delay_strategy (Union[stats.rv_continuous, stats.rv_discrete, str]): The strategy for determining the delay. 
                This can be an instance of a Scipy distribution class or a string specifying the item label name to read the delay from.
            name (str): The name of the multi-assembler.
            sim_clock (SimClock): The simulation clock.
            batch_mode (bool): Optional. Whether batch mode is enabled. Default is False.
        """
        super().__init__(num_servers,delay_strategy,name=name, clock=sim_clock)

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
            the_process = ServerProcess(self, self.delay_strategy)
            self.idle_processes.append(the_process)
        
        for input_port in self.inputs:
            input_port.start()
        
        self.completed_items = 0

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
                self.idle_processes.append(the_process)
                self.check_requirements()
                return True
            else:
                self.completed.appendleft(the_process)
                return False
        return False

    def receive(self, the_item: Item) -> bool:
        return True

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
            the_process.set_item(new_item)
            self.work_in_progress.append(the_process)

            delay_time = the_process.get_delay()
            self.clock.schedule_event(the_process, delay_time)
            self.check_requirements()

    def create_new_item(self) -> Item:
        new_item = Item(self.clock.get_simulation_time())
        return new_item

    def complete_server_process(self, the_process: ServerProcess):
        the_item = the_process.get_item()
        self.work_in_progress.remove(the_process)

        if self.get_output().send(the_item):
            self.idle_processes.append(the_process)
            self.check_requirements()

        else:
            self.completed.append(the_process)

        return self.complete_server_process

    def check_availability(self, the_item: Item) -> bool:
        return len(self.work_in_progress) + len(self.completed) < self.num_servers

    def get_items(self) -> deque:
        items = deque()
        for the_process in self.work_in_progress:
            items.append(the_process.get_item())
        for the_process in self.completed:
            items.append(the_process.get_item())
        return items
