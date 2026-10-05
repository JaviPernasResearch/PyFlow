from .statVariable import StatVariable

class StatLevelVariable(StatVariable):
    def __init__(self):
        super().__init__()

    def update(self, value):
        """Update the variable with a new value."""
        self.value += value
        self.count += 1
        current = self.value
        if self.max_value is None:
            self.max_value = self.min_value = value
        else:
            if current > self.max_value:
                self.max_value = current
            if current < self.min_value:
                self.min_value = current
        self.average = current / self.count
