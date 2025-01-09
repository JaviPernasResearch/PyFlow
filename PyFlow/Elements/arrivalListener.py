from abc import ABC, abstractmethod

class ArrivalListener(ABC):

    @abstractmethod
    def item_received(self, item, input_id:int):
        pass

