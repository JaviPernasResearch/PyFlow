from abc import ABC, abstractmethod
from ..Items.item import Item

class ArrivalListener(ABC):

    @abstractmethod
    def is_main_receiving(self, i: int) -> bool:
        pass

    @abstractmethod
    def component_received(self, item:Item, input_id:int):
        pass

