from typing import Optional

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .element import Element

class Sink (Element):
    def __init__(self, name:str, clock:SimClock):
        super().__init__(name, clock)
        self.number_items:int=0
   
    def start(self)->None:
        self.number_items:int=0
    
    def unblock(self)->Optional[Item]:
        raise NotImplementedError ("The Sink cannot receive notifications.")
    
    def receive(self, the_item:Item)->bool:
        self.number_items+=1
        # print(str(the_item.get_type()) + ": " + str(the_item.get_all_labels()))
        print(f"{the_item.name}: Sink at {self.clock.get_simulation_time()}")
        return True
    
    def check_availability(self, the_item: Item) -> bool:
        return True

