from abc import ABC, abstractmethod

class DoubleProvider(ABC):
    @abstractmethod
    def provide_value (self)->float:
       pass
