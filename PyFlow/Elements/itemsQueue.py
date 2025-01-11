from collections import deque
from typing import Deque

from .element import Element
from ..Items.item import Item
from ..SimClock.simClock import SimClock

class ItemsQueue (Element):
    def __init__(self, capacity:int, name:str, clock:SimClock):
        super().__init__(name, clock)
        self.capacity:int=capacity
        self.items_q:Deque[Item]=deque(maxlen=capacity)
        self.total_times_processed:int=0

    def start(self)->None:
        self.items_q.clear()

        self.pending_requests:int=0
        self.current_items:int=0
   
    def unblock(self)->bool:
        if len(self.items_q) >0:
            the_item = self.items_q.popleft()
            self.current_items-=1
  
            if self.get_output().send(the_item):  # Transmitir el ítem al siguiente elemento
                self.get_input().notify_available()  # Notificar disponibilidad al componente anterior
                self.total_times_processed += 1

                return True
            else:  ##No debería pasar en teoría nunca porque estamos en un unblock
                self.items_q.append(the_item)
                self.current_items += 1
        else:
            return False
        
    def receive(self, the_item:Item)->bool:
        if self.current_items<self.capacity:

            if not self.get_output().send(the_item):
                ##Engadir o item a unha lista
                self.items_q.append(the_item)
                self.current_items+=1
            else:
                self.total_times_processed += 1
            return True
        else:
            return False
        
    def check_availability(self, the_item: Item) -> bool:
        return self.current_items<self.capacity