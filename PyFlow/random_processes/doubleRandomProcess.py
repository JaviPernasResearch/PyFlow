from abc import ABC, abstractmethod
from typing import Any

class DoubleRandomProcess(ABC):

    @abstractmethod
    def initialize(self, initialValue:float, parameters:Any)->float:
        pass
    
    @abstractmethod
    def next_value(self, parameters:Any)->float:
        pass