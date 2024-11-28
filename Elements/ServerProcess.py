from Items import item
from scipy import stats
from SimClock.SimClock import SimClock
from typing import List, Union

class ServerProcess():
    def __init__(self, my_server, random_delay:Union[stats.rv_continuous, stats.rv_discrete]):
        from Elements.MultiServer import MultiServer
        self.my_server:MultiServer=my_server
        self.the_item:item=None
        self.random_delay=random_delay
        self.state:int=0  #0:idle, 1:busy, 2: bloocked

    def get_delay(self)->float:
        return self.random_delay.rvs(None)
    
    def execute(self) -> None:
        self.my_server.complete_server_process(self)
  