from collections import deque
from typing import Any, Deque, Optional

from .source import Source
from ..Items.item import Item
from ..SimClock.simClock import SimClock


# The interarrival time of this source works as the time between the arrivals of two items.
# If the source is blocked, it keeps generating items on schedule, stores them and sends them
# in arrival order (FIFO) as soon as the element downstream is available.

class InterArrivalBufferingSource(Source):
    def __init__(self, name: str, clock: SimClock, interarrival_dist: Any, model_item: Optional[Item] = None):
        super().__init__(name, clock, model_item)

        self.interarrival_dist = self._bind_sampler(interarrival_dist, "interarrival")
        self.buffer: Deque[Item] = deque()

    def start(self) -> None:
        self.buffer.clear()
        self.number_items = 0
        self.schedule_next_arrival()

    def schedule_next_arrival(self) -> None:
        delay = self.interarrival_dist.get_delay(None)
        self.clock.schedule_event(self, delay)

    def execute(self) -> None:
        new_item = self.create_item()
        # Earlier items still waiting go first; the new one is only sent directly if none wait
        if self.buffer or not self.get_output().send(new_item):
            self.buffer.append(new_item)
        else:
            self.number_items += 1
        self.schedule_next_arrival()

    def unblock(self) -> bool:
        if self.buffer and self.get_output().send(self.buffer[0]):
            self.buffer.popleft()
            self.number_items += 1
            return True
        return False

    def get_buffer_length(self) -> int:
        return len(self.buffer)

    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")
    
    def check_availability(self, the_item: Item) -> bool:
        return False
