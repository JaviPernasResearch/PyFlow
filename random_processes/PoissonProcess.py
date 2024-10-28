import numpy as np
from random_processes import DoubleRandomProcess 
from Elements.Link import DoubleProvider
from typing import Any
from SimClock import SimClock


class PoissonProcess(DoubleRandomProcess, DoubleProvider):
    def __init__(self, clock:SimClock, mean:float):
        self.clock=clock
        self.mean=mean

    def getMean(self)->float:
        return self.mean

    def setMean(self, mean)->None:
        self.mean=mean

    def provideValue(self)->float:
        raise NotImplementedError ("Not supported yet. ")
    
    def nextValue(self, parameters:list[float])->float:
        return -np.log(1-np.random.random())*self.mean
    
    def initialize(self,initial_value:float, parameters:list[float])->None:
        pass


