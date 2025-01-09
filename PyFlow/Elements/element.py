from abc import ABC, abstractmethod
from typing import Optional

#from Elements.Link.Link import Link
from ..Items import *
from ..SimClock.simClock import SimClock


@abstractmethod
class Element(ABC):
    def __init__(self, name:str, clock:SimClock)->None:
        self.input=None
        self.output=None
        self.name:str=name
        self.clock:SimClock=clock

    def get_input(self):
        return self.input
    
    def set_input(self, input_link)->None:
        self.input=input_link
    
    def get_output(self):
        return self.output
    
    def set_output(self, output_link)->None:
        self.output=output_link
    
    def connect(self, successors:list, *args) -> None:
        from ..Link.simpleLink import SimpleLink  
        if len(successors) > 1:
            pass
        else:
            the_link= SimpleLink(self, successors[0])
            self.set_output(the_link)
            successors[0].set_input(the_link)


    @abstractmethod
    def start(self)->None:
        pass

    @abstractmethod
    def receive(self, the_item:Item)->bool:
        pass

    @abstractmethod
    def unblock(self)->bool:
        pass

    @abstractmethod
    def check_availability(self, the_item:Item)->bool:
        pass


