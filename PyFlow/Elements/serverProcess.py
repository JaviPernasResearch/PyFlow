from scipy import stats
from typing import List, Union

from ..SimClock.simClock import SimClock
from .state import State
from .delayStrategy import DelayStrategy, LabelDelayStrategy, RandomDelayStrategy, ExpressionDelayStrategy

class ServerProcess():
    def __init__(self, my_server, delay_strategy:Union[stats.rv_continuous, stats.rv_discrete, str]):
        from ..Items.item import Item # Lazy import to avoid recircularity
        from .multiServer import MultiServer # Lazy import to avoid recircularity

        if isinstance(delay_strategy, str):
            self.delay_strategy = ExpressionDelayStrategy(delay_strategy)
        else:
            self.delay_strategy = RandomDelayStrategy(delay_strategy)

        self.my_server:MultiServer=my_server
        self.the_item:Item=None
        self.state:State=State.IDLE  #0:idle, 1:receiving, 3: busy, 4 blocked

    def get_delay(self)->float:
        return self.delay_strategy.get_delay(self.the_item)
    
    def execute(self) -> None:
        self.my_server.complete_server_process(self)

    def get_state(self) -> State:
        return self.state
    
    def set_state(self, new_state:State) -> None:
        self.state = new_state 

    def get_item(self):
        return self.the_item
    
    def set_item(self, the_item):
        self.the_item = the_item