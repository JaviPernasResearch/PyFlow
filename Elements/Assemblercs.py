from collections import deque
from typing import List, Dict, Optional

from Elements.Element import Element
from Elements.WorkStation import WorkStation
from SimClock.SimClock import SimClock
from Elements.ServerProcess import ServerProcess
from random_processes.DoubleRandomProcess import DoubleRandomProcess
from Items.item import item

class Assembler(Element, WorkStation):
    def __init__(self, name: str, clock: SimClock, random_times: DoubleRandomProcess, requirements: int):
        super().__init__(name, clock)
        self.random_times = random_times
        self.name = name
        self.requirements = requirements
        
        self.the_server: Optional[ServerProcess] = None
        self.items_completed: int = 0
        self.the_item: Optional[item] = None

    def start(self) -> None:
        self.the_server = ServerProcess(self, self.random_times, self.requirements)
        self.items_completed = 0

    def get_queue_length(self) -> int:
        return self.the_server.get_queue_length()

    def get_free_capacity(self) -> int:
        return self.requirements - self.the_server.get_queue_length()

    def get_name(self) -> str:
        return self.name

    def unblock(self) -> bool:
        if self.the_server.state == 2:
            if self.get_output().send_item(self.the_server.the_item, self):
                self.set_type(0)
                self.the_server.state = 0
                self.the_server.the_item = None
                self.the_server.clear_list()
                self.get_input().notify_available(self)
                self.the_item = None
                self.items_completed += 1
                return True
            return False
        return False

    def receive(self, the_item: item) -> bool:
        not_found = True

        if self.the_server.state == 0:
            if self.get_type() == the_item.get_id():
                not_found = not_found
            elif self.get_type() == 0:
                self.set_type(the_item.get_id())
                not_found = not_found

        if not_found:
            return False
        else:
            self.the_item = the_item
            self.the_server.add_item(the_item)
            v_element.load_item(the_item)

            if self.the_server.get_queue_length() == self.requirements:
                self.the_server.state = 1
                self.the_server.the_item = the_item

                delay = self.random_times.next_value()
                self.the_server.last_delay = delay
                self.sim_clock.schedule_event(self.the_server, delay)
            else:
                self.get_input().notify_available(self)

            return True

    def complete_server_process(self, the_process: ServerProcess) -> None:
        if self.the_server.state == 1:
            items_storaged = self.the_server.get_items()
            the_item = items_storaged[0]
            self.the_server.load_time = time.time()
            the_item.v_item = v_element.generate_item(the_item.get_id())

            for item in items_storaged:
                the_item.add_item(item)

            if self.get_output().send_item(the_item, self):
                self.set_type(0)
                self.the_server.state = 0
                self.the_server.the_item = None
                self.the_server.clear_list()
                the_item = None
                self.items_completed += 1
                self.get_input().notify_available(self)
            else:
                self.the_server.state = 2
                self.the_server.the_item = the_item
                self.the_server.clear_list()
        elif not self.get_input().notify_available(self):
            self.sim_clock.schedule_event(self.the_server, 2)

    def check_availability(self, the_item: item) -> bool:
        if self.get_type() == the_item.get_id() and self.the_server.state == 0:
            return True
        elif self.get_type() == 0:
            return True
        else:
            return False

    def get_item(self) -> Optional[item]:
        return self.the_item

    def set_capacity(self, capacity: int) -> None:
        self.requirements = capacity
