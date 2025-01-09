from abc import ABC, abstractmethod

class IntegerProvider(ABC):
    @abstractmethod
    def provide_value(self)->float:
        pass
