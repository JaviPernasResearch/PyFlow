from typing import Optional

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .element import Element

class Sink (Element):
    def __init__(self, name:str, clock:SimClock):
        super().__init__(name, clock)
        self.number_items:int=0

    def get_number_items(self)->int:
        return self.number_items
    
    def start(self)->None:
        self.number_items:int=0
    
    def unblock(self)->Optional[Item]:
        raise NotImplementedError ("The Sink cannot receive notifications.")
    
    def receive(self, the_item:Item)->bool:
        self.number_items+=1
        # print(str(the_item.get_type()) + ": " + str(the_item.get_all_labels()))
        return True
    
    def check_availability(self, the_item: Item) -> bool:
        return True

