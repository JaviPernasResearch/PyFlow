from ..Elements.element import Element
from .statTimeVariable import StatTimeVariable
from .statLevelVariable import StatLevelVariable
from .statTimeWeightedVariable import StatTimeWeightedVariable
from ..SimClock.simClock import SimClock
from ..Items.item import Item


class ElementStatsCollector:
    def __init__(self, element:Element, simclock:SimClock):
        self.element = element
        self.simclock = simclock
        self.var_input:StatLevelVariable =  StatLevelVariable()
        self.var_output:StatLevelVariable =  StatLevelVariable()
        self.var_staytime:StatTimeVariable =  StatTimeVariable()
        # Content (WIP) is time-weighted: its average is the mean number of items held
        self.var_content:StatTimeWeightedVariable = StatTimeWeightedVariable(simclock.get_simulation_time())

        # Dictionary to store entry time for each item
        self.entry_times = {}

    def clear(self, t: float = 0.0) -> None:
        """Start from scratch (new run): no items inside, every statistic empty."""
        self.entry_times.clear()
        self.var_content = StatTimeWeightedVariable(t)
        self.reset(t)

    def reset(self, t: float = None) -> None:
        """Discard statistics collected before ``t`` (default: now), e.g. after a warm-up.
        Items currently inside the element are kept, so the content level is preserved."""
        if t is None:
            t = self.simclock.get_simulation_time()
        self.var_input = StatLevelVariable()
        self.var_output = StatLevelVariable()
        self.var_staytime = StatTimeVariable()
        self.var_content.reset(t)
    
    def on_entry(self, the_item:Item):
        # Only considers shipments of 1 item
        current_time = self.simclock.get_simulation_time()
        self.var_input.update(1)
        self.var_content.update(1, current_time)
        self.entry_times[the_item] = current_time
        if self.element._listeners:
            self.element._emit("item_entered", the_item)

    def rollback_entry(self, the_item: Item) -> None:
        """Undo ``on_entry`` when the element finally refused the item."""
        if self.entry_times.pop(the_item, None) is None:
            return
        self.var_input.value -= 1
        self.var_input.count -= 1
        self.var_content.update(-1, self.simclock.get_simulation_time())

    def absorb(self, the_item: Item) -> None:
        """The item ends here (sink): forget it without counting an exit."""
        if self.entry_times.pop(the_item, None) is not None:
            self.var_content.update(-1, self.simclock.get_simulation_time())

    def on_exit(self, the_item:Item):
        # Only considers shipments of 1 item
        self.var_output.update(1)

        # Items that never entered (created here, e.g. by a source or an assembler)
        # do not change the content level nor produce a stay time.
        if the_item in self.entry_times:
            current_time = self.simclock.get_simulation_time()
            entry_time = self.entry_times.pop(the_item)  # Get and remove the entry time
            self.var_content.update(-1, current_time)
            self.var_staytime.update(current_time - entry_time)
        if self.element._listeners:
            self.element._emit("item_exited", the_item)

        # Getters for each of the variables
    def get_var_input_stats(self):
        """Retrieve statistics for the input variable."""
        return self.var_input.get_stats()

    def get_var_output_stats(self):
        """Retrieve statistics for the output variable."""
        return self.var_output.get_stats()

    def get_var_staytime_stats(self):
        """Retrieve statistics for the stay time variable."""
        return self.var_staytime.get_stats()

    def get_var_content_stats(self):
        """Retrieve statistics for the content variable."""
        return self.var_content.get_stats(self.simclock.get_simulation_time())

    def get_var_input_max(self) -> float:
        """Retrieve the max value for the input variable."""
        return self.var_input.get_stats_max()

    def get_var_output_max(self) -> float:
        """Retrieve the max value for the output variable."""
        return self.var_output.get_stats_max()

    def get_var_staytime_max(self) -> float:
        """Retrieve the max value for the stay time variable."""
        return self.var_staytime.get_stats_max()

    def get_var_content_max(self) -> float:
        """Retrieve the max value for the content variable."""
        return self.var_content.get_stats_max()

    def get_var_input_min(self) -> float:
        """Retrieve the min value for the input variable."""
        return self.var_input.get_stats_min()

    def get_var_output_min(self) -> float:
        """Retrieve the min value for the output variable."""
        return self.var_output.get_stats_min()

    def get_var_staytime_min(self) -> float:
        """Retrieve the min value for the stay time variable."""
        return self.var_staytime.get_stats_min()

    def get_var_content_min(self) -> float:
        """Retrieve the min value for the content variable."""
        return self.var_content.get_stats_min()

    def get_var_input_average(self) -> float:
        """Retrieve the average value for the input variable."""
        return self.var_input.get_stats_average()

    def get_var_output_average(self) -> float:
        """Retrieve the average value for the output variable."""
        return self.var_output.get_stats_average()

    def get_var_staytime_average(self) -> float:
        """Retrieve the average value for the stay time variable."""
        return self.var_staytime.get_stats_average()

    def get_var_content_average(self) -> float:
        """Time-weighted average number of items held since the last reset."""
        return self.var_content.average(self.simclock.get_simulation_time())
    
    def get_var_input_value(self) -> float:
        """Retrieve the current value for the input variable."""
        return self.var_input.get_stats_value()

    def get_var_output_value(self) -> float:
        """Retrieve the current value for the output variable."""
        return self.var_output.get_stats_value()

    def get_var_staytime_value(self) -> float:
        """Retrieve the current value for the stay time variable."""
        return self.var_staytime.get_stats_value()

    def get_var_content_value(self) -> float:
        """Retrieve the current value for the content variable."""
        return self.var_content.get_stats_value()