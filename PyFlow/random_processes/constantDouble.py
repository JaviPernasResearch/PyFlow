from .doubleRandomProcess import DoubleRandomProcess 
from .doubleProvider import DoubleProvider
from typing import Any
from ..SimClock.simClock import SimClock

class ConstantDouble(DoubleRandomProcess, DoubleProvider):
    def __init__(self, clock:SimClock, value:float):
        self.clock=clock
        self.value=value

    def get_mean(self)->float:
        return self.value

    def set_mean(self, value)->None:
        self.value=value

    def provide_value(self)->float:
        raise NotImplementedError ("Not supported yet. ")
    
    def next_value(self, parameters:list[float])->float:
        return self.value
    
    def initialize(self,initial_value:float, parameters:list[float])->None:
        self.value=initial_value


