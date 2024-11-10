from abc import ABC, abstractmethod
from Elements import Element
from Items import item

class Link(ABC):
    @abstractmethod
    def execute(self,the_item:item, source:Element)->bool:
        pass

    @abstractmethod
    def request(self, source:Element)->bool:
        pass

