from Elements import Element
from Elements.Link.Link import Link
from Items.item import Item


class SimpleLink(Link):
    def __init__(self, origin:Element, destination:Element):
        self.origin:Element=origin
        self.destination:Element=destination
        self.is_blocked:bool=False

    @staticmethod
    def create_link(origin:Element, destination:Element)->None:
        the_link= SimpleLink(origin, destination)
        origin.set_output(the_link)
        destination.set_input(the_link)

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
        
    def NotifyAvaliable(self)->bool:
        self.origin.unblock()

