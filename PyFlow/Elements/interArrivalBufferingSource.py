from typing import Optional, Union
from typing import Deque
from collections import deque

from .source import Source
from ..Items.item import Item
from ..SimClock.simClock import SimClock
from scipy import stats
from .delayStrategy import RandomDelayStrategy, ExpressionDelayStrategy


# The interarrival time of this source works as the time between the arrivals of two items. 
# If the source is blocked, it stores the items arriving during the blockage and sends them as soon as the the element downstream is available.

class InterArrivalBufferingSource(Source):
    def __init__(self, name: str, clock: SimClock, interarrival_dist: Union[stats.rv_continuous, stats.rv_discrete, str], 
                 model_item: Optional[Item] = None):
        super().__init__(name, clock, model_item)

        if isinstance(interarrival_dist, str):
            self.interarrival_dist = ExpressionDelayStrategy(interarrival_dist)
        else:
            self.interarrival_dist = RandomDelayStrategy(interarrival_dist)

    def start(self) -> None:
        self.schedule_next_arrival()

    def schedule_next_arrival(self) -> None:
        delay = self.interarrival_dist.get_delay(the_item=None)
        self.clock.schedule_event(self, delay)

    def execute(self) -> None:
        new_item = self.create_item()

        if not self.get_output().send(new_item):
            self.last_items.appendleft(new_item)
            return

        self.number_items += 1
        self.schedule_next_arrival()

    def unblock(self) -> bool:
        if len(self.last_items) > 0:
            if self.get_output().send(self.last_items[0]):
                self.last_items.popleft()
                self.number_items += 1
                return True
        else:
            return False
    
    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")
    
    def check_availability(self, the_item: Item) -> bool:
        return False