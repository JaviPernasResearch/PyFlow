from collections import deque
from typing import Deque, Optional

from Items.item import Item
from Elements.Element import Element
from SimClock.SimClock import SimClock



class ItemQueue (Element):
    def __init__(self, capacity:int, name:str, clock:SimClock):
        super().__init__(name, clock)
        self.capacity:int=capacity
        self.items_q:Deque[Item]=deque(maxlen=capacity)

    def start(self)->None:
        self.items_q.clear()

        self.pending_requests:int=0
        self.current_items:int=0

    # def retrieve(self)->Optional[Item]:
    #     if len(self.items_q)>0:
    #         self.current_items-=1
    #         return self.items_q.popleft()
    #     else:
    #         return None
        
    def unblock(self)->bool:
        # if self.pending_requests>0:
        if len(self.items_q) >0:
            the_item = self.items_q.popleft()
            self.current_items = self.current_items-1
            
            self.get_output().send(the_item)

            self.get_input().NotifyAvaliable()
            return True
        elif self.capacity == 0:
            self.get_input().NotifyAvaliable()
            return True
        else:
            return False
        
    def receive(self, the_item:Item)->bool:
        if self.current_items<self.capacity:
            if not self.get_output().send(the_item):
                ##Engadir o item a unha lista
                self.items_q.append(the_item) ##COMPROBAR
            self.items_q.append(the_item)
            self.current_items+=1
            return True
        else:
            return False
        
    # def cancel_request(self)->bool:
    #     if self.pending_requests>0:
    #         self.pending_requests -=1
    #         return True
        
    #     else:
    #         return False
        
    def check_availability(self)->bool:
        return self.current_items<self.capacity
    
    

        
