from .statVariable import StatVariable

class StatTimeVariable(StatVariable):
    def __init__(self):
        super().__init__()

    def update(self, value):
        """Update the variable with a new value."""
        self.value = value
        self.count += 1
        self.max_value = max(self.max_value, value) if self.max_value is not None else value
        self.min_value = min(self.min_value, value) if self.min_value is not None else value
        self.average = (self.average * (self.count-1) + value) / self.count
