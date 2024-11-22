from Elements.Element import Element
from typing import Optional
from Elements.Link.Link import Link
from Items.item import Item

from SimClock.SimClock import SimClock,clock

class InfiniteSource (Element):
    def __init__(self, name:str, clock:SimClock):
        super().__init__(name,clock)
        self.last_item:Optional[Item]=None
        self.number_items:int=0

    def start (self)->None:
        self.number_items=0
        self.clock.schedule_event(self, 0.0)
        output=self.get_output()
        if output is not None:
            pass
        else:
            print("Warning: Output is not set for InfiniteSource.")

    # def retrieve(self)->Optional[Item]:
    #     to_send:Item=self.last_item
    #     self.last_item=None
    #     return to_send
    
    def unblock(self)->bool:

        if self.get_output().send(Item(self.clock.get_simulation_time())):
            self.last_item= Item(self.clock.get_simulation_time())
            self.number_items+=1
            return True
        else:
            return False
    
    def execute(self):
        return self.notify_request()
    
    def get_number_items(self):
        return self.number_items
    
    def receive(self, the_item:Item)->bool:
        raise NotImplementedError ("The Source cannot receive Items.")
    
    def execute(self)->None:  ##Este é o execute

        self.last_item=Item(self.clock.get_simulation_time())
        self.number_items +=1

        while self.get_output().send(self.last_item):
            self.last_item=Item(self.clock.get_simulation_time())
            self.number_items +=1
        
    def check_availability(self, the_item:Item)->bool:
        return True
    
    

    
    