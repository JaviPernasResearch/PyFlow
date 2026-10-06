from collections import deque
from typing import Any, List, Optional, Sequence, Union
from scipy import stats

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .multiServer import MultiServer
from .serverProcess import ServerProcess
from .combinerInput import CombinerInput
from .arrivalListener import ArrivalListener
from .state import State
from .inputStrategy import DefaultStrategy, InputStrategy
from ..states import ElementState

_ELEMENT_STATE = {State.IDLE: ElementState.IDLE, State.RECEIVING: ElementState.RECEIVING,
                  State.BUSY: ElementState.PROCESSING, State.BLOCKED: ElementState.BLOCKED}


# Combiner has capacity of 1 assembly process, replicating FlexSim's ones
class Combiner(MultiServer, ArrivalListener):
    def __init__(self, requirements: List[int], delay_strategy: Union[stats.rv_continuous, stats.rv_discrete, str],
                 name: str, sim_clock: SimClock, *, batch_mode: bool = False,
                 pull_mode: Optional[InputStrategy] = None, update_requirements: bool = False,
                 update_labels: Optional[List[str]] = None, resources: Optional[Sequence[Any]] = None,
                 resource_release: str = "on_finish"):
        """
        Args:
            requirements (List[int]): Components needed per input port.
            delay_strategy: Processing time, any sampler specification (number, scipy.stats
                distribution, ``"Exponential~0.5"``, label expression, ``Sampler``).
            name (str): Name of the combiner.
            sim_clock: The ``Model`` (or its ``SimClock``).
            batch_mode (bool): The components travel as sub-items of the main item.
            pull_mode (InputStrategy): Filter of the component ports, updated with each main
                item. Default: accept every component.
            update_requirements (bool): Read the requirements from labels of the main item.
            update_labels (List[str]): Label per port holding its requirement.
            resources / resource_release: shared resources needed while processing (see
                :class:`MultiServer`).
        """
        super().__init__(1, delay_strategy, name=name, clock=sim_clock, resources=resources,
                         resource_release=resource_release)

        self.the_process = None
        self.requirements = requirements
        self.delay_strategy = delay_strategy

        self.batch_mode = batch_mode
        self.pull_mode = pull_mode if pull_mode is not None else DefaultStrategy()
        self.update_requirements_enabled = update_requirements
        self.update_labels = update_labels

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
        
        self.the_process = ServerProcess(self, self.service_sampler)
        self.blockage_count = 0
        self._set_process_state(State.IDLE)
        
        for input_port in self.inputs:
            input_port.start()
        
    def _set_process_state(self, state: State) -> None:
        self.the_process.set_state(state)
        self._set_state(_ELEMENT_STATE[state])

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
                self._release_all(self.the_process)
                self._set_process_state(State.IDLE)
                self.get_input().notify_available()
                return True
            else:
                return False
        return False

    def receive(self, the_item: Item) -> bool:
        if self.the_process.get_state() == State.IDLE:
            self._set_process_state(State.RECEIVING)
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
            
            self.the_process.set_state(State.BUSY)   # components consumed: no longer receiving
            self._acquire(self.the_process, "processing", self._start_processing)
            if self.the_process.phase == "waiting":
                self._set_state(ElementState.WAITING_FOR_RESOURCE)
            return True
        else:
            return False


    def _start_processing(self) -> None:
        self.the_process.phase = "processing"
        self._set_process_state(State.BUSY)
        delay_time = self.the_process.get_delay()
        self.the_process.work = self.schedule_work(self.the_process.execute, delay_time)

    def _refresh_state(self) -> None:
        """Called after a resource grant; the combiner's state follows its single process."""
        if self.the_process is not None and self.the_process.phase != "waiting":
            self._set_state(_ELEMENT_STATE[self.the_process.get_state()])

    def create_new_item(self) -> Item:
        return self._new_item()

    def complete_server_process(self, process: ServerProcess):
        the_item = process.the_item
        process.phase = None
        process.work = None
        self._end_phase(process, "processing")

        if self.get_output().send(the_item):
            self._release_all(process)
            self._set_process_state(State.IDLE)
            self.get_input().notify_available()
            

        else:
            self.blockage_count += 1
            self._set_process_state(State.BLOCKED)


    def holds_item(self, the_item: Item) -> bool:
        return self.the_process.get_state() == State.BLOCKED and self.the_process.get_item() is the_item

    def release_item(self, the_item: Item) -> bool:
        if not self.holds_item(the_item):
            return False
        self._release_all(self.the_process)
        self._set_process_state(State.IDLE)
        self.get_input().notify_available()
        return True

    def get_queue_length(self) -> int:
        return 0 if self.the_process.get_state() == State.IDLE else 1

    def get_free_capacity(self) -> float:
        return 1 if self.the_process.get_state() == State.IDLE else 0

    def check_availability(self, the_item: Item) -> bool: ##Cambiarlo
        return self.the_process.get_state() == State.IDLE
