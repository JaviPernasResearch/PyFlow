from typing import Dict, List, Optional

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .element import Element


class Sink (Element):
    """End of the line. Counts items (``number_items``, ``type_counts``) and forgets them, so
    long runs do not keep every item in memory. ``keep_items=True`` stores them in ``items``."""

    def __init__(self, name:str, clock:SimClock, *, keep_items: bool = False):
        super().__init__(name, clock)
        self.keep_items = keep_items
        self.number_items:int=0
        self.type_counts: Dict[str, int] = {}
        self.items: List[Item] = []

    def start(self)->None:
        self.number_items = 0
        self.type_counts = {}
        self.items = []

    def unblock(self)->bool:
        return False  # a sink never sends anything

    def receive(self, the_item:Item)->bool:
        self.number_items+=1
        item_type = the_item.type if the_item.type else "Default"
        self.type_counts[item_type] = self.type_counts.get(item_type, 0) + 1
        if self.keep_items:
            self.items.append(the_item)
        self.stats_collector.absorb(the_item)
        return True

    def get_queue_length(self) -> int:
        return 0

    def check_availability(self, the_item: Item) -> bool:
        return True
