from collections import deque
from typing import Deque, List, Optional, Union
from scipy import stats

from ..Items.item import Item
from ..SimClock.simClock import SimClock
from .element import Element
from .serverProcess import ServerProcess
from .workStation import WorkStation

class MultiServer(Element, WorkStation):
    def __init__(self, num_servers: int, delay_strategy: Union[stats.rv_continuous, stats.rv_discrete, str], name:str, clock:SimClock):
        super().__init__(name, clock)
        """
        Args:
            num_servers (int): The number of servers (capacity of the workstation).
            delay_strategy (Union[stats.rv_continuous, stats.rv_discrete, str]): The strategy for determining the delay. 
                This can be an instance of an Scipy distribution class or a string specifying the item label name to read the delay from.
            name (str): The name of the multi-server.
            clock (SimClock): The simulation clock.
        """
        self.num_servers = num_servers
        self.delay_strategy = delay_strategy

        self.idle_processes:Deque[ServerProcess]=deque()
        self.work_in_progress:Deque[ServerProcess]=deque()
        self.completed:Deque[ServerProcess]=deque()

        self.current_items=0
        self.pending_requests=0
    
    def start(self)->None:
        self.idle_processes.clear()
        self.work_in_progress.clear()
        self.completed.clear()

        for i in  range(self.num_servers):
            the_process=ServerProcess(self, self.delay_strategy)
            self.idle_processes.append(the_process)

        self.current_items=0

    def send(self, item: Item) -> bool:
        if len(self.work_in_progress) < self.num_servers:
            print(f"Sending item from MultiServer: {item.get_creation_time()}")
            # Aquí puedes agregar la lógica para manejar cómo se envía el ítem
            return True
        else:
            print("MultiServer is full; cannot send item.")
            return False


    def unblock(self)->Optional[Item]:
        if  self.completed:
            the_process=self.completed.popleft() 
            the_item = the_process.get_item()

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
        if self.current_items >= self.num_servers:
            return False
        
        if not self.idle_processes:
            return False
        
        
        the_process = self.idle_processes.popleft()
        the_process.set_item(the_item)
        self.work_in_progress.append(the_process)
            
        self.current_items += 1

        delay=the_process.get_delay()
        self.clock.schedule_event(the_process, delay)

        return True
        

    def complete_server_process(self, the_process:ServerProcess)->None:
        the_item = the_process.get_item()
        self.work_in_progress.remove(the_process)
        
        if self.get_output().send(the_item):
            self.idle_processes.append(the_process)
            self.current_items -= 1

            self.get_input().notify_available()
        else:
            self.completed.append(the_process)

    def check_availability(self, the_item: Item) -> bool:
        return not (self.current_items >= self.num_servers)


