from ..Elements.element import Element
from ..SimClock.simClock import SimClock


class StatisticsCollector():
    def __init__(self, element:Element, simclock:SimClock):
        self.element:Element=element
        self.simclock:SimClock=simclock

