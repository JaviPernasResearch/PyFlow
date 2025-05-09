# FILE: PyFlow/Elements/source.py
from abc import ABC, abstractmethod
from typing import Optional, Union
from collections import deque
from ..Items.item import Item
from ..SimClock.simClock import SimClock
from scipy import stats
from .element import Element

class Source(Element):
    def __init__(self, name: str, clock: SimClock, model_item: Optional[Item] = None):
        super().__init__(name, clock)
        
        self.name = name
        self.clock = clock
        self.model_item = model_item
        self.last_items = deque(maxlen=10000000)
        self.number_items = 0

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def execute(self) -> None:
        pass

    def create_item(self, name: Optional[str] = None) -> Item:
        if self.model_item:
            return self.model_item.copy_model(self.clock.get_simulation_time(), name)
        else:
            return Item(self.clock.get_simulation_time())
        
    # def get_number_items(self) -> int: --> Statistics Collector
    #     return self.number_items