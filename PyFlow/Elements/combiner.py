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
from .inputStrategy import DefaultStrategy, InputStrategy


# Combiner has capacity of 1 assembly process, replicating FlexSim's ones
class Combiner(MultiServer, ArrivalListener):
    def __init__(self, requirements: List[int], delay_strategy:Union[stats.rv_continuous, stats.rv_discrete, str], name: str, 
                 sim_clock: SimClock, **kwargs):
        """
        Args:
            requirements (List[int]): A list of requirements.
            delay_strategy (Union[stats.rv_continuous, stats.rv_discrete, str]): The strategy for determining the delay. 
                This can be an instance of a Scipy distribution class or a string specifying the item label name to read the delay from.
            name (str): Name of the combiner.
            sim_clock (SimClock): Simulation clock.
            **kwargs:
                batch_mode (bool): Optional. Whether batch mode is enabled. Default is False.
                pull_mode (InputStrategy): Optional. Strategy for pull mode of the components. Default is None.
                update_requirements (bool): Optional. Whether to update requirements based on main item. Default is False.
                update_labels (List[str]): Optional. The list of label names to use for updating requirements. The label position corresponds to the requirement position. Default is None.
        """
        super().__init__(1, delay_strategy, name=name, clock=sim_clock)
        
        self.the_process = None
        self.requirements = requirements
        self.delay_strategy = delay_strategy

        # Retrieve optional arguments from kwargs
        self.batch_mode = kwargs.get('batch_mode', False)
        self.pull_mode = kwargs.get('pull_mode', DefaultStrategy())
        self.update_requirements_enabled = kwargs.get('update_requirements', False)
        self.update_labels = kwargs.get('update_labels', None)

        # Validation
        if not isinstance(self.batch_mode, bool):
            raise TypeError("batch_mode must be a boolean.")
        if self.pull_mode is not None and not isinstance(self.pull_mode, InputStrategy):
            raise TypeError("pull_mode must be an InputStrategy object.")
        if not isinstance(self.update_requirements_enabled, bool):
            raise TypeError("update_requirements must be a boolean.")
        if self.update_labels is not None and not isinstance(self.update_labels, list):
            raise TypeError("update_label must be string.")
        
        self.inputs = [
            CombinerInput(requirements[i], self, i, f"{name}.Input{i}", self.clock, self.pull_mode)
            for i in range(len(requirements))
        ]
        
    def start(self):
        
        self.the_process = ServerProcess(self, self.delay_strategy)
        self.the_process.set_state(State.IDLE)
        
        for input_port in self.inputs:
            input_port.start()
        
    def is_main_receiving(self) -> bool:
        return self.the_process.get_state() == State.RECEIVING
    
    def get_component_input(self, i: int) -> CombinerInput:
        return self.inputs[i]

    def get_inputs_count(self) -> int:
        return len(self.inputs)
    
    def _update_requirements(self, the_item: Item) -> None:
        """
        Update the requirements (capacity of constrained inputs) based on the main item's label values.
        """
        if not self.update_requirements_enabled or not self.update_labels:
            return

        for i, label in enumerate(self.update_labels):
            label_value = the_item.get_label_value(label)
            if label_value is not None and i < len(self.inputs):
                self.requirements[i] = int(label_value)
                self.inputs[i].set_capacity(int(label_value))

    # def get_queue_length(self) -> int:
    #     queue_length = sum(input_port.get_queue_length() for input_port in self.inputs)
    #     return queue_length

    # def get_free_capacity(self) -> int:
    #     return self.capacity - len(self.work_in_progress) - len(self.completed)

    def unblock(self) -> bool:
        if self.the_process.get_state() == State.BLOCKED:

            if self.get_output().send(self.the_process.get_item()):
                self.the_process.set_state(State.IDLE)
                self._check_requirements()
                return True
            else:
                return False
        return False

    def receive(self, the_item: Item) -> bool:
        if self.the_process.get_state() == State.IDLE:
            self.the_process.set_state(State.RECEIVING)
            self.the_process.set_item(the_item)
            self.pull_mode.update_strategy(the_item)
            self._update_requirements(the_item)
            for i in range(self.get_inputs_count()):
                self.get_component_input(i).unblock() 
            return True
        else:
            return False

    def component_received(self, the_item: Item, source: int) -> bool:
        if self.the_process.get_state() == State.RECEIVING:
            return self._check_requirements()
        else:    
            return False

    def _check_requirements(self) -> bool:
        if self.the_process.get_state() != State.RECEIVING:
            return False
        
        ready = all(input_port.get_queue_length() >= req for input_port, req in zip(self.inputs, self.requirements))
        
        if ready:
            # new_item = self.create_new_item() ##Would depend on the mode

            for i, (input_port, req) in enumerate(zip(self.inputs, self.requirements)):
                items = input_port.release(req)
                for item in items:
                    if self.batch_mode:
                        self.the_process.get_item().add_item(item)
            
            # process.the_item = new_item
            # self.the_process.load_time = self.clock.get_simulation_time()
            self.the_process.set_state(State.BUSY)

            delay_time = self.the_process.get_delay()
            self.clock.schedule_event(self.the_process, delay_time)
            return True
        else:
            return False


    def create_new_item(self) -> Item:
        new_item = Item(self.clock.get_simulation_time())
        return new_item

    def complete_server_process(self, process: ServerProcess):
        the_item = process.the_item

        if self.get_output().send(the_item):
            self.the_process.set_state(State.IDLE)
            self.get_input().notify_available()

        else:
            self.the_process.set_state(State.BLOCKED)


    def check_availability(self, the_item: Item) -> bool: ##Cambiarlo
        return self.the_process.get_state() == State.IDLE
