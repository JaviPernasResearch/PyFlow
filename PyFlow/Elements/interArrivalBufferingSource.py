from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Optional

from .source import Source
from ..states import ElementState
from ..Items.item import Item

if TYPE_CHECKING:
    from ..model import Model


# The interarrival time of this source works as the time between the arrivals of two items.
# If the source is blocked, it keeps generating items on schedule, stores them and sends them
# in arrival order (FIFO) as soon as the element downstream is available.

class InterArrivalBufferingSource(Source):
    def __init__(self, name: str, model: "Model", interarrival_dist: Any, model_item: Optional[Item] = None):
        super().__init__(name, model, model_item)

        self.interarrival_dist = self._bind_sampler(interarrival_dist, "interarrival")
        self.buffer: Deque[Item] = deque()

    def start(self) -> None:
        self.buffer.clear()
        self.number_items = 0
        self.schedule_next_arrival()

    def schedule_next_arrival(self) -> None:
        delay = self.interarrival_dist.sample()
        self.clock.schedule_event(self, delay)

    def execute(self) -> None:
        new_item = self.create_item()
        # Earlier items still waiting go first; the new one is only sent directly if none wait
        if self.buffer or not self.get_output().send(new_item):
            self.buffer.append(new_item)
            self._set_state(ElementState.BLOCKED)
            self._announce(new_item)
        else:
            self.number_items += 1
        self.schedule_next_arrival()

    def unblock(self) -> bool:
        if not self.buffer:
            return False
        the_item = self.buffer.popleft()  # out first: re-entrant unblock must not resend it
        if self.get_output().send(the_item):
            self.number_items += 1
            if not self.buffer:
                self._set_state(ElementState.IDLE)
            return True
        self.buffer.appendleft(the_item)
        return False

    def holds_item(self, the_item: Item) -> bool:
        return any(i is the_item for i in self.buffer)

    def release_item(self, the_item: Item) -> bool:
        if not self.holds_item(the_item):
            return False
        self.buffer.remove(the_item)
        self.number_items += 1
        if not self.buffer:
            self._set_state(ElementState.IDLE)
        return True

    def get_buffer_length(self) -> int:
        return len(self.buffer)

    def get_queue_length(self) -> int:
        return len(self.buffer)

    def get_free_capacity(self) -> float:
        return 0

    def receive(self, the_item: Item) -> bool:
        raise NotImplementedError("The Source cannot receive Items.")
    
    def check_availability(self, the_item: Item) -> bool:
        return False
