from abc import ABC, abstractmethod
from Elements import Element
from Items import item

class Link(Element, item, ABC):
    @abstractmethod
    def send(self,the_item:item, source:Element)->bool:
        pass

    @abstractmethod
    def request(self, source:Element)->bool:
        pass

