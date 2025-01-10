from collections import deque
from typing import List, Union
from scipy import stats

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .multiServer import MultiServer
from .serverProcess import ServerProcess
from .combinerInput import CombinerInput
from .arrivalListener import ArrivalListener
from .state import State
from .inputStrategy import InputStrategy


# Combiner has capacity of 1 assembly process, replicating FlexSim's ones
class Combiner(MultiServer, ArrivalListener):
    def __init__(self, requirements: List[int], delay: Union[stats.rv_continuous, stats.rv_discrete], name: str, 
                 sim_clock: SimClock, **kwargs):
        """
        Args:
            requirements (List[int]): A list of requirements.
            delay (Union[stats.rv_continuous, stats.rv_discrete]): A delay distribution.
            name (str): Name of the combiner.
            sim_clock (SimClock): Simulation clock.
            **kwargs:
                batch_mode (bool): Optional. Whether batch mode is enabled. Default is False.
                pull_mode (InputStrategy): Optional. Strategy for pull mode. Default is None.
        """
        super().__init__(1, delay, name=name, clock=sim_clock)
        
        self.the_process = None
        self.requirements = requirements
        self.delay = delay
        self.inputs = [
            CombinerInput(requirements[i], self, i, f"{name}.Input{i}", self.clock)
            for i in range(len(requirements))
        ]

        # Retrieve optional arguments from kwargs
        self.batch_mode = kwargs.get('batch_mode', False)
        self.pull_mode = kwargs.get('pull_mode', None)

        # Validation
        if not isinstance(self.batch_mode, bool):
            raise TypeError("batch_mode must be a boolean.")
        if self.pull_mode is not None and not isinstance(self.pull_mode, InputStrategy):
            raise TypeError("pull_mode must be an InputStrategy object.")
        
    def start(self):
        
        self.the_process = ServerProcess(self, self.delay)
        self.the_process.set_state(State.IDLE)
        
        for input_port in self.inputs:
            input_port.start()
        
    def is_main_receiving(self) -> bool:
        return self.the_process.get_state() == State.RECEIVING
    
    def get_component_input(self, i: int) -> CombinerInput:
        return self.inputs[i]

    def get_inputs_count(self) -> int:
        return len(self.inputs)

    def get_queue_length(self) -> int:
        queue_length = sum(input_port.get_queue_length() for input_port in self.inputs)
        return queue_length

    # def get_free_capacity(self) -> int:
    #     return self.capacity - len(self.work_in_progress) - len(self.completed)

    def get_completed_items(self) -> int:
        return self.get_stats_collector().get_var_output_value()

    def unblock(self) -> bool:
        if self.the_process.get_state() == State.BLOCKED:

            if self.get_output().send(self.the_process.item):
                self.the_process.set_state(State.IDLE)
                self.check_requirements()
                return True
            else:
                return False
        return False

    def receive(self, the_item: Item) -> bool:
        if self.the_process.get_state() == State.IDLE:
            self.the_process.set_state(State.RECEIVING)
            for i in range(self.get_inputs_count()):
                self.get_component_input(i).unblock() 
            return True
        else:
            return False

    def component_received(self, the_item: Item, source: int):
        if self.the_process.get_state() == State.RECEIVING:
            self.check_requirements()

    def check_requirements(self):
        if self.the_process.get_state() != State.RECEIVING:
            return
        
        ready = all(input_port.get_queue_length() >= req for input_port, req in zip(self.inputs, self.requirements))
        
        if ready:
            # new_item = self.create_new_item() ##Would depend on the mode

            for i, (input_port, req) in enumerate(zip(self.inputs, self.requirements)):
                items = input_port.release(req)
                for item in items:
                    if self.batch_mode:
                        self.the_process.the_item.add_item(item)
            
            # process.the_item = new_item
            self.the_process.load_time = self.clock.get_simulation_time()
            self.the_process.set_state(State.BUSY)

            delay_time = self.the_process.get_delay()
            self.clock.schedule_event(self.the_process, delay_time)


    def create_new_item(self) -> Item:
        new_item = Item(self.clock.get_simulation_time())
        return new_item

    def complete_server_process(self, process: ServerProcess):
        item = process.the_item

        if self.get_output().send(item):
            self.the_process.set_state(State.IDLE)
            self.get_input().notify_available()

        else:
            self.the_process.set_state(State.BLOCKED)


    def check_availability(self, the_item: Item) -> bool:
        return len(self.work_in_progress) + len(self.completed) < self.capacity

    def get_items(self) -> deque:
        pass ##pending?

    def set_capacity(self, capacity: int):
        self.capacity = capacity
