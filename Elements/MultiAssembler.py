from collections import deque
from typing import List
#import logging

from Elements.Element import Element
from Elements.WorkStation import WorkStation
from SimClock.SimClock import SimClock
from Elements.ServerProcess import ServerProcess
from random_processes.DoubleRandomProcess import DoubleRandomProcess
from Items.item import Item
from Element import ConstrainedInput
from Element import ArrivalListener



class MultiAssembler(Element, WorkStation, ArrivalListener):
    def __init__(self, capacity: int, requirements: List[int], delay: DoubleRandomProcess, name: str, sim_clock: SimClock, batch_mode: bool = False):
        super().__init__(name, sim_clock)
        self.idle_processes = deque(maxlen=capacity)
        self.work_in_progress = []
        self.completed = deque(maxlen=capacity)

        self.requirements = requirements
        self.delay = delay
        self.name = name
        self.batch_mode = batch_mode
        self.capacity = capacity
        self.inputs = [ConstrainedInput(requirements[i], self, i, f"{name}.Input{i}", sim_clock) for i in range(len(requirements))]
        
        self.completed_items = 0
        self.receiving_items = False

    def start(self):
        self.idle_processes.clear()
        self.work_in_progress.clear()
        self.completed.clear()
        
        for _ in range(self.capacity):
            server = ServerProcess(self, self.delay, 1)
            self.idle_processes.append(server)
        
        for input_port in self.inputs:
            input_port.start()
        
        self.completed_items = 0

    def get_input(self, i: int) -> ConstrainedInput:
        return self.inputs[i]

    def get_inputs_count(self) -> int:
        return len(self.inputs)

    def get_queue_length(self) -> int:
        queue_length = sum(input_port.get_queue_length() for input_port in self.inputs)
        return len(self.work_in_progress) + len(self.completed) + queue_length

    def get_free_capacity(self) -> int:
        return self.capacity - len(self.work_in_progress) - len(self.completed)

    def get_completed_items(self) -> int:
        return self.completed_items

    def unblock(self) -> bool:
        if self.completed:
            process = self.completed.popleft()
            item = process.the_item

            if self.get_output().send(item):
                self.idle_processes.append(process)
                #logging.info("Item sent and process moved to idle.")
                self.check_requirements()
                return True
            else:
                self.completed.appendleft(process)
                return False
        return False

    def receive(self, the_item: Item) -> bool:
        return True

    def item_received(self, the_item: Item, source: int):
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
            process = self.idle_processes.popleft()

            for i, (input_port, req) in enumerate(zip(self.inputs, self.requirements)):
                items = input_port.release(req)
                for item in items:
                    if self.batch_mode:
                        new_item.add_item(item)
            
            self.receiving_items = False
            process.the_item = new_item
            process.load_time = self.sim_clock.get_simulation_time()
            self.work_in_progress.append(process)

            delay_time = self.delay.next_value()
            self.sim_clock.schedule_event(delay_time, process)
            #logging.info(f"Scheduled process with delay {delay_time}")
            self.check_requirements()

    def create_new_item(self) -> Item:
        new_item = Item(self.sim_clock.get_simulation_time())
        new_item.set_id("type", 1, 1)
        return new_item

    def complete_server_process(self, process: ServerProcess):
        item = process.the_item
        self.work_in_progress.remove(process)

        if self.get_output().send(item):
            self.idle_processes.append(process)
            self.check_requirements()
        else:
            self.completed.append(process)

    def check_availability(self, item: Item) -> bool:
        return len(self.work_in_progress) + len(self.completed) < self.capacity

    def get_items(self) -> deque:
        items = deque()
        for process in self.work_in_progress:
            items.append(process.get_current_item())
        for process in self.completed:
            items.append(process.get_current_item())
        return items

    def set_capacity(self, capacity: int):
        self.capacity = capacity
