from abc import ABC, abstractmethod
from typing import Optional

from ..Items import *
from ..SimClock.simClock import SimClock


@abstractmethod
class Element(ABC):
    def __init__(self, name:str, clock:SimClock)->None:
        self.input=None
        self.output=None
        self.name:str=name
        self.clock:SimClock=clock

        clock.add_element(self)

        from ..Statistics import ElementStatsCollector
        self.stats_collector:ElementStatsCollector = ElementStatsCollector(self, self.clock)

    def get_name(self)->str:
        return self.name
    
    def get_input(self):
        return self.input
    
    def set_input(self, input_link)->None:
        self.input=input_link
    
    def get_output(self):
        return self.output
    
    def set_output(self, output_link)->None:
        self.output=output_link
    
    @abstractmethod
    def start(self)->None:
        pass

    @abstractmethod
    def receive(self, the_item:Item)->bool:
        pass

    @abstractmethod
    def unblock(self)->bool:
        pass

    @abstractmethod
    def check_availability(self, the_item: Item) -> bool:
        pass

    def get_stats_collector(self):
        return self.stats_collector

    # # Exposed Methods
    # def connect(self, successors:list, *args) -> None:
    #     from ..Link.simpleLink import SimpleLink  
    #     from ..Link.multipleLink import MultipleLink  
    #     if len(successors) > 1:
    #         the_link= MultipleLink(self, successors)
    #         self.set_output(the_link)
    #         for successor in successors:
    #             successor.set_input(the_link)
    #     else:
    #         the_link= SimpleLink(self, successors[0])
    #         self.set_output(the_link)
    #         successors[0].set_input(the_link)
    def connect_multiple(predecessors: list, successors: list, **kwargs) -> None:
        from ..Link.multipleLink import MultipleLink  
        from ..Link.outputStrategy import OutputStrategy, FirstAvailableStrategy
        
        strategy = kwargs.get('strategy', FirstAvailableStrategy())

        the_link= MultipleLink(predecessors, successors, strategy)
        for predecessor in predecessors:
            predecessor.set_output(the_link)
        for successor in successors:
            successor.set_input(the_link)

    def connect(self, successors: list, *args) -> None:
        from ..Link.simpleLink import SimpleLink  
        from ..Link.multipleLink import MultipleLink  

        # Check if there is already an output link
        if self.get_output() is not None:
            # If the existing link is not a MultipleLink, create a new MultipleLink
            if not isinstance(self.get_output(), MultipleLink):
                existing_successors = [self.get_output().get_destination()]
                all_successors = existing_successors + successors
                the_link = MultipleLink([self], all_successors)
            else:
                # If it is already a MultipleLink, just add the new successors
                all_successors = self.get_output().get_destinations() + successors
                the_link = MultipleLink([self], all_successors)
        else:
            # If there is no existing output link, create a new link
            if len(successors) > 1:
                the_link = MultipleLink([self], successors)
            else:
                the_link = SimpleLink(self, successors[0])

        self.set_output(the_link)
        
        for successor in successors:
            # Check if the successor already has an input link
            if successor.get_input() is not None:
                # If the existing link is not a MultipleLink, create a new MultipleLink
                if not isinstance(successor.get_input(), MultipleLink):
                    existing_predecessors = [successor.get_input().get_origin()]
                    all_predecessors = existing_predecessors + [self]
                    new_link = MultipleLink(all_predecessors, [successor])
                else:
                    # If it is already a MultipleLink, just add the new predecessor
                    all_predecessors = successor.get_input().get_origins() + [self]
                    new_link = MultipleLink(all_predecessors, [successor])
                successor.set_input(new_link)
            else:
                successor.set_input(the_link)