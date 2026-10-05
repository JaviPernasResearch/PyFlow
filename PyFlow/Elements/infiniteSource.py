import logging
from typing import Optional

from .source import Source
from ..Items.item import Item
from ..SimClock.simClock import SimClock
from ..states import ElementState


class InfiniteSource (Source):
    """Always has an item ready: sends as many as downstream accepts. The item refused last
    is kept and sent first when downstream frees up (no item is ever lost)."""

    def __init__(self, name: str, clock: SimClock, model_item: Optional[Item] = None):
        super().__init__(name, clock, model_item)
        self.last_item = None

    def start (self)->None:
        self.number_items=0
        self.last_item = None
        self.clock.schedule_event(self, 0.0)
        if self.get_output() is None:
            logging.getLogger("pyflow").warning("Output is not set for InfiniteSource %s.", self.name)

    def _pending_item(self) -> Item:
        if self.last_item is None:
            self.last_item = self.create_item()
            self.number_items += 1
        return self.last_item

    def _send_pending(self) -> bool:
        the_item = self._pending_item()
        self.last_item = None  # out first: re-entrant unblock must not resend it
        if self.get_output().send(the_item):
            return True
        if self.last_item is None:
            self.last_item = the_item
        return False

    def unblock(self)->bool:
        if self._send_pending():
            self.execute()
            return True
        return False
        
    def receive(self, the_item:Item)->bool:
        raise NotImplementedError ("The Source cannot receive Items.")
    
    def execute(self) -> None:
        while self._send_pending():
            pass
        self._set_state(ElementState.BLOCKED)

    def get_queue_length(self) -> int:
        return 0 if self.last_item is None else 1

    def get_free_capacity(self) -> float:
        return 0
    
    def check_availability(self, the_item: Item) -> bool:
        return False
