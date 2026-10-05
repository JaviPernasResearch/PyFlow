# FILE: PyFlow/Link/outputStrategy.py
from abc import ABC, abstractmethod
from typing import List
from ..Elements.element import Element
from ..Items.item import Item

class OutputStrategy(ABC):
    @abstractmethod
    def select_output(self, outputs: List[Element], the_item: Item) -> int:
        pass

class FirstAvailableStrategy(OutputStrategy):
    def select_output(self, outputs: List[Element], the_item: Item) -> int:
        for i, output in enumerate(outputs):
            if output.check_availability(the_item):
                return i
        return -1

class RoundRobinStrategy(OutputStrategy):
    def __init__(self):
        self.index = 0

    def select_output(self, outputs: List[Element], the_item: Item) -> int:
        start_index = self.index
        while True:
            if outputs[self.index].check_availability(the_item):
                selected_index = self.index
                self.index = (self.index + 1) % len(outputs)
                return selected_index
            self.index = (self.index + 1) % len(outputs)
            if self.index == start_index:
                return -1

class QueueSizeStrategy(OutputStrategy):
    """Available destination with the fewest items; ties go to the lowest index."""

    def select_output(self, outputs: List[Element], the_item: Item) -> int:
        selected_index = -1
        min_queue_size = float('inf')
        for i, output in enumerate(outputs):
            queue_size = output.get_stats_collector().get_var_content_value()
            if queue_size < min_queue_size and output.check_availability(the_item):
                min_queue_size = queue_size
                selected_index = i
        return selected_index
    
class LabelBasedStrategy(OutputStrategy):
    def __init__(self, label_name: str):
        self.label_name = label_name

    def select_output(self, outputs: List[Element], the_item: Item) -> int:
        try:
            index = int(the_item.get_label_value(self.label_name))
            if 0 <= index < len(outputs):
                if outputs[index].check_availability(the_item):
                    return index
        except ValueError:
            pass
        return -1