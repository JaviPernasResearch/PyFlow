from Elements.Element import Element
from typing import Optional
from Items.item import item

from SimClock.SimClock import SimClock


class InfiniteSource (Element):
    def __init__(self, name:str, clock:SimClock):
        super().__init__(name,clock)
        self.last_item:Optional[item]=None
        self.number_items:int=0

    def start (self)->None:
        self.number_items=0
        self.clock.schedule_event(self, 0.0)

    def retrieve(self)->Optional[item]:
        to_send:item=self.last_item
        self.last_item=None
        return to_send
    
    def notify_request(self)->bool:
        self.last_item= item(self.clock.get_simulation_time())
        self.get_output().send(self.last_item,self)
        self.number_items+=1
        return True
    
    def receive(self, the_item:item)->bool:
        raise NotImplementedError ("The Source cannot receive Items.")
    
    def step(self)->None:
        while True:
            self.last_item=item(self.clock.get_simulation_time())
            self.number_item+=1
            if not self.get_output().send(self.last_item,self):
                break

    def check_availability(self, the_item:item)->bool:
        return False
    
    def cancel_request(self)->bool:
        return True
    
    