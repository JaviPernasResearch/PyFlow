import numpy as np
from .doubleRandomProcess import DoubleRandomProcess 
from .doubleProvider import DoubleProvider
from typing import Any
from ..SimClock.simClock import SimClock

import sys
import os

sys.path.append(os.path.abspath("C:/Users/Uxia/Documents/GitHub/PyFlow"))


class PoissonProcess(DoubleRandomProcess, DoubleProvider):
    def __init__(self, clock:SimClock, mean:float):
        self.clock=clock
        self.mean=mean

    def get_mean(self)->float:
        return self.mean

    def set_mean(self, mean)->None:
        self.mean=mean

    def provide_value(self)->float:
        raise NotImplementedError ("Not supported yet. ")
    
    def next_value(self, parameters:list[float])->float:
        return -np.log(1-np.random.random())*self.mean
    
    def initialize(self,initial_value:float, parameters:list[float])->None:
        pass


