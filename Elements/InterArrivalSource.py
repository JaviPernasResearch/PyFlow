from Elements.Element import Element
from typing import Optional, Union
from Items.item import Item
from SimClock.SimClock import SimClock
from scipy import stats

class IntelArriveSource(Element):
    def __init__(self, name: str, clock: SimClock, arrival_time_distribution: Union[stats.rv_continuous, stats.rv_discrete]):
        super().__init__(name, clock)
        self.last_item: Optional[Item] = None
        self.number_items: int = 0
        self.arrival_time_distribution = arrival_time_distribution

    def start(self) -> None:
        self.schedule_next_arrival()

    def schedule_next_arrival(self) -> None:
        delay = self.arrival_time_distribution.rvs()
        self.clock.schedule_event(self, delay)

    def execute(self) -> None:
        self.last_item = Item(self.clock.get_simulation_time())
        self.number_items += 1

        output = self.get_output()
        if output is not None:
            output.send(self.last_item)

        self.schedule_next_arrival()

    def unblock(self) -> bool:
        if self.get_output().send(Item(self.clock.get_simulation_time())):
            self.last_item = Item(self.clock.get_simulation_time())
            self.number_items += 1
            return True
        else:
            return False

    def get_number_items(self) -> int:
        return self.number_items
    
    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")
    
    def check_availability(self, the_item: Item) -> bool:
        return True