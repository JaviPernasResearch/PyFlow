from collections import deque
from typing import List, Deque

from ..Elements.element import Element
from ..SimClock.simClock import SimClock
from ..Items.item import Item
from .link import Link
from .outputStrategy import OutputStrategy, FirstAvailableStrategy


class MultipleLink (Link):
    def __init__(self, origins:List[Element], destinations:List[Element], strategy: OutputStrategy = FirstAvailableStrategy()):
        self.origins:List[Element]=origins
        self.destinations:List[Element]=destinations
        self.strategy = strategy
        self.pending_request:Deque[int]=deque()

    def send(self, the_item:Item, origin:Element)->bool:
        index_origin=self.origins.index(origin)
        index_destination=self.strategy.select_output(self.destinations, the_item)

        if index_destination<0:
            self.pending_request.append(index_origin)
            return False
        else:
            origin.get_stats_collector().on_exit(the_item)
            self.destinations[index_destination].get_stats_collector().on_entry(the_item)
            self.destinations[index_destination].receive(the_item)
            return True
    

    # def notify_available (self)->bool:
    #     if self.pending_request:
    #         input_index=self.pending_request.popleft()
    #         the_item:Item=self.origins[input_index].retrieve()

    #         if the_item is None:
    #             return False
            
    #         self.send(the_item, self.origins[input_index])
    #         return True
    #     return False
    def notify_available (self)->bool:
        if self.pending_request:
            input_index=self.pending_request.popleft()
            return self.origins[input_index].unblock()
        return False
        
    def get_origins(self)->List[Element]:
        return self.origins
    
    def get_destinations(self)->List[Element]:
        return self.destinations
