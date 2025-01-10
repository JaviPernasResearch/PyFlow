
from abc import ABC, abstractmethod

class InputStrategy(ABC):
    @abstractmethod
    def is_valid(self, item) -> bool:
        """
        Determine if the given item satisfies the strategy.
        Args:
            item: The item to check.
        Returns:
            bool: True if the item satisfies the strategy, False otherwise.
        """
        pass


class DefaultStrategy(InputStrategy):
    def __init__(self):
        pass

    def is_valid(self, item) -> bool:
        """
        Always returns True
        """
        return True
    
class SingleLabelStrategy(InputStrategy):
    def __init__(self, required_label: str):
        self.required_label = required_label

    def is_valid(self, item) -> bool:
        """
        Check if the item has the required label.
        """
        return self.required_label in item.labels
    
class MultiLabelStrategy(InputStrategy):
    def __init__(self, accepted_labels: list):
        self.accepted_labels = set(accepted_labels)  # Use a set for efficient lookup

    def is_valid(self, item) -> bool:
        """
        Check if the item has any of the accepted labels.
        """
        return bool(self.accepted_labels.intersection(item.labels))