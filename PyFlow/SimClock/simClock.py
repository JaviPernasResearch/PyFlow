
from .doubleMinBinaryHeat import DoubleMinBinaryHeat
from .event import Event

from typing import Any, List


class SimClock:
    _instance = None  # Class-level attribute to hold the reference to the created SimClock instance

    def __init__(self):
        self.sim_time = 0.0
        self.events:DoubleMinBinaryHeat = DoubleMinBinaryHeat()
        SimClock._instance = self
        self.sim_elements = []

    @staticmethod
    def get_instance():
        """
        Get the static reference to the created SimClock instance.
        """
        if SimClock._instance is None:
                    SimClock._instance = SimClock()
        return SimClock._instance

    def schedule_event(self, the_event:'Event',time:float)->None:
        self.events.add(self.sim_time+time, the_event)

    def advance_clock(self, time:float) ->bool:
        t:float
        next_event:Event
        
        if self.events.count()==0:
            return False
        
        t=self.events.get_min_value()
        
        while t<=time:
            self.sim_time=t
            next_event=self.events.retrieve_first()
            next_event.execute()

            if self.events.count()==0:
                return False
            
            t=self.events.get_min_value()

        return True
    
    def reset(self)->None:
        self.sim_time=0.0
        self.events.reset()

    def get_simulation_time(self)-> float:
        return self.sim_time
    
    def add_element(self, element:Any)->None:
        from  ..Elements.element import Element
        if isinstance(element, Element):
            self.sim_elements.append(element)
        else:
             raise TypeError("The element must be an instance of Element")


