from abc import ABC, abstractmethod

class StatVariable(ABC):
    def __init__(self):
        self.value = 0
        self.count = 0
        self.max_value = None  # None until first update so max/min reflect real observations
        self.min_value = None
        self.average = 0

    @abstractmethod
    def update(self, value):
        """Update the variable with a new value."""
        pass

    # Getters
    def get_stats(self):
        """Retrieve current statistics for this variable."""
        return {
            'max': self.max_value,
            'min': self.min_value,
            'average': self.average,
            'count': self.count,
            'current': self.value
        }
    
    def get_stats_value(self) -> float:
        """Retrieve current current value for this variable."""
        return self.value
    
    def get_stats_max(self) -> float:
        """Retrieve current max value for this variable. Returns 0 if no observations yet."""
        return self.max_value if self.max_value is not None else 0

    def get_stats_min(self) -> float:
        """Retrieve current min value for this variable. Returns 0 if no observations yet."""
        return self.min_value if self.min_value is not None else 0

    def get_stats_average(self) -> float:
        """Retrieve current average value for this variable."""
        return self.average

    def get_stats_count(self) -> int:
        """Retrieve current count for this variable."""
        return self.count

    # Setters
    # def set_stats_current_value(self, value: float):
    #     """Set the current value for this variable."""
    #     self.current_value = value
    
    def set_stats_max(self, max_value: float):
        """Set the max value for this variable."""
        self.max_value = max_value

    def set_stats_min(self, min_value: float):
        """Set the min value for this variable."""
        self.min_value = min_value

    def set_stats_average(self, average: float):
        """Set the average value for this variable."""
        self.average = average

    def set_stats_count(self, count: int):
        """Set the count for this variable."""
        self.count = count