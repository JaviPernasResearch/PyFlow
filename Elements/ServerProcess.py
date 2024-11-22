from Items import item
from random_processes.DoubleRandomProcess import DoubleRandomProcess
from SimClock.SimClock import SimClock

class ServerProcess():
    def __init__(self, my_server, random_delay:DoubleRandomProcess):
        from Elements.MultiServer import MultiServer
        self.my_server:MultiServer=my_server
        self.the_item:item=None
        self.random_delay:DoubleRandomProcess=random_delay
        self.state:int=0  #0:idle, 1:busy, 2: bloocked

    def get_delay(self)->float:
        return self.random_delay.next_value(None)
    
    def execute(self) -> None:
        self.my_server.complete_server_process(self)
  