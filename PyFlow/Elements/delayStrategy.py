from abc import ABC, abstractmethod
from typing import Union
from scipy import stats
from ..Items.item import Item

class DelayStrategy(ABC):
    @abstractmethod
    def get_delay(self, the_item: Item) -> float:
        pass

class RandomDelayStrategy(DelayStrategy):
    def __init__(self, random_times: Union[stats.rv_continuous, stats.rv_discrete]):
        self.random_times = random_times

    def get_delay(self, the_item: Item) -> float:
        return self.random_times.rvs()

class LabelDelayStrategy(DelayStrategy):
    def __init__(self, label_name: str):
        self.label_name = label_name

    def get_delay(self, the_item: Item) -> float:
        return float(the_item.get_label_value(self.label_name))