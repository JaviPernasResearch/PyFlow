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

    def update_strategy(self, item) -> None:
        """
        Update the strategy information when an item arrives.
        Default implementation does nothing.
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
    def __init__(self, required_label_name: str, required_label_value = None):
        self.required_label_name = required_label_name
        self.required_label_value = required_label_value

    def update_strategy(self, item) -> None:
        """
        Update the accepted label values when an item arrives.
        """
        self.required_label_value = item.get_label_value(self.required_label_name)

    def is_valid(self, item) -> bool:
        """
        Check if the item has the required label.
        """
        return (self.required_label_name in item.labels and 
                self.required_label_value == item.get_label_value(self.required_label_name))
    
class MultiLabelStrategy(InputStrategy):
    def __init__(self, accepted_labels: dict):
            self.accepted_labels = accepted_labels

    def is_valid(self, item) -> bool:
        """
        Check if the item has any of the accepted labels.
        """
        labels = item.get_all_labels()
        for label_name, label_value in labels.items():
            if label_name in self.accepted_labels.keys() and label_value in self.accepted_labels[label_name]:
                return True
        return False

    def update_strategy(self, item) -> None:
        """
        Update the accepted label values when an item arrives.
        """
        labels = item.get_all_labels()
        for label_name, label_value in labels.items():
            if label_name in self.accepted_labels:
                self.accepted_labels[label_name] = label_value
