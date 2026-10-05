from typing import Any, Optional

from .source import Source
from ..states import ElementState
from ..Items.item import Item
from ..SimClock.simClock import SimClock

##The source works currently as the FlexSim Source. The interarrival time defines the time between the exit of an item and the arrival of the next one, not between arrivals.

class InterArrivalSource(Source):
    def __init__(self, name: str, clock: SimClock, interarrival_dist: Any, model_item: Optional[Item] = None):
        """``interarrival_dist``: any sampler specification (number, scipy.stats frozen
        distribution, ``"Exponential~0.5"`` spec, expression or ``Sampler``)."""
        super().__init__(name, clock, model_item)

        self.interarrival_dist = self._bind_sampler(interarrival_dist, "interarrival")

        self.on_arrival = False
        self.last_item = None
        
    def start(self) -> None:
        self.number_items = 0
        self.last_item = None
        self.schedule_next_arrival()

    def schedule_next_arrival(self) -> None:
        delay = self.interarrival_dist.get_delay(the_item=None)
        self.clock.schedule_event(self, delay)
        self.on_arrival = True

    def execute(self) -> None:
        new_item = self.create_item()
        self.on_arrival = False

        if not self.get_output().send(new_item):
            self.last_item = new_item
            self._set_state(ElementState.BLOCKED)
            return

        self.number_items += 1
        self.schedule_next_arrival()

    def unblock(self) -> bool:
        if self.last_item is not None:
            # take the item out before sending: the receiver may call unblock() again
            # (re-entrant notify) and must not get the same item twice
            the_item, self.last_item = self.last_item, None
            if self.get_output().send(the_item):
                self._set_state(ElementState.IDLE)
                self.schedule_next_arrival()
                return True
            self.last_item = the_item
        if not self.on_arrival:
            self.schedule_next_arrival()
        return False
    
    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")
    
    def check_availability(self, the_item: Item) -> bool:
        return False

    def get_queue_length(self) -> int:
        return 0 if self.last_item is None else 1

    def get_free_capacity(self) -> float:
        return 0