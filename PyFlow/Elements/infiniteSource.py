from typing import Optional

from .element import Element
from ..Items.item import Item
from ..SimClock.simClock import SimClock

class InfiniteSource (Element):
    def __init__(self, name: str, clock: SimClock, model_item: Optional[Item] = None):
        super().__init__(name, clock, model_item)
        self.last_item = None

    def start (self)->None:
        self.number_items=0
        self.clock.schedule_event(self, 0.0)
        if self.get_output() is None:
            print(f"Warning: Output is not set for InfiniteSource {self.name}.")
    
    def unblock(self)->bool:
        self.execute()
        return True
        
    def receive(self, the_item:Item)->bool:
        raise NotImplementedError ("The Source cannot receive Items.")
    
    def execute(self) -> None:
        self.last_item = self.create_item()
        self.number_items += 1

        while self.get_output().send(self.last_item):
            self.last_item = self.create_item()
            self.number_items += 1        
    
    def check_availability(self, the_item: Item) -> bool:
        return False
    
    

    
    