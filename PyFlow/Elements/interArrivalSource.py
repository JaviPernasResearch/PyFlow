from typing import Optional, Union
from typing import Deque
from collections import deque

from .source import Source
from ..Items.item import Item
from ..SimClock.simClock import SimClock
from scipy import stats
from .delayStrategy import RandomDelayStrategy, ExpressionDelayStrategy

##The source works currently as the FlexSim Source. The interarrival time defines the time between the exit of an item and the arrival of the next one, not between arrivals.

class InterArrivalSource(Source):
    def __init__(self, name: str, clock: SimClock, interarrival_dist: Union[stats.rv_continuous, stats.rv_discrete, str], 
                 model_item: Optional[Item] = None):
        super().__init__(name, clock, model_item)

        if isinstance(interarrival_dist, str):
            self.interarrival_dist = ExpressionDelayStrategy(interarrival_dist)
        else:
            self.interarrival_dist = RandomDelayStrategy(interarrival_dist)

        self.on_arrival = False
        self.last_item = None
        
    def start(self) -> None:
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
            return

        self.number_items += 1
        self.schedule_next_arrival()

    def unblock(self) -> bool:
        if self.last_item is not None:
            if self.get_output().send(self.last_item):
                self.last_item = None
                self.schedule_next_arrival()
                return True
        if not self.on_arrival:
            self.schedule_next_arrival()
        return False
    
    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")
    
    def check_availability(self, the_item: Item) -> bool:
        return False