from abc import ABC, abstractmethod
from typing import Optional

from Elements.Link.Link import Link
from Items.item import Item

from SimClock.SimClock import SimClock


@abstractmethod
class Element(ABC):
    def __init__(self, name:str, clock:SimClock)->None:
        self.input:Optional[Link]=None
        self.output:Optional[Link]=None
        self.name:str=name
        self.clock:SimClock=clock

    def get_input(self)->Optional[Link]:
        return self.input
    
    def set_input(self,input_link:Link)->None:
        self.input=input_link
    
    def get_output(self)->Optional[Link]:
        return self.output
    
    def set_output(self, output_link:Link)->None:
        self.output=output_link

    @abstractmethod
    def start(self)->None:
        pass

    @abstractmethod
    def start(self)->None:
        pass

    @abstractmethod
    def retrieve(self)->Optional[Item]:
        pass

    @abstractmethod
    def notify_request(self)->bool:
        pass

    @abstractmethod
    def receive(self, the_item:Item)->bool:
        pass

    @abstractmethod
    def cancel_request(self)->bool:
        pass

    @abstractmethod
    def check_availability(self, the_item:Item)->bool:
        pass


