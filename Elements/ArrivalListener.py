from abc import ABC, abstractmethod

class ArrivalListener(ABC):

    @abstractmethod
    def item_received(self, item, source:int):
        pass

    @abstractmethod
    def get_v_element(self):
        pass
