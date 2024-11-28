from SimClock.DoubleMinBinaryHeat import DoubleMinBinaryHeat
from SimClock.Event import Event

from typing import Any, List


class SimClock:
    def __init__(self):
        self.sim_time:float=0.0
        self.events:DoubleMinBinaryHeat=DoubleMinBinaryHeat(10)

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


clock=SimClock()

