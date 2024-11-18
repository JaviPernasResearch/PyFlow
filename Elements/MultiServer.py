from collections import deque
from typing import Deque, List, Optional

from Elements.Element import Element
from Items.item import Item
from random_processes.DoubleRandomProcess import DoubleRandomProcess
from Elements.ServerProcess import ServerProcess
from SimClock.SimClock import SimClock
from Elements.WorkStation import WorkStation

import logging
logging.basicConfig(level=logging.INFO)
logger=logging.getLogger(__name__)

class MultiServer(Element,WorkStation):
    def __init__(self, random_times:List[DoubleRandomProcess], name:str, clock:SimClock):
        super().__init__(name, clock)
        self.idle_processes:Deque[ServerProcess]=deque()
        self.work_in_progress:Deque[ServerProcess]=deque()
        self.completed:Deque[ServerProcess]=deque()

        self.current_items=0
        self.pending_requests=0

        self.random_times:List[DoubleRandomProcess]=random_times
    
        self.capacity:int=len(random_times)

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
        # self.pending_requests=0

    def unblock(self)->Optional[Item]:
        if  self.completed:
            the_process=self.completed.popleft()  ##debería ser solamente peek, non peek and remove (popleft)
            the_item = the_process.the_item

            if self.get_output().send(the_item):
                ##Quitar proceso da lista se é posible envialo
                self.idle_processes.append(the_process)
                self.current_items -= 1
                self.get_input().notify_avaliable()
                return True
            else:
                return False
        else:
            return False
    # def notify_request(self)->bool:
    #     # if self.pending_requests > 0:
    #         if self.get_input().request(self):
    #             # self.pending_requests -= 1
    #             return True
    #         else:
    #             return False

    def receive(self, the_item:Item)->bool:
        if self.current_items >= self.capacity:
            # self.pending_requests += 1
            return False
        
        if not self.idle_processes:
            # self.pending_requests +=1
            return False
        
        
        the_process = self.idle_processes.popleft()
        the_process.the_item = the_item
        self.work_in_progress.append(the_process)
            
        self.current_items += 1
        logger.info(f"{self.name}: Received item. Current items: {self.current_items}")

        delay=the_process.get_delay()
        self.clock.schedule_event(the_process, delay)

        return True
        

    def complete_server_process(self, the_process:ServerProcess)->None:
        the_item = the_process.the_item
        self.work_in_progress.remove(the_process)
        
        if self.get_output().send(the_item):
            self.idle_processes.append(the_process)
            self.current_items -= 1

            # if self.pending_requests > 0:
            self.get_input().notify_avaliable()
                # self.pending_requests -= 1
        else:
            self.completed.append(the_process)

    def check_availability(self)->bool:
        return not (self.current_items >= self.capacity)

    # def cancel_request(self)->bool:
    #     if self.pending_requests > 0:
    #         self.pending_requests -= 1
    #         return True
    #     else:
    #         return False



