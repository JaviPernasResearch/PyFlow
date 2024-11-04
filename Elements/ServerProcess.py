from Elements import WorkStation
from Items import item
from random_processes import DoubleRandomProcess
from SimClock.SimClock import SimClock

class ServerProcess:
    def __init__(self, my_server:WorkStation, random_delay:DoubleRandomProcess):
        self.my_server:WorkStation=my_server
        self.the_item:item=None
        self.random_delay:DoubleRandomProcess=random_delay
        self.state:int=0  #0:idle, 1:busy, 2: bloocked

    def get_delay(self)->float:
        return self.random_delay.nextValue(None)
    
    def execute(self)->None:
        self.my_server.complete_server_process(self)
  