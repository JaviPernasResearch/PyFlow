from abc import ABC, abstractmethod
from typing import Any, List, Optional, Union

from ..Items import *
from ..SimClock.simClock import SimClock

class Element(ABC):
    """Base class of every element. ``model`` may be a :class:`~PyFlow.model.Model`
    or, for backwards compatibility, the ``SimClock`` of a model."""

    def __init__(self, name: str, clock: Union["Model", SimClock]) -> None:
        from ..model import resolve_model
        self.input = None
        self.output = None
        self.name: str = name
        self.model = resolve_model(clock)
        self.clock: SimClock = self.model.clock

        self.origins: List[Element] = []
        self.destinations: List[Element] = []

        self.model.add_element(self)

        from ..Statistics import ElementStatsCollector
        self.stats_collector: ElementStatsCollector = ElementStatsCollector(self, self.clock)

    def _bind_sampler(self, spec: Any, purpose: str, **kwargs):
        """Sampler for ``spec`` with its own random stream keyed ``"<name>.<purpose>"``."""
        return self.model.bind_sampler(spec, f"{self.name}.{purpose}", **kwargs)

    def _new_item(self, **kwargs) -> Item:
        """New item stamped with the current time and a per-model id."""
        return Item(self.clock.get_simulation_time(), item_id=self.model.next_item_id(), **kwargs)

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

    def connect_multiple(predecessors: list, successors: list, **kwargs) -> None:
        from ..Link.generalLink import GeneralLink
        from ..Link.outputStrategy import OutputStrategy, FirstAvailableStrategy
        
        strategy = kwargs.get('strategy', FirstAvailableStrategy())

        for predecessor in predecessors:
            Element.connect(predecessor, successors=successors, strategy=strategy)

    def connect(self, successors: list, **kwargs) -> None:
        from ..Link.generalLink import GeneralLink
        from ..Link.outputStrategy import OutputStrategy, FirstAvailableStrategy

 
        strategy = kwargs.get('strategy', FirstAvailableStrategy())

        # Check if there is already an output link
        if self.get_output() is not None:
            existing_successors = self.get_output().get_destinations()
            all_successors = existing_successors + successors
            the_link = GeneralLink([self], all_successors, strategy)
        else:
            the_link = GeneralLink([self], successors, strategy)

        self.set_output(the_link)
        
        for successor in successors:
            # Check if the successor already has an input link
            if successor.get_input() is not None:
                existing_predecessors = successor.get_input().get_origins()
                all_predecessors = existing_predecessors + [self]
                the_link = GeneralLink(all_predecessors, [successor], strategy)
            else:
                the_link = GeneralLink([self], [successor], strategy)
                
            successor.set_input(the_link)
