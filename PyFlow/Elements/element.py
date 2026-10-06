from abc import ABC, abstractmethod
from typing import Any, List, Optional, Union

from ..Items import *
from ..SimClock.simClock import SimClock
from ..stops import ElementRuntime


class Element(ElementRuntime, ABC):
    """Base class of every element. ``model`` may be a :class:`~PyFlow.model.Model`
    or, for backwards compatibility, the ``SimClock`` of a model.

    States, pausable work, stops and events come from :class:`~PyFlow.stops.ElementRuntime`."""

    def __init__(self, name: str, clock: Union["Model", SimClock]) -> None:
        from ..model import resolve_model
        self.input = None
        self.output = None
        self.name: str = name
        self.model = resolve_model(clock)
        self.clock: SimClock = self.model.clock

        self.origins: List[Element] = []
        self.destinations: List[Element] = []
        self.output_strategy = None   # OutputStrategy; None = first available
        self.input_strategy = None    # InputStrategy; None = accept everything
        self._init_runtime()

        self.model.add_element(self)

        from ..Statistics import ElementStatsCollector
        self.stats_collector: ElementStatsCollector = ElementStatsCollector(self, self.clock)

    def _bind_sampler(self, spec: Any, purpose: str, **kwargs):
        """Sampler for ``spec`` with its own random stream keyed ``"<name>.<purpose>"``."""
        return self.model.bind_sampler(spec, f"{self.name}.{purpose}", **kwargs)

    def _new_item(self, **kwargs) -> Item:
        """New item stamped with the current time and a per-model id."""
        return Item(self.clock.get_simulation_time(), item_id=self.model.next_item_id(), **kwargs)

    def expression_field(self, name: str):
        """Fields reachable from queries (``puller.name``, ``element.queue_length``...)."""
        if name == "name":
            return self.name
        if name == "class":
            return type(self).__name__
        if name == "state":
            return self.state
        if name == "queue_length":
            return self.get_queue_length()
        if name == "free_capacity":
            return self.get_free_capacity()
        raise KeyError(name)

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

    # ------------------------------------------------------------------ routing
    def set_output_strategy(self, strategy) -> None:
        self.output_strategy = strategy

    def set_input_strategy(self, strategy) -> None:
        self.input_strategy = strategy

    def validate_input(self, the_item: Item, origin=None) -> bool:
        return self.input_strategy is None or self.input_strategy.accepts(self, the_item, origin)

    def get_queue_length(self) -> int:
        """Items held (used by shortest-queue routing and MaxQueue input strategies)."""
        return int(self.stats_collector.get_var_content_value())

    def get_free_capacity(self) -> float:
        """Items that could still enter (``inf`` if unbounded)."""
        return float("inf")

    def connect_multiple(predecessors: list, successors: list, **kwargs) -> None:
        from ..Link.generalLink import GeneralLink
        from ..Link.outputStrategy import OutputStrategy, FirstAvailableStrategy
        
        import copy
        strategy = kwargs.get('strategy')

        for predecessor in predecessors:
            # each origin owns its strategy (a shared round robin would rotate for all)
            own = copy.deepcopy(strategy) if strategy is not None else None
            Element.connect(predecessor, successors=successors, strategy=own)

    def connect(self, successors: list, **kwargs) -> None:
        from ..Link.generalLink import GeneralLink
        from ..Link.outputStrategy import OutputStrategy, FirstAvailableStrategy

 
        strategy = kwargs.get('strategy')
        if strategy is not None:
            self.output_strategy = strategy
        elif self.output_strategy is None:
            self.output_strategy = FirstAvailableStrategy()
        strategy = self.output_strategy

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
