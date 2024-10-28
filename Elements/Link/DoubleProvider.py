from abc import ABC, abstractmethod

class DoubleProvider(ABC):
    @abstractmethod
    def provideValue (self)->float:
       pass
