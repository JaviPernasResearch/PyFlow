from collections import deque
from typing import Deque, List, Optional, Union
from scipy import stats

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .element import Element
from .serverProcess import ServerProcess
from .workStation import WorkStation

class MultiServer(Element,WorkStation):
    def __init__(self, capacity,random_times:Union[stats.rv_continuous, stats.rv_discrete], name:str, clock:SimClock):
        super().__init__(name, clock)
        self.capacity=capacity
        self.random_times=random_times
        self.idle_processes:Deque[ServerProcess]=deque()
        self.work_in_progress:Deque[ServerProcess]=deque()
        self.completed:Deque[ServerProcess]=deque()

        self.current_items=0
        self.pending_requests=0

        self.random_times:Union[stats.rv_continuous, stats.rv_discrete]=random_times
    
        self.capacity:int=1
        

    def get_name(self)->str:
        pass

    
    def start(self)->None:
        self.idle_processes.clear()
        self.work_in_progress.clear()
        self.completed.clear()

        for i in  range(self.capacity):
            the_server=ServerProcess(self, self.random_times[i])
            self.idle_processes.append(the_server)

        self.current_items=0

    def send(self, item: Item) -> bool:
        if len(self.work_in_progress) < self.capacity:
            print(f"Sending item from MultiServer: {item.get_creation_time()}")
            # Aquí puedes agregar la lógica para manejar cómo se envía el ítem
            return True
        else:
            print("MultiServer is full; cannot send item.")
            return False


    def unblock(self)->Optional[Item]:
        if  self.completed:
            the_process=self.completed.popleft() 
            the_item = the_process.the_item

            if self.get_output().send(the_item):
                ##Quitar proceso da lista se é posible envialo
                self.idle_processes.append(the_process)
                self.current_items -= 1
                self.get_input().notify_available()
                return True
            else:
                return False
        else:
            return False

    def receive(self, the_item:Item)->bool:
        if self.current_items >= self.capacity:
            return False
        
        if not self.idle_processes:
            return False
        
        
        the_process = self.idle_processes.popleft()
        the_process.the_item = the_item
        self.work_in_progress.append(the_process)
            
        self.current_items += 1

        delay=the_process.get_delay()
        self.clock.schedule_event(the_process, delay)

        return True
        

    def complete_server_process(self, the_process:ServerProcess)->None:
        the_item = the_process.the_item
        self.work_in_progress.remove(the_process)
        
        if self.get_output().send(the_item):
            self.idle_processes.append(the_process)
            self.current_items -= 1

            self.get_input().notify_available()
        else:
            self.completed.append(the_process)

    def check_availability(self)->bool:
        return not (self.current_items >= self.capacity)


