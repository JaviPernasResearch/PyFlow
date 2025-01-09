from abc import ABC, abstractmethod
from ..Elements.element import Element
from ..Items.item import Item

class Link(ABC):
    @abstractmethod
    def execute(self,the_item:Item, source:Element)->bool:
        pass

    @abstractmethod
    def notify_available(self, source:Element)->bool:
        pass

