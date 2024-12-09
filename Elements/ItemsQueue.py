from collections import deque
from typing import Deque

from Items.item import Item
from Elements.Element import Element
from SimClock.SimClock import SimClock

class ItemQueue (Element):
    def __init__(self, capacity:int, name:str, clock:SimClock):
        super().__init__(name, clock)
        self.capacity:int=capacity
        self.items_q:Deque[Item]=deque(maxlen=capacity)
        self.queue_lengths=[]
        self.item_count=0


        self.total_waiting_time = 0
        self.average_waiting_times = []
        self.last_service_time = self.clock.get_simulation_time()

    def start(self)->None:
        self.items_q.clear()

        self.pending_requests:int=0
        self.current_items:int=0

    
    ## Sería algo así como "que_queue_avg_length_data"  pero habería que depuralo
    # def get_queue_length_data(self):
    #     return self.queue_lengths
    def get_queue_length_data(self):
        return len(self.items_q)
    
    def get_average_waiting_time_data(self):
        return self.average_waiting_times

    def unblock(self)->bool:
        if len(self.items_q) >0:
            the_item = self.items_q.popleft()
            self.current_items = self.current_items-1
            
            self.get_output().send(the_item)

            self.get_input().notify_available()
            return True
        elif self.capacity == 0:
            self.get_input().notify_available()
            return True
        else:
            return False
        
    def receive(self, the_item:Item)->bool:
        if self.current_items < self.capacity:

            current_time = self.clock.get_simulation_time()
            waiting_time = current_time - self.last_service_time
            self.total_waiting_time += waiting_time
            self.last_service_time = current_time


            if not self.get_output().send(the_item):
                self.items_q.append(the_item)
                self.item_count += 1
                if self.item_count % 1000 == 0:
                    self.queue_lengths.append(len(self.items_q))


                    avg_waiting_time = self.total_waiting_time / self.item_count
                    self.average_waiting_times.append(avg_waiting_time)


            self.current_items += 1
            return True
        else:
            return False
        
    def check_availability(self)->bool:
        return self.current_items<self.capacity
        
