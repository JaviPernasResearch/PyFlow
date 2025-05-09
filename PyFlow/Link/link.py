from abc import ABC, abstractmethod
from ..Elements.element import Element
from ..Items.item import Item

class Link(ABC):
    @abstractmethod
    def send(self, the_item: Item, origin: Element) -> bool:
        pass

    @abstractmethod
    def notify_available(self) -> bool:
        pass
