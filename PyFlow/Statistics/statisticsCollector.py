from ..Elements.element import Element
from ..Link.link import Link
from ..Items.item import Item


class StatisticsCollector():
    def __init__(self, element:Element):
        self.element:Element=element

    def execute (self, the_item:Item)->bool:
        if self.destination.receive(the_item):
            self.is_blocked=False
            return True
        else:
            self.is_blocked=True
            return False
        
    def send(self, the_item:Item)->bool:
        if self.destination is not None:
            return self.destination.receive(the_item)
        else:
            return False
        
    def notify_available(self)->bool:
        self.origin.unblock()

