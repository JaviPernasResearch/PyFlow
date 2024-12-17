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
        self.items_q_arrival_times:Deque[float]=deque(maxlen=capacity)
        self.total_items_processed = 0 #Suma 1 OnExit
    def start(self)->None:
        self.items_q.clear()

        self.pending_requests:int=0
        self.current_items:int=0

    def get_queue_length_data(self):
        return self.current_items
    
    # def get_last_time_waiting_time_data(self):
    #     return (self.clock.get_simulation_time()- self.items_q_arrival_times[0]) if len(self.items_q) > 0 else 0
    def get_last_time_waiting_time_data(self):
        with open("simulation_resultsMD1_new.txt", 'a') as f:
            waiting_time = (self.clock.get_simulation_time()- self.items_q_arrival_times[0]) if self.current_items > 0 else 0
            f.write(f"{self.total_items_processed}\t{self.get_queue_length_data()}\t\t{waiting_time}\n") ##faltaría 
        return waiting_time
    
    def get_average_waiting_time_data(self):
        ##Pendente Facer
        ##Non é urxente, non é para a comparación
        return self.current_items
    
    def unblock(self)->bool:
        if len(self.items_q) >0:
            the_item = self.items_q.popleft()

            if self.get_output().send(the_item):  # Transmitir el ítem al siguiente elemento
                self.get_input().notify_available()  # Notificar disponibilidad al componente anterior


                self.total_items_processed+=1
                if self.total_items_processed %1000 == 0:
                    self.get_last_time_waiting_time_data()

                self.current_items-=1
                self.items_q_arrival_times.popleft()
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
                self.items_q_arrival_times.append(self.clock.get_simulation_time())
                self.current_items+=1

            self.total_items_processed+=1
            if self.total_items_processed %1000 == 0:
                self.get_last_time_waiting_time_data()
            return True
        else:
            return False
        
    def check_availability(self)->bool:
        return self.current_items<self.capacity