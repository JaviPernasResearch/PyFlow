from abc import ABC, abstractmethod

class IntegerProvider(ABC):
    @abstractmethod
    def provideValue(self)->float:
        pass
