from .statVariable import StatVariable

# TimeStatVariable (for variables that update over time)  -- Pending
class TimeStatVariable(StatVariable):
    def __init__(self):
        super().__init__()
        self.time_steps = []  # Track values at different time steps

    def update(self, value, time_step):
        """Update the variable with a new value at a specific time step."""
        super().update(value)
        self.time_steps.append((time_step, value))

    def get_time_steps(self):
        """Retrieve the list of (time_step, value) pairs."""
        return self.time_steps

    def get_value_at_time(self, time_step) -> float:
        """Retrieve the value at a specific time step."""
        for ts, value in self.time_steps:
            if ts == time_step:
                return value
        return None  # Return None if the time step is not found