import warnings
from ..Elements.element import Element
from ..Items.item import Item

from .link import Link


class SimpleLink(Link):
    def __init__(self, origin:Element, destination:Element):
        warnings.warn(
            "SimpleLink is deprecated and will be removed in a future version. Use GeneralLink instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.origin:Element=origin
        self.destination:Element=destination
        self.is_blocked:bool=False

    def send(self, the_item:Item, origin:Element)->bool:
        if self.destination is not None:
            if self.destination.check_availability(the_item):
                self.origin.get_stats_collector().on_exit(the_item)
                self.destination.get_stats_collector().on_entry(the_item)
                return self.destination.receive(the_item)
        return False
        
    def notify_available(self)->bool:
        self.origin.unblock()

    def get_origin(self)->Element:
        return self.origin
    
    def get_destination(self)->Element:
        return self.destination
