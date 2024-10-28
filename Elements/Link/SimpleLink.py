from Elements import Element
from Elements.Link.Link import Link
from Elements.Link.SimpleLink import SimpleLink
from Items import item

class SimpleLink(Link):
    def __init__(self, origin:Element, destination:Element):
        self.origin:Element=origin
        self.destination:Element=destination
        self.is_blocked:bool=False

    @staticmethod
    def create_link(origin:Element, destination:Element)->None:
        the_link: SimpleLink=(origin, destination)
        origin.set_output(the_link)
        destination.set_input(the_link)

    def send (self, the_item:item)->bool:
        if self.destination.receive(the_item):
            self.is_blocked=False
            return True
        else:
            self.is_blocked=True
            return False
        
    def request(self)->bool:
        the_item:item=self.origin.retrieve()
        if the_item is not None:
            self.send(the_item, self.origin)
            self.origin.notify_request()
            return True
        else:
            return False

