from Elements.Element import Element
from Items.item import Item
from SimClock.SimClock import SimClock

from typing import Optional



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
    
    # def notify_request(self)->bool:
    #     raise NotImplementedError ("The Sink cannot receive notifications.")
    
    def receive(self, the_item:Item)->bool:
        self.number_items+=1
        return True
    
    def check_availability(self, the_item:Item)->bool:
        return True
    
    # def cancel_request(self)->bool:
    #     return True
    
