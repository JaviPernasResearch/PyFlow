from random_processes.DoubleRandomProcess import DoubleRandomProcess 
from Elements.Link.DoubleProvider import DoubleProvider
from typing import Any
from SimClock import SimClock

import sys
import os

sys.path.append(os.path.abspath("C:/Users/Uxia/Documents/GitHub/PyFlow"))


class ConstantDouble(DoubleRandomProcess, DoubleProvider):
    def __init__(self, clock:SimClock, value:float):
        self.clock=clock
        self.value=value

    def get_mean(self)->float:
        return self.mean

    def set_mean(self, value)->None:
        self.value=value

    def provide_value(self)->float:
        raise NotImplementedError ("Not supported yet. ")
    
    def next_value(self, parameters:list[float])->float:
        return self.value
    
    def initialize(self,initial_value:float, parameters:list[float])->None:
        self.value=initial_value


