from Elements.Element import Element
from Items.item import item
from SimClock.SimClock import SimClock

from typing import Optional



class Sink (Element):
    def __init__(self, name:str, clock:SimClock):
        super.__init__(self, name, clock)
        self.number_items:int=0

    def get_number_items(self)->int:
        return self.number_items
    
    def star(self)->None:
        self.number_items:int=0
    
    def retreive(self)->Optional[item]:
        raise NotImplementedError ("The Sink cannot receive notifications.")
    
    def notify_request(self)->bool:
        raise NotImplementedError ("The Sink cannot receive notifications.")
    
    def receive(self, the_item:item)->bool:
        self.number_items+=1
        return True
    
    def check_avaliability(self, the_item:item)->bool:
        return True
    
    def cancel_request(self)->bool:
        return True
    
