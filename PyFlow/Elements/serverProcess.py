from scipy import stats
from typing import List, Union

from ..SimClock.simClock import SimClock

class ServerProcess():
    def __init__(self, my_server, random_delay:Union[stats.rv_continuous, stats.rv_discrete]):
        from ..Items.item import Item # Lazy import to avoid recircularity
        from .multiServer import MultiServer # Lazy import to avoid recircularity

        self.my_server:MultiServer=my_server
        self.the_item:Item=None
        self.random_delay=random_delay
        self.state:int=0  #0:idle, 1:busy, 2: bloocked

    def get_delay(self)->float:
        return self.random_delay.rvs(None)
    
    def execute(self) -> None:
        self.my_server.complete_server_process(self)
  