from Elements.Element import Element
from typing import Optional, Union
from typing import Deque
from collections import deque

from Items.item import Item
from SimClock.SimClock import SimClock
from scipy import stats

class IntelArriveSource(Element):
    def __init__(self, name: str, clock: SimClock, arrival_time_distribution: Union[stats.rv_continuous, stats.rv_discrete]):
        super().__init__(name, clock)
        self.last_items:Deque[Item]=deque(maxlen=10000000)
        self.number_items: int = 0
        self.arrival_time_distribution = arrival_time_distribution
        self.on_process: bool = False
        
    def start(self) -> None:
        self.schedule_next_arrival()

    def schedule_next_arrival(self) -> None:
        delay = self.arrival_time_distribution.rvs()
        self.clock.schedule_event(self, delay)
        self.on_process = True

    def execute(self) -> None:
        new_item = Item(self.clock.get_simulation_time())
        self.on_process = False

        if not self.get_output().send(new_item):
            # self.last_items.appendleft(new_item)
            return

        self.number_items += 1
        self.schedule_next_arrival()

    def unblock(self) -> bool:
        # if len(self.last_items) > 0:
        #     if self.get_output().send(self.last_items[0]):
        #         self.last_items.popleft()
        #         self.number_items += 1
        #         return True
        # else:
        #     return False
        if not self.on_process:
            return self.schedule_next_arrival()
        else:
            return

    def get_number_items(self) -> int:
        return self.number_items
    
    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")
    
    def check_availability(self, the_item: Item) -> bool:
        return len(self.last_items) > 0