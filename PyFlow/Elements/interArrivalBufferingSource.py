from typing import Optional, Union
from typing import Deque
from collections import deque

from .source import Source
from ..Items.item import Item
from ..SimClock.simClock import SimClock
from scipy import stats

# The interarrival time of this source works as the time between the arrivals of two items. 
# If the source is blocked, it stores the items arriving during the blockage and sends them as soon as the the element downstream is available.

class InterArrivalBufferingSource(Source):
    def __init__(self, name: str, clock: SimClock, arrival_time_distribution: Union[stats.rv_continuous, stats.rv_discrete], model_item: Optional[Item] = None):
        super().__init__(name, clock, model_item)
        self.arrival_time_distribution = arrival_time_distribution

    def start(self) -> None:
        self.schedule_next_arrival()

    def schedule_next_arrival(self) -> None:
        delay = self.arrival_time_distribution.rvs()
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