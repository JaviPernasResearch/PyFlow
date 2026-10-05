from typing import List

from ..Elements.element import Element
from ..Items.item import Item
from .link import Link
from .outputStrategy import OutputStrategy, FirstAvailableStrategy

##General Links are defined per element and per input and output lists (thus, 2 links per element connected upstream and downstream)
class GeneralLink (Link):
    def __init__(self, origins:List[Element], destinations:List[Element], strategy: OutputStrategy = None):
        self.origins:List[Element]=origins
        self.destinations:List[Element]=destinations
        self.strategy = strategy if strategy is not None else FirstAvailableStrategy()
        # Origins blocked waiting for space, shared by all links of the same model
        self.pending_requests = origins[0].model.pending_requests

    # Thus, at "send", there will be only one origin in the current link.
    def send(self, the_item:Item)->bool:
        index_destination=self.strategy.select_output(self.destinations, the_item)

        if index_destination<0:
            if self.origins[0] not in self.pending_requests:
                self.pending_requests.append(self.origins[0])
            return False
        else:
            self.origins[0].get_stats_collector().on_exit(the_item)
            self.destinations[index_destination].get_stats_collector().on_entry(the_item)
            self.destinations[index_destination].receive(the_item)
            return True

    def notify_available (self)->bool:
        non_prioritized_origins = []

        for origin in self.origins:
            if origin in self.pending_requests:
                self.pending_requests.remove(origin)
                if origin.unblock():  # The origin can return false if the output strategy does not allow the shipment
                    return True
                else:
                    self.pending_requests.append(origin)
            else:
                non_prioritized_origins.append(origin)
        # Consult the rest of inputs just in case (for instance, twice in a row to the same input queue, the second time there may not be a pending request
        for origin in non_prioritized_origins:
            if origin.unblock():
                return True
        return False

    def get_origins(self)->List[Element]:
        return self.origins

    def get_destinations(self)->List[Element]:
        return self.destinations
